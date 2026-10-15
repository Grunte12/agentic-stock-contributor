import os
import tempfile
import unittest

from helpers import CFG, new_store
from adobe_stock_analytics import recency, report, verify
from adobe_stock_analytics.config import metrics_version


def csv_file(text):
    f = os.path.join(tempfile.mkdtemp(), "d.csv")
    with open(f, "w") as fh:
        fh.write(text)
    return f


ROWS = "asset_id,uploaded_on\n1000,2026-01-01\n2000,2026-03-01\n3000,2026-06-01\nx,2026-06-02\n4000,not-a-date\n"


class RecencyTests(unittest.TestCase):
    def setUp(self):
        self.st = new_store()
        self.cfg = {**CFG, "recency": {**CFG["recency"], "window_days": 100, "min_anchors": 3}}

    def cut(self, as_of="2026-07-01", cfg=None):
        (m,) = recency.compute_recency_cut(self.st, cfg or self.cfg, as_of)
        return m

    def test_import_skips_bad_rows(self):
        self.assertEqual(recency.import_upload_dates(self.st, csv_file(ROWS))["dated"], 3)
        with self.assertRaises(ValueError):
            recency.import_upload_dates(self.st, csv_file("a,b\n1,2\n"))

    def test_no_data_gives_nothing(self):
        self.assertEqual(recency.compute_recency_cut(self.st, self.cfg, "2026-07-01"), [])

    def test_exact_interpolation(self):
        recency.import_upload_dates(self.st, csv_file(ROWS))
        m = self.cut()  # target 2026-03-23 = 22 of 92 days between 2000 (03-01) and 3000 (06-01)
        self.assertEqual(m["value"]["suggested_min_asset_id"], 2000 + round(1000 * 22 / 92))
        self.assertEqual(m["value"]["current_min_asset_id"], CFG["recency"]["min_asset_id"])
        self.assertEqual(m["value"]["target_date"], "2026-03-23")

    def test_null_reasons(self):
        recency.import_upload_dates(self.st, csv_file("asset_id,uploaded_on\n1,2026-01-01\n2,2026-06-01\n"))
        self.assertEqual(self.cut()["status"], "too_few_anchors")
        recency.import_upload_dates(self.st, csv_file("asset_id,uploaded_on\n1,2026-01-01\n2,2026-06-01\n3,2026-06-02\n"))
        self.assertEqual(self.cut("2030-01-01")["status"], "outside_anchor_range")
        recency.import_upload_dates(self.st, csv_file("asset_id,uploaded_on\n0,2026-06-03\n"))
        self.assertEqual(self.cut()["status"], "ids_not_monotonic")
        self.assertIsNone(self.cut()["value"])

    def test_suggestion_does_not_touch_config_metrics(self):
        recency.import_upload_dates(self.st, csv_file(ROWS))
        before = metrics_version(self.cfg)
        self.cut()
        self.assertEqual(before, metrics_version(self.cfg))

    def test_report_verifies(self):
        recency.import_upload_dates(self.st, csv_file(ROWS))
        r = report.report(self.st, self.cfg, calibration=True, as_of="2026-07-01")
        self.assertIn("not applied", r["markdown"])
        self.assertTrue(verify.verify_doc(self.st, r["markdown"])["ok"])

    def test_window_is_versioned(self):
        self.assertNotEqual(metrics_version(CFG), metrics_version(self.cfg))
