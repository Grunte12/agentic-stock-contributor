import io
import hashlib
import json
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

from helpers import CFG, fixture, new_store
from adobe_stock_analytics import mcp_server
from adobe_stock_analytics.app import App
from adobe_stock_analytics.bridge import Bridge
from adobe_stock_analytics.queue import Queue


class Clock:
    def __init__(self):
        self.t = 1_700_000_000.0

    def __call__(self):
        return self.t


def make_queue(cfg=CFG):
    ck = Clock()
    return Queue(new_store(), cfg, clock=ck, rng=lambda: 0.5), ck


REQ = {"keyword": "matcha latte", "media_type": "photo", "ai_filter": "all", "order": "relevance"}


class QueueTests(unittest.TestCase):
    def test_pacing_and_dispatch(self):
        q, ck = make_queue()
        a = q.enqueue("search", REQ)
        b = q.enqueue("search", {**REQ, "ai_filter": "only_ai"})
        self.assertEqual(q.enqueue("search", REQ), a)  # dedupe
        job, why = q.next_job()
        self.assertEqual((job["job_id"], why), (a, "dispatched"))
        self.assertEqual(q.next_job()[1], "busy")
        self.assertTrue(q.complete(a, fixture("search_matcha_p0_1.json"))["ok"])
        job, why = q.next_job()
        self.assertIsNone(job)
        self.assertTrue(why.startswith("pacing:"))
        ck.t += 25 + 5 + 1  # min gap + jitter(0.5*10)
        self.assertEqual(q.next_job()[0]["job_id"], b)

    def test_daily_cap(self):
        cfg = {**CFG, "pacing": {**CFG["pacing"], "daily_cap": 1}}
        q, ck = make_queue(cfg)
        q.enqueue("search", REQ)
        q.enqueue("search", {**REQ, "order": "downloads"})
        j, _ = q.next_job()
        q.complete(j["job_id"], fixture("search_matcha_p0_1.json"))
        ck.t += 100
        self.assertEqual(q.next_job(), (None, "daily_cap"))
        ck.t += 86400
        self.assertIsNotNone(q.next_job()[0])

    def test_captcha_stops_and_never_retries(self):
        q, ck = make_queue()
        a = q.enqueue("search", REQ)
        q.enqueue("search", {**REQ, "order": "downloads"})
        q.next_job()
        res = q.complete(a, {"page_state": "captcha"})
        self.assertEqual(res["status"], "blocked")
        ck.t += 1000
        self.assertEqual(q.next_job(), (None, "stopped:captcha"))
        q.resume()
        self.assertIsNotNone(q.next_job()[0])

    def test_http_403_stops(self):
        q, _ = make_queue()
        a = q.enqueue("search", REQ)
        q.next_job()
        q.complete(a, {"http_status": 429})
        self.assertEqual(q.stop_state()["reason"], "http_429")

    def test_unknown_shape_stops_at_once(self):
        q, _ = make_queue()
        a = q.enqueue("search", REQ)
        q.next_job()
        q.complete(a, {"page_url": "https://stock.adobe.com/search?k=x", "rows": [], "results_text": None})
        self.assertTrue(q.stop_state()["reason"].startswith("unknown_page_shape"))

    def test_filters_not_applied_stops_after_repeats(self):
        q, ck = make_queue()
        variants = [{"order": "relevance"}, {"order": "downloads"}, {"order": "creation"}]
        for i, v in enumerate(variants):
            ck.t += 1000
            q.enqueue("search", {**REQ, "ai_filter": "only_ai", **v})
            job, _ = q.next_job()
            q.complete(job["job_id"], fixture("search_matcha_p0_1.json"))  # page that lacks the AI filter
            if i < 2:
                self.assertIsNone(q.stop_state())
        self.assertEqual(q.stop_state()["reason"], "repeated_parse_failures")

    def test_dispatch_timeout_stops(self):
        q, ck = make_queue()
        q.enqueue("search", REQ)
        q.next_job()
        ck.t += 1000
        self.assertEqual(q.next_job(), (None, "stopped:dispatch_timeout"))

    def test_bad_params_rejected(self):
        q, _ = make_queue()
        with self.assertRaises(Exception):
            q.enqueue("search", {"keyword": "a\nb"})
        with self.assertRaises(Exception):
            q.enqueue("raw_url", {"url": "https://evil.example"})


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.q, self.ck = make_queue()
        self.b = Bridge(self.q, "tok", port=0, poll_seconds=1)
        self.b.start()
        self.base = f"http://127.0.0.1:{self.b.port}"

    def tearDown(self):
        self.b.stop()

    def call(self, path, body=None, token="tok", origin=None):
        h = {"X-Intel-Token": token}
        if origin:
            h["Origin"] = origin
        req = urllib.request.Request(self.base + path, data=json.dumps(body).encode() if body is not None else None, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_auth(self):
        self.assertEqual(self.call("/v1/ping", token="bad")[0], 401)
        self.assertEqual(self.call("/v1/ping", origin="https://evil.example")[0], 403)
        self.assertEqual(self.call("/v1/ping", origin="chrome-extension://abc")[0], 200)

    def test_records_extension_version(self):
        req = urllib.request.Request(self.base + "/v1/ping", headers={"X-Intel-Token": "tok", "X-Intel-Ext": "9.9.9"})
        urllib.request.urlopen(req, timeout=10).read()
        self.assertEqual(self.b.ext_version, "9.9.9")

    def test_rejects_foreign_host_header(self):
        req = urllib.request.Request(self.base + "/v1/ping", headers={"X-Intel-Token": "tok", "Host": "evil.example"})
        with self.assertRaises(urllib.error.HTTPError) as c:
            urllib.request.urlopen(req, timeout=10)
        self.assertEqual(c.exception.code, 403)

    def _get(self, path, **headers):
        req = urllib.request.Request(self.base + path, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.read().decode(), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode(), dict(e.headers)

    def test_dashboard_route_needs_its_own_token_host_and_no_origin(self):
        self.b.dashboard = lambda: "<html>ok</html>"
        url = self.b.dashboard_url().replace(self.base, "")
        code, body, hdr = self._get(url)
        self.assertEqual((code, body), (200, "<html>ok</html>"))
        self.assertEqual(hdr["Referrer-Policy"], "no-referrer")
        self.assertIn("default-src 'none'", hdr["Content-Security-Policy"])
        self.assertEqual(self._get("/dashboard")[0], 401)
        self.assertEqual(self._get("/dashboard?t=tok")[0], 401)  # the extension token is not the link token
        self.assertEqual(self._get(url, Origin="https://evil.example")[0], 403)
        self.assertEqual(self._get(url, Host="evil.example")[0], 403)
        self.assertNotEqual(self.b.dash_token, self.b.token)

    def test_dashboard_link_endpoint_needs_extension_token(self):
        self.assertEqual(self.call("/v1/dashboard-url", token="bad")[0], 401)
        code, res = self.call("/v1/dashboard-url")
        self.assertEqual((code, res["url"]), (200, self.b.dashboard_url()))

    def test_fake_extension_roundtrip(self):
        jid = self.q.enqueue("search", REQ)
        code, body = self.call("/v1/next")
        self.assertEqual(body["job"]["job_id"], jid)
        code, res = self.call("/v1/result", {"job_id": jid, "payload": fixture("search_matcha_p0_1.json")})
        self.assertEqual((code, res["status"]), (200, "ok"))
        self.assertTrue(self.b.connected())


class McpContractTests(unittest.TestCase):
    def setUp(self):
        self.app = App(data_dir=tempfile.mkdtemp())
        self.app.queue.rng = lambda: 0

    def rpc(self, method, params=None, i=1):
        return mcp_server.handle(self.app, {"id": i, "method": method, "params": params or {}})

    def call(self, name, **args):
        r = self.rpc("tools/call", {"name": name, "arguments": args})
        return json.loads(r["content"][0]["text"]) if not r["isError"] else r["content"][0]["text"]

    def test_tool_list_has_no_raw_url_number_or_pacing_inputs(self):
        names = set()
        for t in self.rpc("tools/list")["tools"]:
            names.add(t["name"])
            blob = json.dumps(t["inputSchema"])
            for forbidden in ('"url"', "pacing", "threshold", "min_gap", "daily_cap"):
                self.assertNotIn(forbidden, blob)
        self.assertIn("stock_report", names)

    def test_outcomes_tools(self):
        self.assertIn("run stock_outcomes_scan first", self.call("stock_outcomes"))
        self.assertEqual(len(self.call("stock_outcomes_scan")["job_ids"]), 1)
        job = self.app.queue.job(self.app.queue.enqueue("outcomes", {}))
        self.assertEqual(job["url"], "https://contributor.stock.adobe.com/en/uploads/rejected")

    def test_extra_args_rejected(self):
        self.assertIn("unexpected arguments", self.call("stock_status", url="https://x"))

    def test_every_numeric_field_has_provenance(self):
        from helpers import ingest_search
        st = self.app.store
        for fx, ai, order in (("search_matcha_p0_1.json", "all", "relevance"), ("search_matcha_p0_2.json", "all", "downloads"),
                              ("search_matcha_p0_3.json", "only_ai", "relevance")):
            obs, _ = ingest_search(st, fx, "matcha latte", ai, order)
        out = self.app.stock_metrics(keywords=["matcha latte"])
        for m in out["metrics"]:
            self.assertRegex(m["metric_id"], r"^[0-9a-f]{16}$")
            self.assertTrue(m["inputs"] or m["value"] is None or m["name"] == "lead_window")
        o = self.app.stock_observation(obs_id=obs)
        self.assertEqual(o["search_count"]["obs_id"], obs)
        self.assertTrue(all(r["obs_id"] == obs for r in o["rows"]))
        rep = self.app.stock_report(keywords=["matcha latte"])
        self.assertIn("91,325", rep["markdown"])
        self.assertEqual(len(rep["render_sha256"]), 64)

    def test_analysis_tools_spill_full_results_before_mcp(self):
        from helpers import ingest_search
        obs, _ = ingest_search(self.app.store, "search_matcha_p0_1.json", "matcha latte", "all", "relevance")

        observation = self.call("stock_observation", obs_id=obs)
        self.assertNotIn("rows", observation)
        self.assertGreater(observation["rows_count"], 0)
        self.assertTrue(Path(observation["artifact_path"]).is_file())
        self.assertLessEqual(len(json.dumps(observation, ensure_ascii=False)), mcp_server.MAX_MCP_RESULT_CHARS)

        report = self.call("stock_report", keywords=["matcha latte"])
        self.assertNotIn("markdown", report)
        self.assertGreater(report["markdown_chars"], 0)
        self.assertGreater(report["metric_count"], 0)
        artifact = Path(report["artifact_path"])
        self.assertTrue(artifact.is_file())
        self.assertEqual(hashlib.sha256(artifact.read_bytes()).hexdigest(), report["artifact_sha256"])
        self.assertEqual(artifact.stat().st_size, report["artifact_bytes"])
        self.assertIn("91,325", json.loads(artifact.read_text())["markdown"])
        self.assertLessEqual(len(json.dumps(report, ensure_ascii=False)), mcp_server.MAX_MCP_RESULT_CHARS)

    def test_large_operational_result_keeps_only_decision_fields(self):
        jobs = [{"job_id": f"job-{i:02d}", "kind": "search", "state": "done", "obs_id": f"obs-{i:02d}"}
                for i in range(30)]
        result = mcp_server._compact_result(self.app, "stock_wait", {"jobs": jobs, "stop": None})
        self.assertNotIn("jobs", result)
        self.assertEqual(result["state"], "completed")
        self.assertEqual(result["job_state_counts"], {"done": 30})
        self.assertNotIn("obs_ids", result)
        self.assertNotIn("artifact_path", result)
        self.assertLessEqual(len(json.dumps(result, ensure_ascii=False)), mcp_server.MAX_MCP_RESULT_CHARS)

    def test_wait_keeps_pending_and_failed_job_ids(self):
        jobs = [
            {"job_id": "job-pending", "kind": "search", "state": "queued", "obs_id": None},
            {"job_id": "job-failed", "kind": "search", "state": "failed", "obs_id": None},
        ]
        result = mcp_server._compact_result(self.app, "stock_wait", {"jobs": jobs, "stop": None})
        self.assertEqual(result["state"], "pending")
        self.assertEqual(result["unfinished_job_ids"], ["job-pending"])
        self.assertEqual(result["failed_job_ids"], ["job-failed"])

    def test_completed_asset_wait_preserves_observation_for_retrieval(self):
        parsed = {"status": "ok", "parser_version": "test", "asset_id": 123,
                  "title": "Sensor", "keywords": ["sensor", "maintenance"], "keywords_shown": 2, "keywords_total": 2}
        obs = self.app.store.add_observation("asset", "https://stock.adobe.com/123", {"asset_id": 123}, {}, parsed)
        job = self.app.stock_asset([123])["job_ids"][0]
        self.app.store.db.execute("UPDATE job SET state='done', obs_id=? WHERE job_id=?", (obs, job))
        waited = self.call("stock_wait", job_ids=[job], timeout_seconds=1)
        observation = self.call("stock_observation", obs_id=waited["observations"][job])
        self.assertEqual(observation["asset"]["keywords"], ["sensor", "maintenance"])

    def test_every_receipt_path_caps_nested_stop_and_retains_full_evidence(self):
        for name in ("stock_status", "stock_wait"):
            for reason in ("x" * 3000, "\\" * 3000):
                value = {"stop": {"reason": reason, "details": {"large": "y" * 3000}}}
                if name == "stock_wait":
                    value["jobs"] = [{"job_id": "job-1", "state": "queued", "obs_id": None}]
                receipt = mcp_server._compact_result(self.app, name, value)
                self.assertLessEqual(len(json.dumps(receipt, ensure_ascii=False)), mcp_server.MAX_MCP_RESULT_CHARS)
                self.assertTrue(receipt["stop"])
                full = json.loads(Path(receipt["artifact_path"]).read_text())
                self.assertEqual(full, value)

    def test_wait_explains_disconnected_queue_without_requeueing(self):
        job_id = self.app.stock_scan([REQ])["job_ids"][0]
        with mock.patch("adobe_stock_analytics.app.time.time", side_effect=[0, 1]):
            result = self.call("stock_wait", job_ids=[job_id], timeout_seconds=1)
        self.assertEqual(result["state"], "pending")
        self.assertEqual(result["queue_reason"], "extension_disconnected")
        self.assertEqual(result["unfinished_job_ids"], [job_id])
        self.assertIn("do not scan again", result["next"])
        self.assertNotIn("artifact_path", result)

    def test_tool_schemas_expose_runtime_limits_to_weak_models(self):
        scan = mcp_server.TOOLS["stock_scan"][1]["properties"]["requests"]
        self.assertEqual((scan["minItems"], scan["maxItems"]), (1, 20))
        self.assertEqual(scan["items"]["properties"]["keyword"]["maxLength"], 100)
        wait = mcp_server.TOOLS["stock_wait"][1]["properties"]
        self.assertEqual((wait["job_ids"]["minItems"], wait["job_ids"]["maxItems"]), (1, 20))
        self.assertEqual((wait["timeout_seconds"]["minimum"], wait["timeout_seconds"]["maximum"]), (1, 120))
        self.assertIn("explicitly instructs", mcp_server.TOOLS["stock_resume"][0])

    def test_knowledge_index_is_inline_but_topic_is_artifact(self):
        index = self.call("stock_knowledge", topic="index")
        self.assertIn("mindset", index["topics"])
        self.assertNotIn("artifact_path", index)
        topic = self.call("stock_knowledge", topic="mindset")
        self.assertNotIn("markdown", topic)
        self.assertEqual(topic["topic"], "mindset")
        self.assertTrue(Path(topic["artifact_path"]).is_file())
        self.assertLessEqual(len(json.dumps(topic, ensure_ascii=False)), mcp_server.MAX_MCP_RESULT_CHARS)

    def test_long_tool_error_is_spilled(self):
        with mock.patch.object(self.app, "stock_status", side_effect=ValueError("x" * 3000)):
            result = self.rpc("tools/call", {"name": "stock_status", "arguments": {}})
        self.assertTrue(result["isError"])
        body = json.loads(result["content"][0]["text"])
        self.assertEqual(body["status"], "error")
        self.assertTrue(Path(body["artifact_path"]).is_file())
        self.assertLessEqual(len(result["content"][0]["text"]), mcp_server.MAX_MCP_RESULT_CHARS)

    def test_outcome_receipt_keeps_coverage_and_provenance(self):
        result = mcp_server._compact_result(self.app, "stock_outcomes", {
            "rows": [{"asset_id": i, "outcome_class": "quality"} for i in range(100)],
            "counts": {"quality": 100},
            "accepted": [{"asset_id": i} for i in range(200)],
            "accepted_asset_ids": list(range(200)),
            "accepted_ids_read": 200,
            "accepted_total": 250,
            "accepted_obs_id": "obs-accepted",
            "read_at": "2026-10-23T00:00:00Z",
            "obs_id": "obs-outcomes",
        })
        self.assertEqual(result["counts"], {"quality": 100})
        self.assertEqual(result["accepted_ids_read"], 200)
        self.assertEqual(result["accepted_total"], 250)
        self.assertEqual(result["accepted_obs_id"], "obs-accepted")
        self.assertEqual(result["obs_id"], "obs-outcomes")
        self.assertNotIn("rows", result)
        self.assertNotIn("accepted", result)
        self.assertLessEqual(len(json.dumps(result, ensure_ascii=False)), mcp_server.MAX_MCP_RESULT_CHARS)

    def test_scan_and_resume_policy(self):
        r = self.call("stock_scan", requests=[{"keyword": "matcha latte"}])
        self.assertEqual(len(r["job_ids"]), 1)
        self.assertIn("user-only", self.call("stock_resume"))
        self.assertEqual(self.call("stock_stop")["stop"]["reason"], "agent_requested")

    def test_restart_is_exposed_and_preserves_stop(self):
        self.app.queue.stop("captcha")
        result = self.call("stock_restart_server")
        self.assertTrue(result["restart_requested"])
        self.assertEqual(result["stop"]["reason"], "captcha")

    def test_stdio_restart_execs_after_flushing_result(self):
        inp = io.StringIO(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                     "params": {"name": "stock_restart_server", "arguments": {}}}) + "\n")
        out = io.StringIO()
        with mock.patch.object(mcp_server.os, "execv") as execv:
            mcp_server.serve(self.app, inp, out)
        response = json.loads(out.getvalue())
        self.assertTrue(json.loads(response["result"]["content"][0]["text"])["restart_requested"])
        execv.assert_called_once()
        self.assertEqual(execv.call_args.args[0], mcp_server.sys.executable)

    def test_stdio_loop(self):
        inp = io.StringIO("\n".join(json.dumps(m) for m in (
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "nope"})) + "\n")
        out = io.StringIO()
        mcp_server.serve(self.app, inp, out)
        lines = [json.loads(x) for x in out.getvalue().splitlines()]
        self.assertEqual([x["id"] for x in lines], [1, 2, 3])
        self.assertEqual(lines[2]["error"]["code"], -32601)


if __name__ == "__main__":
    unittest.main()
