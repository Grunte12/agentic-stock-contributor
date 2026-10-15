import os
import tempfile
import unittest

from helpers import CFG, new_store
from adobe_stock_analytics import related, report, verify

GOOD = "TOP\nquery,value\nmatcha tea,100\nmatcha powder,82\n\nRISING\nquery,value\niced matcha,Breakout\nmatcha cafe,+250%\n"


def csv_file(text):
    f = os.path.join(tempfile.mkdtemp(), "r.csv")
    with open(f, "w", encoding="utf-8") as fh:
        fh.write(text)
    return f


class RelatedTests(unittest.TestCase):
    def test_import_and_metrics(self):
        st = new_store()
        r = related.import_related(st, csv_file(GOOD), "Matcha")
        self.assertEqual((r["top"], r["rising"], r["already_imported"]), (2, 2, False))
        ms = {m["name"]: m for m in related.compute_related(st, CFG, "matcha")}
        self.assertEqual(ms["related_top"]["value"][0], ["matcha tea", "100"])
        self.assertEqual(ms["related_rising"]["value"][0], ["iced matcha", "Breakout"])
        self.assertTrue(ms["related_top"]["inputs"][0].startswith("file:"))

    def test_same_file_is_noop(self):
        st = new_store()
        f = csv_file(GOOD)
        related.import_related(st, f, "matcha")
        self.assertTrue(related.import_related(st, f, "matcha")["already_imported"])

    def test_unknown_shapes_are_refused_entirely(self):
        st = new_store()
        for bad in ("a,b\n1,2\n", "TOP\nquery,value\nok,5\nbroken\n", ""):
            with self.assertRaises(ValueError):
                related.import_related(st, csv_file(bad), "matcha")
        self.assertEqual(st.db.execute("SELECT count(*) c FROM trend_related").fetchone()["c"], 0)  # no partial import
        with self.assertRaises(ValueError):
            related.import_related(st, csv_file(GOOD), "a|b")

    def test_missing_seed_gives_null(self):
        st = new_store()
        ms = related.compute_related(st, CFG, "nothing")
        self.assertTrue(all(m["value"] is None for m in ms))

    def test_report_verifies(self):
        st = new_store()
        related.import_related(st, csv_file(GOOD), "matcha")
        r = report.report(st, CFG, related=["matcha"])
        self.assertIn("not stock-image demand", r["markdown"])
        self.assertTrue(verify.verify_doc(st, r["markdown"])["ok"])
