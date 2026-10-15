import hashlib
import json
import tempfile
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from helpers import CFG, new_store
from adobe_stock_analytics import upload_stage as U
from adobe_stock_analytics.bridge import Bridge
from adobe_stock_analytics.queue import Queue

ON = {**CFG, "upload_stage": {**CFG["upload_stage"], "enabled": True}}
NOW = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)


def make_package(root, names=("a.jpg", "b.jpg"), folder="PKG_OK", created=NOW - timedelta(hours=1)):
    d = Path(root) / folder
    d.mkdir(parents=True)
    files = []
    for n in names:
        (d / n).write_bytes(b"\xff\xd8" + n.encode() * 50)
        files.append({"path": str(d / n), "sha256": hashlib.sha256((d / n).read_bytes()).hexdigest()})
    plan = {"ready_for_upload": True, "failures": [], "package_digest": "ab" * 32, "folder": str(d), "files": files,
            "created_at": created.isoformat().replace("+00:00", "Z")}
    pp = Path(root) / f"{folder}.plan.json"
    pp.write_text(json.dumps(plan))
    return pp, plan, d


class LoadPlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_off_by_default(self):
        pp, _, _ = make_package(self.tmp)
        with self.assertRaises(PermissionError):
            U.load_plan(pp, CFG, now=NOW)

    def test_valid_plan_lists_sorted_files(self):
        pp, _, _ = make_package(self.tmp, ("b.jpg", "a.jpg"))
        r = U.load_plan(pp, ON, now=NOW)
        self.assertEqual([f["name"] for f in r["files"]], ["a.jpg", "b.jpg"])
        self.assertEqual(r["package_digest"], "ab" * 32)

    def test_only_subset_and_unknown_name(self):
        pp, _, _ = make_package(self.tmp)
        self.assertEqual([f["name"] for f in U.load_plan(pp, ON, only=["b.jpg"], now=NOW)["files"]], ["b.jpg"])
        with self.assertRaises(U.StageError):
            U.load_plan(pp, ON, only=["zzz.jpg"], now=NOW)

    def test_not_ready_or_failures_refused(self):
        pp, plan, _ = make_package(self.tmp)
        for change in ({"ready_for_upload": False}, {"failures": ["x"]}):
            pp.write_text(json.dumps({**plan, **change}))
            with self.assertRaises(U.StageError):
                U.load_plan(pp, ON, now=NOW)

    def test_protected_folder_refused(self):
        for marker_folder in ("X_DO_NOT_UPLOAD", "X_quarantine_01", "quarantine_old", "X_holdout_a"):
            pp, _, _ = make_package(self.tmp, folder=marker_folder)
            with self.assertRaises(U.StageError, msg=marker_folder):
                U.load_plan(pp, ON, now=NOW)

    def test_changed_file_refused(self):
        pp, _, d = make_package(self.tmp)
        (d / "a.jpg").write_bytes(b"changed")
        with self.assertRaises(U.StageError):
            U.load_plan(pp, ON, now=NOW)

    def test_old_plan_refused(self):
        pp, _, _ = make_package(self.tmp, created=NOW - timedelta(hours=100))
        with self.assertRaises(U.StageError):
            U.load_plan(pp, ON, now=NOW)

    def test_file_outside_folder_and_non_image_refused(self):
        pp, plan, d = make_package(self.tmp)
        other = Path(self.tmp) / "other.jpg"
        other.write_bytes(b"x")
        bad = {**plan, "files": [{"path": str(other), "sha256": hashlib.sha256(b"x").hexdigest()}]}
        pp.write_text(json.dumps(bad))
        with self.assertRaises(U.StageError):
            U.load_plan(pp, ON, now=NOW)
        (d / "notes.txt").write_text("x")
        pp.write_text(json.dumps({**plan, "files": [{"path": str(d / "notes.txt"), "sha256": hashlib.sha256(b"x").hexdigest()}]}))
        with self.assertRaises(U.StageError):
            U.load_plan(pp, ON, now=NOW)

    def test_too_many_files_refused(self):
        pp, _, _ = make_package(self.tmp, tuple(f"{i}.jpg" for i in range(21)))
        with self.assertRaises(U.StageError):
            U.load_plan(pp, ON, now=NOW)

    def test_submit_count(self):
        self.assertEqual(U.submit_count("Submit 16 files"), 16)
        self.assertEqual(U.submit_count("Submit 1 file"), 1)
        self.assertIsNone(U.submit_count("Submit"))


def staged_queue(tmp, cfg=ON):
    pp, _, _ = make_package(tmp)
    plan = U.load_plan(pp, cfg, now=NOW)
    q = Queue(new_store(), cfg, clock=lambda: 1_700_000_000.0, rng=lambda: 0.5)
    jid = q.enqueue("upload_stage", {"package_digest": plan["package_digest"], "files": plan["files"]})
    return q, jid, plan


def good_payload(before=0, n=2, names=("a.jpg", "b.jpg")):
    return {"kind": "upload_stage", "page_state": None, "http_status": 200, "error": None,
            "before": {"all_count": before, "input_found": True},
            "after": {"all_count": before + n, "input_found": True}, "names_seen": list(names)}


class StageQueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_dispatch_carries_names_and_hashes_but_no_paths(self):
        q, jid, plan = staged_queue(self.tmp)
        job, why = q.next_job()
        self.assertEqual(why, "dispatched")
        self.assertEqual([f["name"] for f in job["files"]], ["a.jpg", "b.jpg"])
        self.assertNotIn("path", json.dumps(job))
        self.assertEqual(job["url"], "https://contributor.stock.adobe.com/en/uploads")

    def test_ok_when_submit_count_rises_by_files_staged_and_records_staged(self):
        q, jid, plan = staged_queue(self.tmp)
        q.next_job()
        res = q.complete(jid, good_payload())
        self.assertEqual(res["status"], "ok")
        self.assertEqual(q.store.get_state("stage_result:" + jid)["added"], 2)
        self.assertEqual({v["name"] for v in q.store.get_state("staged").values()}, {"a.jpg", "b.jpg"})
        self.assertIsNone(q.stop_state())

    def test_incomplete_stage_stops_the_queue_so_it_is_not_retried(self):
        q, jid, _ = staged_queue(self.tmp)
        q.next_job()
        p = good_payload(n=1)
        res = q.complete(jid, p)
        self.assertEqual((res["status"], res["reason"]), ("unknown", "stage_incomplete"))
        self.assertIn("upload_stage:stage_incomplete", q.stop_state()["reason"])
        self.assertIsNone(q.store.get_state("staged"))

    def test_sha_mismatch_and_missing_input_stop(self):
        for err, reason in (("sha_mismatch", "stage_sha_mismatch"), ("no_upload_input", "no_upload_input")):
            q, jid, _ = staged_queue(tempfile.mkdtemp())
            q.next_job()
            res = q.complete(jid, {"kind": "upload_stage", "error": err, "bad_file": "a.jpg"})
            self.assertEqual(res["reason"], reason)
            self.assertIsNotNone(q.stop_state())

    def test_captcha_page_blocks(self):
        q, jid, _ = staged_queue(self.tmp)
        q.next_job()
        self.assertEqual(q.complete(jid, {"kind": "upload_stage", "page_state": "signin"})["status"], "blocked")

    def test_turning_the_switch_off_before_dispatch_cancels_the_job(self):
        q, jid, _ = staged_queue(self.tmp)
        q.cfg = CFG
        self.assertEqual(q.next_job(), (None, "upload_stage_off"))
        self.assertEqual(q.job(jid)["state"], "failed")


class StageBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.q, self.jid, self.plan = staged_queue(self.tmp)
        self.b = Bridge(self.q, "tok", port=0, poll_seconds=1)
        self.b.start()
        self.base = f"http://127.0.0.1:{self.b.port}"

    def tearDown(self):
        self.b.stop()

    def get(self, path, token="tok"):
        req = urllib.request.Request(self.base + path, headers={"X-Intel-Token": token})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def test_file_served_only_for_a_dispatched_stage_job(self):
        self.assertEqual(self.get(f"/v1/file?job={self.jid}&i=0")[0], 404)  # still queued
        self.q.next_job()
        status, body = self.get(f"/v1/file?job={self.jid}&i=0")
        self.assertEqual(status, 200)
        self.assertEqual(hashlib.sha256(body).hexdigest(), self.plan["files"][0]["sha256"])
        self.assertEqual(self.get(f"/v1/file?job={self.jid}&i=9")[0], 404)
        self.assertEqual(self.get(f"/v1/file?job={self.jid}&i=x")[0], 404)
        self.assertEqual(self.get(f"/v1/file?job={self.jid}&i=0", token="bad")[0], 401)

    def test_reload_request_is_delivered_once(self):
        self.q.store.set_state("reload_extension", True)
        self.assertEqual(json.loads(self.get("/v1/next")[1]), {"job": None, "reason": "reload", "reload": True})
        self.assertNotIn("reload", json.loads(self.get("/v1/next")[1]))

    def test_changed_file_is_not_served(self):
        self.q.next_job()
        Path(self.plan["files"][0]["path"]).write_bytes(b"tampered")
        self.assertEqual(self.get(f"/v1/file?job={self.jid}&i=0")[0], 409)

    def test_not_served_after_switch_off(self):
        self.q.next_job()
        self.q.cfg = CFG
        self.assertEqual(self.get(f"/v1/file?job={self.jid}&i=0")[0], 404)


class LiveSwitchTests(unittest.TestCase):
    def test_default_config_is_reread_on_every_use_so_the_switch_works_without_restart(self):
        import json as _json
        from unittest import mock
        from adobe_stock_analytics import config as C
        cfg = {**CFG, "_live_config": True}
        on = {**CFG, "upload_stage": {**CFG["upload_stage"], "enabled": True}}
        with mock.patch.object(C, "load_config", return_value=on):
            self.assertTrue(C.upload_stage_cfg(cfg)["enabled"])
        with mock.patch.object(C, "load_config", return_value=CFG):
            self.assertFalse(C.upload_stage_cfg(cfg)["enabled"])
        self.assertFalse(C.upload_stage_cfg(CFG)["enabled"])  # a passed-in config is used as given


class StageToolTests(unittest.TestCase):
    def test_tools_are_listed_and_refuse_when_off(self):
        from adobe_stock_analytics import mcp_server
        from adobe_stock_analytics.app import App
        self.assertIn("stock_upload_stage", mcp_server.TOOLS)
        self.assertIn("stock_upload_result", mcp_server.TOOLS)
        app = App(data_dir=tempfile.mkdtemp())
        pp, _, _ = make_package(tempfile.mkdtemp())
        res = mcp_server.handle(app, {"id": 1, "method": "tools/call", "params": {"name": "stock_upload_stage", "arguments": {"plan_path": str(pp)}}})
        self.assertTrue(res["isError"])
        self.assertIn("upload staging is off", res["content"][0]["text"])

    def test_stage_refuses_files_already_staged(self):
        from adobe_stock_analytics.app import App
        tmp = tempfile.mkdtemp()
        app = App(data_dir=tempfile.mkdtemp(), cfg=ON)
        pp, plan, _ = make_package(tmp, created=datetime.now(timezone.utc) - timedelta(hours=1))
        app.store.set_state("staged", {plan["files"][0]["sha256"]: {"name": "a.jpg"}})
        with self.assertRaisesRegex(ValueError, "already staged"):
            app.stock_upload_stage(str(pp))


class KnowledgeAndSkillTests(unittest.TestCase):
    def setUp(self):
        from adobe_stock_analytics.app import App
        self.app = App(data_dir=tempfile.mkdtemp())

    def test_index_lists_every_doc_with_when_to_read(self):
        idx = self.app.stock_knowledge("index")
        topics = {t["topic"]: t["read_when"] for t in idx["topics"]}
        for need in ("mindset", "niche-research", "production-workflow", "qc-upscale", "metadata-seo", "upload-and-portal", "community-evidence"):
            self.assertTrue(topics.get(need), need)
        self.assertEqual(idx["start_with"], "mindset")

    def test_doc_is_returned_without_front_matter_and_unknown_topic_refused(self):
        d = self.app.stock_knowledge("mindset")
        self.assertTrue(d["markdown"].startswith("# Mindset"))
        with self.assertRaises(ValueError):
            self.app.stock_knowledge("../config/stock_analytics")

    def test_mcp_initialize_carries_instructions_and_lists_knowledge_tool(self):
        from adobe_stock_analytics import mcp_server
        init = mcp_server.handle(self.app, {"id": 1, "method": "initialize", "params": {}})
        self.assertIn("Never click Submit", init["instructions"])
        self.assertIn("stock_knowledge", mcp_server.TOOLS)

    def test_install_skill_dry_run_then_write_and_refuses_foreign_folder(self):
        import io
        from contextlib import redirect_stdout
        from adobe_stock_analytics import cli
        dest = tempfile.mkdtemp()
        buf = io.StringIO()
        with redirect_stdout(buf):
            cli.main(["--data-dir", tempfile.mkdtemp(), "install-skill", "--dest", dest])
        self.assertFalse(json.loads(buf.getvalue())["written"])
        self.assertFalse((Path(dest) / "adobe-stock").exists())
        with redirect_stdout(io.StringIO()):
            cli.main(["--data-dir", tempfile.mkdtemp(), "install-skill", "--dest", dest, "--confirm-write"])
        self.assertTrue((Path(dest) / "adobe-stock" / "SKILL.md").is_file())
        self.assertTrue((Path(dest) / "adobe-stock" / "references" / "mindset.md").is_file())
        other = tempfile.mkdtemp()
        (Path(other) / "adobe-stock").mkdir()
        (Path(other) / "adobe-stock" / "SKILL.md").write_text("name: something-else\n")
        with self.assertRaises(SystemExit):
            cli.main(["--data-dir", tempfile.mkdtemp(), "install-skill", "--dest", other, "--confirm-write"])
        self.assertEqual((Path(other) / "adobe-stock" / "SKILL.md").read_text(), "name: something-else\n")


if __name__ == "__main__":
    unittest.main()
