import unittest
from pathlib import Path

from helpers import CFG, fixture, ingest_search, new_store, seeded_store
from adobe_stock_analytics import metrics as M, parsers, report, urls, verify
from adobe_stock_analytics.config import metrics_version


class UrlTests(unittest.TestCase):
    def test_search_url(self):
        u = urls.build_search("matcha latte", "photo", "only_ai", "downloads")
        self.assertTrue(urls.is_allowed(u))
        self.assertIn("filters%5Bgentech%5D=only", u)
        self.assertIn("order=nb_downloads", u)

    def test_rejects_bad_input(self):
        for bad in (("", "photo"), ("x" * 101, "photo"), ("a\nb", "photo"), ("a", "audio")):
            with self.assertRaises(urls.UrlError):
                urls.build_search(*bad)
        with self.assertRaises(urls.UrlError):
            urls.build_asset("5; drop")

    def test_allowlist(self):
        self.assertFalse(urls.is_allowed("https://evil.example/search?k=x"))
        self.assertFalse(urls.is_allowed("http://stock.adobe.com/search?k=x"))
        self.assertFalse(urls.is_allowed("https://stock.adobe.com/Download/Watermarked/1"))
        self.assertTrue(urls.is_allowed(urls.build_contributor(900000008)))


class ParserTests(unittest.TestCase):
    def test_counts(self):
        self.assertEqual(parsers.parse_count("91,325 ผลลัพธ์สำหรับ matcha latte ใน ภาพ"), 91325)
        self.assertEqual(parsers.parse_count("1 234 results for x"), 1234)
        self.assertIsNone(parsers.parse_count("no count here"))
        self.assertIsNone(parsers.parse_count(None))

    def test_no_exact_match_page_counts_zero(self):
        for text in ("เราไม่พบผลลัพธ์ที่ตรงกันสำหรับ bakery pre order bags ผลลัพธ์ที่เกี่ยวข้องถูกแสดงไว้ด้านล่าง",
                     "เราไม่พบผลลัพธ์ ภาพ สำหรับ bakery cold chain ingredient tag"):
            r = parsers.parse_search({"results_text": text, "rows": [], "page_url": "https://stock.adobe.com/th/search?k=x"})
            self.assertEqual((r["status"], r["results"]), ("ok", 0))
        r = parsers.parse_search({"results_text": "nothing here", "rows": []})
        self.assertEqual(r["reason"], "no_count_text")

    def test_fixture_search_ok(self):
        st = new_store()
        _, p = ingest_search(st, "search_matcha_p0_1.json", "matcha latte", "all", "relevance")
        self.assertEqual((p["status"], p["results"], len(p["rows"])), ("ok", 91325, 99))

    def test_filters_not_applied_is_unknown(self):
        st = new_store()
        _, p = ingest_search(st, "search_matcha_p0_1.json", "matcha latte", "only_ai", "relevance")
        self.assertEqual((p["status"], p["reason"]), ("unknown", "filters_not_applied"))

    def test_blocked_states(self):
        for s in ("captcha", "restricted", "signin"):
            self.assertEqual(parsers.parse_search({"page_state": s})["status"], "blocked")

    def test_unknown_shape_never_zero(self):
        p = parsers.parse_search({"page_url": "https://stock.adobe.com/search?k=x", "rows": [], "results_text": None})
        self.assertEqual(p["status"], "unknown")
        self.assertNotIn("results", p)

    def test_asset(self):
        p = parsers.parse_asset({"asset_id": 5, "title": "t", "keywords": ["a", "b"], "keywords_total_text": "Show all (28)"})
        self.assertEqual((p["keywords_shown"], p["keywords_total"]), (2, 28))
        self.assertEqual(parsers.parse_asset({"asset_id": None})["status"], "unknown")


class MetricTests(unittest.TestCase):
    def setUp(self):
        self.st = seeded_store()
        self.m = {x["name"]: x for x in M.compute_keyword(self.st, CFG, "Matcha  Latte", "photo")}

    def test_values(self):
        self.assertEqual(self.m["results"]["value"], 91325)
        self.assertEqual(self.m["supply_band"]["value"], "saturated")
        self.assertEqual(self.m["ai_share"]["value"], round(63820 / 91325, 4))

    def test_missing_inputs_are_null_not_zero(self):
        self.assertIsNone(self.m["ai_split_gap"]["value"])
        self.assertEqual(self.m["ai_split_gap"]["status"], "no_input")

    def test_rating_rules(self):
        self.assertEqual(M.rate(CFG, 91325, 0.7, 0.05)[0], "SKIP")
        self.assertEqual(M.rate(CFG, 1500, 0.2, 0.05)[0], "GO")
        self.assertEqual(M.rate(CFG, 1500, 0.2, 0.5)[0], "MAYBE")
        self.assertEqual(M.rate(CFG, None, 0.2, 0.05)[0], "UNMEASURED")

    def test_ids_are_deterministic_and_versioned(self):
        again = {x["name"]: x for x in M.compute_keyword(self.st, CFG, "matcha latte", "photo")}
        self.assertEqual({k: v["metric_id"] for k, v in again.items()}, {k: v["metric_id"] for k, v in self.m.items()})
        cfg2 = {**CFG, "rating": {**CFG["rating"], "go": {**CFG["rating"]["go"], "max_dl_top1_creator_share": 0.2}}}
        self.assertNotEqual(metrics_version(CFG), metrics_version(cfg2))

    def test_lead_window(self):
        ms = M.compute_lead(self.st, CFG, "2026-10-10")
        xmas = next(m for m in ms if m["subject"] == "Christmas")
        self.assertEqual(xmas["value"], {"event": "2026-12-25", "start": "2026-09-25", "end": "2026-10-30", "state": "open"})

    def test_moving_holidays_use_listed_dates(self):
        ms = {m["subject"]: m for m in M.compute_lead(self.st, CFG, "2026-10-11")}
        self.assertEqual(ms["Easter"]["value"]["event"], "2027-03-28")
        self.assertEqual(ms["Lunar New Year"]["value"]["event"], "2027-02-06")
        self.assertEqual(ms["New Year (resolutions)"]["value"]["event"], "2027-01-01")

    def test_moving_holiday_without_future_date_is_null(self):
        cfg = {**CFG, "events": [{"name": "Easter", "dates": ["2020-04-12"]}]}
        (m,) = M.compute_lead(self.st, cfg, "2026-10-11")
        self.assertIsNone(m["value"])
        self.assertEqual(m["status"], "no_future_date_in_config")

    def test_lead_weeks_are_versioned(self):
        cfg2 = {**CFG, "lead": {**CFG["lead"], "start_weeks": 16}}
        self.assertNotEqual(metrics_version(CFG), metrics_version(cfg2))
        self.assertEqual(M.compute_lead(self.st, cfg2, "2026-10-10")[6]["value"]["start"], "2026-09-04")


class ReportVerifyTests(unittest.TestCase):
    def setUp(self):
        self.st = seeded_store()
        self.r = report.report(self.st, CFG, keywords=[{"keyword": "matcha latte"}])

    def test_render_is_byte_identical(self):
        r2 = report.report(self.st, CFG, keywords=[{"keyword": "matcha latte"}])
        self.assertEqual(self.r["markdown"], r2["markdown"])
        self.assertEqual(self.r["render_sha256"], r2["render_sha256"])
        self.assertIn("91,325", self.r["markdown"])

    def test_clean_doc_passes(self):
        mid = next(m["metric_id"] for m in self.r["metrics"] if m["name"] == "results")
        doc = f"# Decision\n\n{self.r['markdown']}\n\nSupply is crowded: 91,325 results [m:{mid}].\n"
        self.assertEqual(verify.verify_doc(self.st, doc), {"ok": True, "problems": []})

    def test_hand_typed_number_rejected(self):
        doc = f"{self.r['markdown']}\n\nAbout 80,000 results exist.\n"
        v = verify.verify_doc(self.st, doc)
        self.assertFalse(v["ok"])
        self.assertEqual(v["problems"][0]["type"], "untraceable_number")

    def test_number_with_wrong_cite_rejected(self):
        mid = next(m["metric_id"] for m in self.r["metrics"] if m["name"] == "results")
        v = verify.verify_doc(self.st, f"There are 12,000 results [m:{mid}].\n")
        self.assertFalse(v["ok"])

    def test_unknown_cite_rejected(self):
        v = verify.verify_doc(self.st, "Fine [m:0123456789abcdef].\n")
        self.assertEqual(v["problems"][0]["type"], "unknown_metric_cite")

    def test_edited_table_rejected(self):
        doc = self.r["markdown"].replace("91,325", "9,325")
        v = verify.verify_doc(self.st, doc)
        self.assertEqual(v["problems"][0]["type"], "table_mismatch")

    def test_dates_lists_and_code_allowed(self):
        v = verify.verify_doc(self.st, "1. First step\n2. Second on 2026-10-10 using `step 3`\n")
        self.assertTrue(v["ok"])


if __name__ == "__main__":
    unittest.main()


class TrendPortfolioTests(unittest.TestCase):
    def test_trends_import_and_metric(self):
        import tempfile, os
        from adobe_stock_analytics import trends
        st = new_store()
        f = os.path.join(tempfile.mkdtemp(), "t.csv")
        Path(f).write_text("Category: All categories\n\nWeek,matcha latte: (Worldwide)\n2026-01-04,50\n2026-01-11,<1\n2026-01-18,70\n")
        r = trends.import_trends(st, f)
        self.assertEqual(r["points"], 3)
        self.assertTrue(trends.import_trends(st, f)["already_imported"])
        m = {x["name"]: x for x in M.compute_trend(st, CFG, "Matcha Latte")}
        self.assertEqual((m["trend_mean"]["value"], m["trend_points"]["value"]), (60.0, 2))  # "<1" is skipped, not 0

    def test_portfolio_import_and_table(self):
        import tempfile, os
        from adobe_stock_analytics import portfolio
        st = new_store()
        f = os.path.join(tempfile.mkdtemp(), "p.csv")
        Path(f).write_text("asset_id,Downloads,group\n1,3,onboarding\n2,1,onboarding\n3,x,onboarding\n4,0,agents\n")
        self.assertEqual(portfolio.import_portfolio(st, f)["rows"], 3)  # the non-numeric row is skipped
        r = report.report(st, CFG, portfolio=True)
        self.assertIn("| onboarding | 2 | 4 | 2.00 |", r["markdown"])
        self.assertTrue(verify.verify_doc(st, r["markdown"])["ok"])
        with self.assertRaises(ValueError):
            Path(f).write_text("a,b\n1,2\n")
            portfolio.import_portfolio(st, f)


class LivePortfolioTests(unittest.TestCase):
    PAYLOAD = {"overview_downloads_text": "3", "overview_earnings_text": "$1.50", "time_frame": "total",
               "all_count_text": "All(125)", "sort_text": "Sort by Downloads",
               "cards": [{"asset_id": 11, "downloads_text": "2"}, {"asset_id": 22, "downloads_text": "1"},
                         {"asset_id": 33, "downloads_text": "-"}]}

    def ingest(self, payload):
        st = new_store()
        p = parsers.parse_portfolio(payload)
        st.add_observation("portfolio", urls.build_portfolio(), {}, payload, p)
        return st, p

    def test_parse(self):
        p = parsers.parse_portfolio(self.PAYLOAD)
        self.assertEqual((p["status"], p["overview_downloads"], p["overview_earnings"], p["all_count"]), ("ok", 3, 1.5, 125))
        self.assertIsNone(p["rows"][2]["downloads"])  # a dash stays None
        self.assertEqual(parsers.parse_portfolio({"cards": [], "overview_downloads_text": "1"})["status"], "unknown")
        bad = {**self.PAYLOAD, "cards": [{"asset_id": 1, "downloads_text": "?"}]}
        self.assertEqual(parsers.parse_portfolio(bad)["status"], "unknown")

    def test_urls_allowlist(self):
        self.assertTrue(urls.is_allowed(urls.build_portfolio()))
        self.assertTrue(urls.is_allowed(urls.build_probe("uploads")))  # own uploads list, read-only (extension 0.6.0)
        self.assertEqual(urls.build_probe("in_review"), "https://contributor.stock.adobe.com/en/uploads/review")
        self.assertTrue(urls.is_allowed(urls.build_probe("in_review")))
        self.assertFalse(urls.is_allowed(urls.build_probe("in_review") + "?x=1"))
        with self.assertRaises(urls.UrlError):
            urls.build_probe("account")
        for bad in ("https://contributor.stock.adobe.com/en/uploads?x=1", "https://contributor.stock.adobe.com/en/portfolio?x=1",
                    "https://contributor.stock.adobe.com/en/uploads/new",
                    "https://contributor.stock.adobe.com/en/account", "http://contributor.stock.adobe.com/en/portfolio"):
            self.assertFalse(urls.is_allowed(bad), bad)

    def test_probe_parser_stores_structure_only(self):
        ok = parsers.parse_probe({"text": "Rejected(3) Approved(10) " + "x" * 80, "tab_labels": ["Rejected(3)"], "page_state": None})
        self.assertEqual((ok["status"], ok["tab_labels"]), ("ok", ["Rejected(3)"]))
        self.assertEqual(parsers.parse_probe({"text": "short"})["reason"], "no_probe_shape")
        self.assertEqual(parsers.parse_probe({"text": "x" * 80, "page_state": "signin"})["status"], "blocked")  # signed out: sticky stop
        self.assertEqual(parsers.parse_probe({"text": "x" * 80, "page_state": "captcha"})["status"], "blocked")

    OUTCOMES = {"ctx_found": True, "page_state": None, "items": [
        {"asset_id": 11, "original_name": "a.jpg", "status": "state_refused", "created_ms": 5, "width": 4200, "height": 2800},
        {"asset_id": 22, "original_name": "b.jpg", "status": "state_refused", "created_ms": 6, "width": 4200, "height": 2800},
        {"asset_id": 33, "original_name": "c.jpg", "status": "state_refused", "created_ms": 7, "width": 1, "height": 1}],
        "history": {"11": {"cause": 9, "cause_label": "Tech problems"}, "22": {"cause": 8, "cause_label": "Similar auto rejected"}}}

    def test_outcomes_parser_classes_and_missing_cause(self):
        p = parsers.parse_outcomes(self.OUTCOMES)
        self.assertEqual(p["status"], "ok")
        self.assertEqual([r["outcome_class"] for r in p["rows"]], ["quality", "similar", "unknown"])  # no history -> unknown, never guessed
        self.assertEqual(p["history_missing"], 1)
        other = parsers.parse_outcomes({**self.OUTCOMES, "history": {"11": {"cause": 5, "cause_label": "x"}}})
        self.assertEqual(other["rows"][0]["outcome_class"], "other")

    def test_outcomes_parser_rejects_bad_shape_and_blocks(self):
        self.assertEqual(parsers.parse_outcomes({"ctx_found": False, "items": []})["reason"], "no_outcomes_shape")
        self.assertEqual(parsers.parse_outcomes({**self.OUTCOMES, "items": [{"asset_id": "x"}]})["reason"], "no_outcomes_shape")
        self.assertEqual(parsers.parse_outcomes({**self.OUTCOMES, "http_status": 429})["status"], "blocked")
        self.assertEqual(parsers.parse_outcomes({"ctx_found": True, "items": [], "page_state": "signin"})["status"], "blocked")
        self.assertEqual(parsers.parse_outcomes({"ctx_found": True, "items": []})["rows"], [])  # an empty Not accepted list is valid

    def test_outcomes_url_and_store(self):
        self.assertTrue(urls.is_allowed(urls.build_outcomes()))
        st = new_store()
        self.assertIsNone(st.latest_outcomes())
        parsed = parsers.parse_outcomes(self.OUTCOMES)
        obs = st.add_observation("outcomes", urls.build_outcomes(), {}, self.OUTCOMES, parsed)
        got = st.latest_outcomes()
        self.assertEqual((got["obs_id"], len(got["rows"]), got["rows"][0]["cause_label"]), (obs, 3, "Tech problems"))

    def test_portfolio_names_are_optional_and_stored(self):
        payload = {**self.PAYLOAD, "named": [{"asset_id": 11, "original_name": "a.jpg", "status": "state_online", "created_ms": 5},
                                             {"asset_id": "x", "original_name": "bad.jpg"}], "named_total": 125}
        st, p = self.ingest(payload)
        self.assertEqual((p["named"], p["named_total"]), ([{"asset_id": 11, "original_name": "a.jpg", "status": "state_online", "created_ms": 5}], 125))
        self.assertEqual(st.db.execute("SELECT original_name FROM pf_name").fetchone()["original_name"], "a.jpg")
        self.assertEqual(parsers.parse_portfolio(self.PAYLOAD)["named"], [])  # old payloads still parse

    def test_groups_and_dash_rule(self):
        import os, tempfile
        from adobe_stock_analytics import portfolio
        st, _ = self.ingest(self.PAYLOAD)
        f = os.path.join(tempfile.mkdtemp(), "g.csv")
        with open(f, "w") as fh:
            fh.write("asset_id,group\n11,onboarding\n33,onboarding\n22,agents\n")
        self.assertEqual(portfolio.import_groups(st, f)["mapped"], 3)
        r = report.report(st, CFG, portfolio=True)
        self.assertIn("| onboarding @ total | 2 | 2 | 1.00 |", r["markdown"])
        self.assertIn("| total | 3 | 1.50 | 125 | 2 | yes |", r["markdown"])
        self.assertTrue(verify.verify_doc(st, r["markdown"])["ok"])

    def test_cards_not_covering_total_gives_null(self):
        import os, tempfile
        from adobe_stock_analytics import portfolio
        st, _ = self.ingest({**self.PAYLOAD, "overview_downloads_text": "9"})
        f = os.path.join(tempfile.mkdtemp(), "g.csv")
        with open(f, "w") as fh:
            fh.write("asset_id,group\n11,a\n")
        portfolio.import_groups(st, f)
        r = report.report(st, CFG, portfolio=True)
        self.assertIn("n/a (cards_do_not_cover_total)", r["markdown"])

    def _trend_file(self, values):
        import tempfile, os
        f = os.path.join(tempfile.mkdtemp(), "t.csv")
        rows = "".join(f"2026-{1 + i // 4:02d}-{1 + (i % 4) * 7:02d},{v}\n" for i, v in enumerate(values))
        with open(f, "w") as fh:
            fh.write("Category: All categories\n\nWeek,matcha latte: (Worldwide)\n" + rows)
        return f

    def test_momentum_is_recent_mean_over_baseline_mean(self):
        from adobe_stock_analytics import trends
        st = new_store()
        trends.import_trends(st, self._trend_file([10] * 8 + [20] * 4))
        m = {x["name"]: x for x in M.compute_trend(st, CFG, "matcha latte")}
        self.assertEqual(m["trend_momentum"]["value"], 2.0)
        st2 = new_store()
        trends.import_trends(st2, self._trend_file([10] * 5))
        m2 = {x["name"]: x for x in M.compute_trend(st2, CFG, "matcha latte")}
        self.assertIsNone(m2["trend_momentum"]["value"])  # fewer points than recent + baseline

    def test_opportunity_combines_cited_components_and_verifies(self):
        from adobe_stock_analytics import trends
        st = seeded_store()
        trends.import_trends(st, self._trend_file([10] * 8 + [15] * 4))
        ms = {x["name"]: x for x in M.compute_opportunity(st, CFG, "matcha latte", "photo", "matcha latte")}
        o = ms["opportunity_score"]
        if o["value"] is not None:
            w, sc = CFG["opportunity"]["weights"], CFG["opportunity"]["supply_scores"]
            self.assertEqual(o["value"]["score"], round(w["supply"] * sc[o["value"]["rating"]] + w["attention"] * 0.67, 2))
        self.assertEqual(o["inputs"], sorted([f"metric:{ms['supply_rating']['metric_id']}", f"metric:{ms['trend_momentum']['metric_id']}"]))
        r = report.report(st, CFG, opportunities=[{"keyword": "matcha latte", "term": "matcha latte"}])
        self.assertIn("| matcha latte::matcha latte::photo |", r["markdown"])
        self.assertTrue(verify.verify_doc(st, r["markdown"])["ok"])

    def test_opportunity_is_null_when_attention_missing(self):
        st = seeded_store()
        ms = {x["name"]: x for x in M.compute_opportunity(st, CFG, "matcha latte", "photo", "no such term")}
        self.assertIsNone(ms["opportunity_score"]["value"])


class DashboardTests(unittest.TestCase):
    def test_dashboard_shows_metric_ids_and_escapes(self):
        from adobe_stock_analytics import dashboard
        st = seeded_store()
        ms = M.compute_opportunity(st, CFG, "matcha latte", "photo", "<b>x</b>")
        page = dashboard.render(st, CFG, "2026-10-10T00:00:00Z")
        self.assertIn("<code>" + [m for m in ms if m["name"] == "supply_rating"][0]["metric_id"] + "</code>", page)
        self.assertNotIn("<b>x</b>", page)
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", page)

    def test_empty_dashboard(self):
        from adobe_stock_analytics import dashboard
        self.assertIn("No metrics stored yet", dashboard.render(new_store(), CFG, "2026-10-10T00:00:00Z"))


import json  # noqa: E402


class WikipediaTests(unittest.TestCase):
    def _payload(self, days):
        items = [{"timestamp": d.strftime("%Y%m%d00"), "views": 100 + i} for i, d in enumerate(days)]
        return json.dumps({"items": items}).encode()

    def test_weekly_sums_drop_partial_weeks(self):
        from datetime import date, timedelta
        from adobe_stock_analytics import wikipedia
        start = date(2026, 9, 3)  # Thursday: first week is partial
        days = [start + timedelta(days=i) for i in range(20)]
        w = wikipedia.weekly_sums(json.loads(self._payload(days))["items"])
        self.assertEqual(list(w), ["2026-09-07", "2026-09-14"])
        self.assertEqual(w["2026-09-07"], sum(100 + i for i in range(4, 11)))

    def test_fetch_stores_series_once_and_feeds_momentum(self):
        from datetime import date, timedelta
        from adobe_stock_analytics import wikipedia
        st = new_store()
        days = [date(2026, 6, 1) + timedelta(days=i) for i in range(7 * 14)]
        raw = self._payload(days)
        r = wikipedia.fetch(st, "Matcha", term="matcha latte", today=date(2026, 9, 7), get=lambda url: raw)
        self.assertEqual(r["points"], 14)
        self.assertTrue(wikipedia.fetch(st, "Matcha", term="matcha latte", today=date(2026, 9, 7), get=lambda url: raw)["already_imported"])
        m = {x["name"]: x for x in M.compute_trend(st, CFG, "matcha latte")}
        self.assertEqual(m["trend_points"]["value"], 14)
        self.assertGreater(m["trend_momentum"]["value"], 1.0)  # views rise day by day in the fixture
