import json
import tempfile
import unittest
from datetime import date, timedelta

from adobe_stock_analytics import gdelt
from adobe_stock_analytics.store import Store


def payload(start, days, value=0.01):
    return json.dumps({"timeline": [{"series": "Volume Intensity", "data": [
        {"date": (start + timedelta(days=i)).strftime("%Y%m%dT000000Z"), "value": value} for i in range(days)]}]}).encode()


class GdeltTests(unittest.TestCase):
    def test_weekly_mean_drops_partial_weeks(self):
        mon = date(2026, 8, 17)  # a Monday
        pts = json.loads(payload(mon - timedelta(days=2), 18))["timeline"][0]["data"]
        w = gdelt.weekly_means(pts)
        self.assertEqual(list(w), ["2026-08-17", "2026-08-24"])
        self.assertAlmostEqual(w["2026-08-17"], 0.01)

    def test_fetch_stores_and_dedupes(self):
        with tempfile.TemporaryDirectory() as d:
            st = Store(d)
            raw = payload(date(2026, 8, 17), 28)
            slept = []
            r = gdelt.fetch(st, "EUDR", get=lambda u: raw, clock=lambda: 100.0, sleep=slept.append)
            self.assertEqual((r["points"], r["term"]), (4, "gdelt: EUDR"))
            r2 = gdelt.fetch(st, "EUDR", get=lambda u: raw, clock=lambda: 102.0, sleep=slept.append)
            self.assertTrue(r2["already_imported"])
            self.assertEqual(slept, [4.0])  # paced: 6 s gap minus 2 s elapsed

    def test_unknown_shape_stores_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            st = Store(d)
            with self.assertRaises(ValueError):
                gdelt.fetch(st, "x", get=lambda u: b'{"timeline": []}', sleep=lambda s: None)
            self.assertEqual(st.db.execute("SELECT COUNT(*) c FROM trend_point").fetchone()["c"], 0)

    def test_rate_limit_is_reported_not_retried(self):
        with tempfile.TemporaryDirectory() as d:
            st = Store(d)
            calls = []

            def get(u):
                calls.append(u)
                raise gdelt.RateLimited("429")
            with self.assertRaises(gdelt.RateLimited):
                gdelt.fetch(st, "x", get=get, sleep=lambda s: None)
            self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
