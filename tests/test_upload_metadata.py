import csv
import hashlib
import io
import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from helpers import CFG, new_store
from test_upload_stage import NOW, make_package
from adobe_stock_analytics import parsers
from adobe_stock_analytics import upload_metadata as M
from adobe_stock_analytics.queue import Queue

ON = {**CFG, "upload_metadata": {**CFG["upload_metadata"], "enabled": True}}
KW = ",".join(f"keyword{i}" for i in range(8))


def write_csv(d, rows, name="adobe_stock.csv"):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Filename", "Title", "Keywords", "Category"])
    for r in rows:
        w.writerow(r)
    p = Path(d) / name
    p.write_text(buf.getvalue(), encoding="utf-8")
    return p


def package(tmp, rows=None, names=("a.jpg", "b.jpg")):
    pp, plan, d = make_package(tmp, names)
    p = write_csv(d, rows if rows is not None else [(n, f"Title {n}", KW, "8") for n in names])
    plan["csv"] = [{"path": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}]
    pp.write_text(json.dumps(plan))
    return pp, d, p


class LoaderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_off_by_default(self):
        pp, _, _ = package(self.tmp)
        with self.assertRaises(PermissionError):
            M.load_metadata_plan(pp, CFG, now=NOW)

    def test_valid_plan_returns_flags_csv_and_names(self):
        pp, _, p = package(self.tmp)
        r = M.load_metadata_plan(pp, ON, now=NOW)
        self.assertEqual((r["rows"], r["names"]), (2, ["a.jpg", "b.jpg"]))
        self.assertEqual(r["flags"], {"generative_ai": True, "people_property": "no", "include_in_submission": True, "people_property_fictional": True})
        self.assertEqual(r["csv"]["sha256"], hashlib.sha256(p.read_bytes()).hexdigest())

    def test_bad_csv_rows_refused(self):
        cases = {
            "few keywords": [("a.jpg", "T", "one,two", "8"), ("b.jpg", "T", KW, "8")],
            "empty title": [("a.jpg", "", KW, "8"), ("b.jpg", "T", KW, "8")],
            "dup keywords": [("a.jpg", "T", "a,b,c,d,A", "8"), ("b.jpg", "T", KW, "8")],
            "category text": [("a.jpg", "T", KW, "Food"), ("b.jpg", "T", KW, "8")],
            "missing file row": [("a.jpg", "T", KW, "8")],
            "extra row": [("a.jpg", "T", KW, "8"), ("b.jpg", "T", KW, "8"), ("c.jpg", "T", KW, "8")],
            "repeated row": [("a.jpg", "T", KW, "8"), ("a.jpg", "T", KW, "8"), ("b.jpg", "T", KW, "8")],
        }
        for label, rows in cases.items():
            pp, _, _ = package(tempfile.mkdtemp(), rows)
            with self.assertRaises(M.StageError, msg=label):
                M.load_metadata_plan(pp, ON, now=NOW)

    def test_changed_csv_refused(self):
        pp, _, p = package(self.tmp)
        p.write_text(p.read_text() + "\n")
        with self.assertRaises(M.StageError):
            M.load_metadata_plan(pp, ON, now=NOW)

    def test_bad_people_answer_refused(self):
        pp, _, _ = package(self.tmp)
        bad = {**ON, "upload_metadata": {**ON["upload_metadata"], "people_property": "maybe"}}
        with self.assertRaises(M.StageError):
            M.load_metadata_plan(pp, bad, now=NOW)

    def test_old_plan_and_protected_folder_refused(self):
        pp, plan, d = make_package(self.tmp, folder="X_holdout_9")
        with self.assertRaises(M.StageError):
            M.load_metadata_plan(pp, ON, now=NOW)


def good_after(n=2, **kw):
    a = {"all_count": n, "submit_count": n, "keyword_counts": [8] * n, "ai_checked": True, "include_checked": True, "fictional_checked": True}
    a.update(kw)
    return {"kind": "upload_metadata", "page_state": None, "error": None, "steps": ["csv_applied", "saved"], "after": a}


class ParserTests(unittest.TestCase):
    def test_ok(self):
        r = parsers.parse_upload_metadata(good_after(), 2, {"people_property_fictional": True})
        self.assertEqual((r["status"], r["tiles_with_keywords"]), ("ok", 2))
        self.assertEqual(parsers.parse_upload_metadata(good_after(fictional_checked=None), 2, {"people_property_fictional": False})["status"], "ok")

    def test_each_shortfall_is_not_ok(self):
        for label, p, reason in (
            ("submit short", good_after(submit_count=0), "metadata_incomplete"),
            ("count short", good_after(all_count=1), "metadata_incomplete"),
            ("tile without keywords", good_after(keyword_counts=[8, 0]), "metadata_incomplete"),
            ("ai off", good_after(ai_checked=False), "flags_not_set"),
            ("fictional box not ticked", good_after(fictional_checked=False), "flags_not_set"),
            ("fictional box missing", good_after(fictional_checked=None), "flags_not_set"),
            ("include unknown", good_after(include_checked=None), "flags_not_set"),
            ("no shape", {"kind": "upload_metadata", "after": {}}, "no_metadata_shape"),
        ):
            r = parsers.parse_upload_metadata(p, 2, {"people_property_fictional": True})
            self.assertEqual((r["status"], r["reason"]), ("unknown", reason), label)

    def test_error_blocked_and_bad_payload(self):
        r = parsers.parse_upload_metadata({"error": "csv_dialog_missing", "steps": ["page_ready"], "detail": "x"}, 2)
        self.assertEqual(r["reason"], "metadata_error:csv_dialog_missing")
        self.assertEqual(parsers.parse_upload_metadata({"page_state": "captcha"}, 2)["status"], "blocked")
        self.assertEqual(parsers.parse_upload_metadata([], 2)["reason"], "payload_not_object")


def meta_queue(tmp, cfg=ON):
    pp, _, _ = package(tmp)
    plan = M.load_metadata_plan(pp, cfg, now=NOW)
    q = Queue(new_store(), cfg, clock=lambda: 1_700_000_000.0, rng=lambda: 0.5)
    jid = q.enqueue("upload_metadata", {"package_digest": plan["package_digest"], "csv": {k: plan["csv"][k] for k in ("name", "sha256", "size")},
                                        "count": len(plan["names"]), "flags": plan["flags"]})
    return q, jid


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_dispatch_carries_csv_hash_count_and_flags_but_no_path(self):
        q, jid = meta_queue(self.tmp)
        job, why = q.next_job()
        self.assertEqual(why, "dispatched")
        self.assertEqual((job["kind"], job["count"], len(job["files"])), ("upload_metadata", 2, 1))
        self.assertEqual(job["files"][0]["index"], 0)
        self.assertEqual(job["flags"]["people_property"], "no")
        self.assertNotIn("path", json.dumps(job))

    def test_ok_result_is_stored_and_does_not_stop(self):
        q, jid = meta_queue(self.tmp)
        q.next_job()
        self.assertEqual(q.complete(jid, good_after())["status"], "ok")
        self.assertEqual(q.store.get_state("metadata_result:" + jid)["tiles_with_keywords"], 2)
        self.assertIsNone(q.stop_state())

    def test_any_failure_stops_the_queue(self):
        q, jid = meta_queue(self.tmp)
        q.next_job()
        res = q.complete(jid, good_after(ai_checked=False))
        self.assertEqual(res["reason"], "flags_not_set")
        self.assertIn("upload_metadata:flags_not_set", q.stop_state()["reason"])

    def test_switch_off_cancels_before_dispatch(self):
        q, jid = meta_queue(self.tmp)
        q.cfg = CFG
        self.assertEqual(q.next_job(), (None, "upload_metadata_off"))
        self.assertEqual(q.job(jid)["state"], "failed")


if __name__ == "__main__":
    unittest.main()
