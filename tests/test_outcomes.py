import csv
import tempfile
import unittest
from pathlib import Path

from helpers import new_store
from adobe_stock_analytics import outcomes, parsers, urls

REJECTED = {"ctx_found": True, "page_state": None, "items": [
    {"asset_id": 11, "original_name": "people-cafe-01.jpg", "status": "state_refused", "created_ms": 5, "width": 3840, "height": 2880},
    {"asset_id": 12, "original_name": "people-cafe-02.jpg", "status": "state_refused", "created_ms": 6, "width": 3840, "height": 2880},
    {"asset_id": 21, "original_name": "tea-flatlay-03.jpg", "status": "state_refused", "created_ms": 7, "width": 3840, "height": 2880}],
    "history": {"11": {"cause": 9, "cause_label": "Tech problems"}, "12": {"cause": 9, "cause_label": "Tech problems"},
                "21": {"cause": 8, "cause_label": "Similar auto rejected"}}}
PORTFOLIO = {"overview_downloads_text": "3", "overview_earnings_text": "$1.50", "time_frame": "total", "all_count_text": "All(4)",
             "sort_text": "Sort by Downloads",
             "cards": [{"asset_id": 22, "downloads_text": "2"}, {"asset_id": 23, "downloads_text": "1"}, {"asset_id": 24, "downloads_text": "-"},
                       {"asset_id": 13, "downloads_text": "-"}],
             "named": [{"asset_id": 22, "original_name": "tea-flatlay-01.jpg", "status": "state_online", "created_ms": 8},
                       {"asset_id": 23, "original_name": "tea-flatlay-02.jpg", "status": "state_online", "created_ms": 9}]}


def store():
    st = new_store()
    st.add_observation("outcomes", urls.build_outcomes(), {}, REJECTED, parsers.parse_outcomes(REJECTED))
    st.add_observation("portfolio", urls.build_portfolio(), {}, PORTFOLIO, parsers.parse_portfolio(PORTFOLIO))
    return st


class OutcomeReportTests(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())

    def write(self, name, rows):
        p = self.d / name
        with open(p, "w", newline="") as f:
            csv.writer(f).writerows(rows)
        return str(p)

    def test_needs_an_outcomes_read(self):
        with self.assertRaises(ValueError):
            outcomes.build(new_store())

    def test_groups_rates_downloads_and_pending(self):
        g = self.write("g.csv", [["name_contains", "group"], ["people-cafe", "cafe people"], ["tea-flatlay", "tea flatlay"]])
        sub = self.d / "submitted"
        sub.mkdir()
        for n in ("tea-flatlay-01.jpg", "tea-flatlay-09.jpg", "notes.txt"):
            (sub / n).write_text("x")
        r = outcomes.build(store(), groups_csv=g, submitted_folder=str(sub), min_n=3)
        cafe, tea = r["by_group"]["cafe people"], r["by_group"]["tea flatlay"]
        self.assertEqual((cafe["decided"], cafe["rej_quality"], cafe["accept_rate"], cafe["too_few"]), (2, 2, 0.0, True))
        self.assertEqual((tea["accepted"], tea["rej_similar"], tea["pending"], tea["decided"], tea["downloads"]), (2, 1, 1, 3, 3))
        self.assertEqual(tea["accept_rate"], 0.667)
        self.assertFalse(tea["too_few"])
        # accepted files without a name (portfolio page 2+) stay ungrouped unless mapped by asset id
        self.assertEqual(r["by_group"]["(ungrouped)"]["accepted"], 2)
        self.assertEqual(r["overall"]["files"], 8)
        lo, hi = r["overall"]["accept_rate_95ci"]
        self.assertTrue(0 <= lo < r["overall"]["accept_rate"] < hi <= 1)

    def test_tags_and_asset_id_groups_and_ledger(self):
        g = self.write("g.csv", [["asset_id", "group"], ["24", "tea flatlay"], ["13", "cafe people"]])
        t = self.write("t.csv", [["name", "people", "tagger"], ["people-cafe-01.jpg", "large"], ["people-cafe-02.jpg", "large"], ["tea-flatlay-01.jpg", "none"]])
        r = outcomes.build(store(), groups_csv=g, tags_csv=t)
        self.assertEqual(set(r["by_tag"]), {"people"})
        self.assertEqual(r["by_tag"]["people"]["large"]["rej_quality"], 2)
        self.assertEqual(r["by_tag"]["people"]["(untagged)"]["files"], 4)
        self.assertEqual(r["by_group"]["cafe people"]["accepted"], 1)
        path = outcomes.write_ledger(r, self.d / "ledger.csv")
        rows = list(csv.DictReader(open(path)))
        self.assertEqual(len(rows), 7)
        self.assertIn("people", rows[0])

    def test_qc_verdict_as_tag(self):
        q = self.d / "qc.json"
        q.write_text('{"pass": ["people-cafe-01.jpg", "tea-flatlay-01.jpg"], "fail": ["people-cafe-02.jpg"]}')
        r = outcomes.build(store(), qc_decisions=str(q))
        lq = r["by_tag"]["local_qc"]
        self.assertEqual((lq["pass"]["rej_quality"], lq["pass"]["accepted"], lq["fail"]["rej_quality"]), (1, 1, 1))
        self.assertIn("(not in record)", lq)
        q.write_text('{"pass": ["tea-flatlay-01"], "fail": ["people-cafe"]}')  # scenario ids, as older records have
        lq = outcomes.build(store(), qc_decisions=str(q))["by_tag"]["local_qc"]
        self.assertEqual((lq["pass"]["files"], lq["fail"]["rej_quality"]), (1, 2))

    def test_bad_csv_shapes_are_refused(self):
        with self.assertRaises(ValueError):
            outcomes.build(store(), groups_csv=self.write("g.csv", [["file", "group"], ["a", "b"]]))
        with self.assertRaises(ValueError):
            outcomes.build(store(), tags_csv=self.write("t.csv", [["file", "people"], ["a", "b"]]))


if __name__ == "__main__":
    unittest.main()
