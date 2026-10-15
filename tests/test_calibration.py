import os
import tempfile
import unittest

from helpers import CFG, seeded_store
from adobe_stock_analytics import calibration, metrics as M, parsers, portfolio, report, urls, verify
from adobe_stock_analytics.config import metrics_version

PAYLOAD = {"overview_downloads_text": "3", "overview_earnings_text": "$1.50", "time_frame": "total",
           "all_count_text": "All(125)", "sort_text": "Sort by Downloads",
           "cards": [{"asset_id": 11, "downloads_text": "2"}, {"asset_id": 22, "downloads_text": "1"}]}


def csv_file(text):
    f = os.path.join(tempfile.mkdtemp(), "x.csv")
    with open(f, "w") as fh:
        fh.write(text)
    return f


class CalibrationTests(unittest.TestCase):
    def setUp(self):
        self.st = seeded_store()
        self.st.add_observation("portfolio", urls.build_portfolio(), {}, PAYLOAD, parsers.parse_portfolio(PAYLOAD))
        portfolio.import_groups(self.st, csv_file("asset_id,group\n11,tea\n22,tea\n"))
        self.cfg = {**CFG, "calibration": {**CFG["calibration"], "min_assets_per_bucket": 2}}

    def metrics(self, cfg=None):
        return {(m["name"], m["subject"]): m for m in calibration.compute_calibration(self.st, cfg or self.cfg)}

    def test_import_needs_columns(self):
        with self.assertRaises(ValueError):
            calibration.import_group_keywords(self.st, csv_file("a,b\n1,2\n"))

    def test_no_mapping_gives_nothing(self):
        self.assertEqual(calibration.compute_calibration(self.st, self.cfg), [])

    def test_group_and_buckets(self):
        self.assertEqual(calibration.import_group_keywords(self.st, csv_file("group,keyword\ntea,matcha  latte\n"))["mapped"], 1)
        ms = self.metrics()
        g = ms[("cal_group", "cal:tea")]["value"]
        self.assertEqual((g["keyword"], g["assets"], g["downloads"], g["dl_per_asset"]), ("matcha latte", 2, 3, 1.5))
        b = ms[("cal_band", f"calband:{g['band']}")]
        self.assertEqual(b["value"], {"groups": 1, "assets": 2, "downloads": 3, "dl_per_asset": 1.5})
        self.assertTrue(b["inputs"][0].startswith("metric:"))
        self.assertEqual(self.metrics(), ms)  # deterministic ids

    def test_bucket_under_floor_is_null_not_zero(self):
        calibration.import_group_keywords(self.st, csv_file("group,keyword\ntea,matcha latte\n"))
        ms = self.metrics(CFG)  # floor 20
        b = next(m for (n, _), m in ms.items() if n == "cal_rating")
        self.assertIsNone(b["value"])
        self.assertEqual(b["status"], "too_few_assets")

    def test_unmeasured_keyword_gives_null_group(self):
        calibration.import_group_keywords(self.st, csv_file("group,keyword\ntea,never scanned phrase\n"))
        g = self.metrics()[("cal_group", "cal:tea")]
        self.assertIsNone(g["value"])

    def test_cards_not_covering_total_gives_null_group(self):
        st = seeded_store()
        bad = {**PAYLOAD, "overview_downloads_text": "9"}
        st.add_observation("portfolio", urls.build_portfolio(), {}, bad, parsers.parse_portfolio(bad))
        portfolio.import_groups(st, csv_file("asset_id,group\n11,tea\n"))
        calibration.import_group_keywords(st, csv_file("group,keyword\ntea,matcha latte\n"))
        ms = {(m["name"], m["subject"]): m for m in calibration.compute_calibration(st, self.cfg)}
        self.assertIsNone(ms[("cal_group", "cal:tea")]["value"])

    def test_report_table_passes_verify_and_edit_fails(self):
        calibration.import_group_keywords(self.st, csv_file("group,keyword\ntea,matcha latte\n"))
        r = report.report(self.st, self.cfg, calibration=True)
        self.assertIn("association in this portfolio, not a forecast", r["markdown"])
        self.assertIn("1.50 per asset", r["markdown"])
        self.assertTrue(verify.verify_doc(self.st, r["markdown"])["ok"])
        self.assertFalse(verify.verify_doc(self.st, r["markdown"].replace("1.50 per asset", "9.50 per asset"))["ok"])

    def test_floor_is_versioned(self):
        self.assertNotEqual(metrics_version(CFG), metrics_version(self.cfg))


if __name__ == "__main__":
    unittest.main()


class OwnKeywordTests(unittest.TestCase):
    CARDS = {"overview_downloads_text": "3", "overview_earnings_text": "$1.50", "time_frame": "total",
             "all_count_text": "All(125)", "sort_text": "Sort by Downloads",
             "cards": [{"asset_id": 11, "downloads_text": "2"}, {"asset_id": 22, "downloads_text": "1"},
                       {"asset_id": 33, "downloads_text": "-"}, {"asset_id": 44, "downloads_text": "-"}]}

    def build(self, payload=None, pages=((11, ["tea", "cup"]), (22, ["tea", "mug"]), (33, ["tea", "cup"]))):
        from helpers import new_store
        st = new_store()
        p = payload or self.CARDS
        st.add_observation("portfolio", urls.build_portfolio(), {}, p, parsers.parse_portfolio(p))
        for aid, kws in pages:
            a = {"asset_id": aid, "title": f"t{aid}", "keywords": kws, "keywords_total_text": "Keywords (9)"}
            st.add_observation("asset", urls.build_asset(aid), {"asset_id": aid}, a, parsers.parse_asset(a))
        return st

    def metrics(self, st):
        return {m["name"]: m for m in portfolio.compute_own_keywords(st, CFG)}

    def test_counts_and_order(self):
        ms = self.metrics(self.build())
        self.assertEqual(ms["own_kw_coverage"]["value"], {"sold_total": 2, "sold_read": 2, "unsold_total": 2, "unsold_read": 1})
        self.assertEqual(ms["own_kw_sold"]["value"], [["tea", 2, 1]])  # cup/mug appear once among sold: below min_sold_assets
        self.assertEqual(self.metrics(self.build()), ms)

    def test_asset_without_page_is_total_not_read(self):
        ms = self.metrics(self.build(pages=((11, ["tea"]),)))
        self.assertEqual(ms["own_kw_coverage"]["value"]["sold_read"], 1)
        self.assertEqual(ms["own_kw_coverage"]["value"]["sold_total"], 2)
        self.assertIsNone(ms["own_kw_sold"]["value"])  # one sold page cannot reach min_sold_assets

    def test_cards_not_covering_total_gives_null_unsold(self):
        ms = self.metrics(self.build({**self.CARDS, "overview_downloads_text": "9"}))
        self.assertIsNone(ms["own_kw_coverage"]["value"]["unsold_total"])
        self.assertEqual(ms["own_kw_sold"]["value"], [["tea", 2, None]])

    def test_report_verifies(self):
        st = self.build()
        r = report.report(st, CFG, own_keywords=True)
        self.assertIn("association only", r["markdown"])
        self.assertTrue(verify.verify_doc(st, r["markdown"])["ok"])

    def test_knobs_are_versioned(self):
        cfg2 = {**CFG, "own_keywords": {**CFG["own_keywords"], "top_k": 5}}
        self.assertNotEqual(metrics_version(CFG), metrics_version(cfg2))
