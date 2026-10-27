import importlib.util
import json
import tempfile
import threading
import unittest
from unittest import mock
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "eval_mcp_workflow.py"
spec = importlib.util.spec_from_file_location("eval_mcp_workflow", SCRIPT)
evaluation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)


class McpWorkflowEvaluationTests(unittest.TestCase):
    def test_local_benchmarks_pass_and_report_measurements(self):
        report = evaluation.evaluate(repeats=1)
        self.assertEqual(report["mode"], "local_fixture_only_read_only")
        self.assertFalse(report["network_access"])
        self.assertFalse(report["portal_access"])
        self.assertFalse(report["bridge_started"])
        self.assertEqual(report["acceptance"], {"passed": 9, "total": 9, "success_rate": 1.0})
        self.assertEqual(report["agent_tokens"], "unavailable")
        self.assertEqual(report["model_tokens"], "unavailable")
        self.assertEqual(report["model_billing_cost"], "unavailable")
        for item in report["runs"]:
            self.assertTrue(item["pass"], item)
            self.assertGreaterEqual(item["latency_ms"], 0)
            self.assertGreater(item["output_bytes"], 0)
            self.assertLessEqual(item["output_chars"], item["output_bytes"])
            self.assertGreater(item["estimated_tokens_chars_div_4"], 0)
            self.assertEqual(item["retries"], 0)
            self.assertIn("errors", item)
        self.assertTrue(set(report["by_scenario"]["daily_cap_wait"]) >= {"min_ms", "p50_ms", "p95_ms", "max_ms"})

    def test_five_concurrent_duplicate_scans_share_one_three_job_set(self):
        with tempfile.TemporaryDirectory(prefix="mcp-eval-concurrent-") as data_dir:
            app = evaluation.make_app(data_dir)
            barrier = threading.Barrier(5)
            results = []
            failures = []

            def call_scan():
                try:
                    barrier.wait()
                    response = evaluation.tool(app, "stock_scan", {"requests": evaluation.VARIANTS})
                    results.append(evaluation.result(response)["job_ids"])
                except BaseException as exc:
                    failures.append(exc)

            threads = [threading.Thread(target=call_scan) for _ in range(5)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            physical = app.store.db.execute("SELECT count(*) FROM job WHERE kind='search'").fetchone()[0]
            self.assertFalse(failures)
            self.assertEqual(len(results), 5)
            self.assertTrue(all(ids == results[0] for ids in results))
            self.assertEqual(len(set(results[0])), 3)
            self.assertEqual(physical, 3)

    def test_plan_scorer_scores_public_synthetic_cases(self):
        score = evaluation.score_plan_file(SCRIPT.parents[1] / "tests/fixtures/mcp_plans.json")
        self.assertEqual((score["passed"], score["total"]), (10, 10))

    def test_plan_scorer_rejects_missing_wrong_and_unknown_arguments(self):
        original = json.loads((SCRIPT.parents[1] / "tests/fixtures/mcp_plans.json").read_text())
        for bad in ({"with_metadata": True}, {"plan_path": 42, "with_metadata": True},
                    {"plan_path": "plan.json", "with_metadata": "true"},
                    {"plan_path": "plan.json", "with_metadata": True, "portal_count": 30}):
            rows = json.loads(json.dumps(original))
            stage = next(x for x in rows if x["case"] == "stage_authorized")
            stage["calls"][0]["arguments"] = bad
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "plan.json"; path.write_text(json.dumps(rows))
                score = evaluation.score_plan_file(path)
            self.assertFalse(score["cases"]["stage_authorized"], bad)
            self.assertEqual(score["passed"], 9)

    def test_supply_variants_must_use_the_same_keyword(self):
        rows = json.loads((SCRIPT.parents[1] / "tests/fixtures/mcp_plans.json").read_text())
        rows[0]["calls"][1]["arguments"]["requests"][0]["keyword"] = "different phrase"
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "plan.json"; path.write_text(json.dumps(rows))
            self.assertFalse(evaluation.score_plan_file(path)["cases"]["supply_one_phrase"])

    def test_schema_checks_nested_bounds_enums_and_boolean_integers(self):
        schema = evaluation.mcp_server.TOOLS["stock_scan"][1]
        for bad in ({"requests": []}, {"requests": [{"keyword": "x", "ai_filter": "unknown"}]},
                    {"requests": ["not an object"]}, {"requests": [{"keyword": "x" * 101}]}):
            self.assertFalse(evaluation.matches_schema(bad, schema))
        self.assertFalse(evaluation.matches_schema({"asset_ids": [True]}, evaluation.mcp_server.TOOLS["stock_asset"][1]))

    def test_empty_plan_glob_is_not_a_success(self):
        with mock.patch("sys.argv", [str(SCRIPT), "--score-plans", "--plans-glob", "no-such-public-plan-*.json"]), \
             mock.patch("sys.stderr"):
            with self.assertRaises(SystemExit) as stopped:
                evaluation.main()
        self.assertEqual(stopped.exception.code, 2)

    def test_rejects_zero_repeats(self):
        with self.assertRaises(ValueError):
            evaluation.evaluate(0)


if __name__ == "__main__":
    unittest.main()
