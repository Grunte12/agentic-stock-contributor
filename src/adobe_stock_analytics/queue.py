"""Job queue with pacing, daily cap and a sticky stop state. Pacing values come from the config file only."""
import hashlib
import json
import random
import threading
import time
from datetime import datetime, timezone

from . import parsers, urls
from .config import canon, upload_metadata_cfg, upload_stage_cfg

SHAPE_REASONS = {"no_portfolio_shape", "no_count_text", "row_shape", "no_rows", "no_asset_id_or_title", "payload_not_object", "no_probe_shape", "no_outcomes_shape"}
DISPATCH_TIMEOUT = 180


class Queue:
    def __init__(self, store, cfg, clock=time.time, rng=random.random):
        self.store, self.cfg, self.clock, self.rng = store, cfg, clock, rng
        self.lock = threading.RLock()

    # --- state helpers -------------------------------------------------
    def _day(self):
        return datetime.fromtimestamp(self.clock(), timezone.utc).strftime("%Y-%m-%d")

    def stop_state(self):
        return self.store.get_state("stop")

    def stop(self, reason):
        self.store.set_state("stop", {"reason": reason, "at": self.store.now()})

    def resume(self):
        with self.lock:
            self.store.set_state("stop", None)
            self.store.set_state("failures", 0)

    def pages_today(self):
        d = self.store.get_state("day", {})
        return d.get("count", 0) if d.get("day") == self._day() else 0

    # --- enqueue ---------------------------------------------------------
    def enqueue(self, kind, params):
        with self.lock:
            if kind == "search":
                url = urls.build_search(params["keyword"], params.get("media_type", "photo"),
                                        params.get("ai_filter", "all"), params.get("order", "relevance"))
                params = {"keyword": " ".join(params["keyword"].split()), "media_type": params.get("media_type", "photo"),
                          "ai_filter": params.get("ai_filter", "all"), "order": params.get("order", "relevance")}
            elif kind == "asset":
                url, params = urls.build_asset(params["asset_id"]), {"asset_id": params["asset_id"]}
            elif kind == "portfolio":
                url, params = urls.build_portfolio(), {}
            elif kind == "probe":
                url, params = urls.build_probe(params["page"]), {"page": params["page"]}
            elif kind == "outcomes":
                url, params = urls.build_outcomes(), {}
            elif kind == "upload_stage":
                url, params = urls.build_probe("uploads"), {"package_digest": params["package_digest"], "files": params["files"]}
            elif kind == "upload_metadata":
                url = urls.build_probe("uploads")
                params = {"package_digest": params["package_digest"], "files": [params["csv"]], "count": params["count"], "flags": params["flags"]}
            elif kind == "contributor":
                url, params = urls.build_contributor(params["creator_id"]), {"creator_id": params["creator_id"]}
            else:
                raise urls.UrlError(f"unknown job kind {kind!r}")
            dup = self.store.db.execute(
                "SELECT job_id FROM job WHERE kind=? AND params=? AND state IN ('queued','dispatched')",
                (kind, canon(params))).fetchone()
            if dup:
                return dup["job_id"]
            n = self.store.db.execute("SELECT count(*) c FROM job").fetchone()["c"]
            jid = "job-" + hashlib.sha256(f"{kind}|{canon(params)}|{n}".encode()).hexdigest()[:12]
            self.store.db.execute("INSERT INTO job VALUES(?,?,?,?,?,?,?,?)",
                                  (jid, kind, canon(params), url, "queued", self.store.now(), None, None))
            return jid

    def job(self, job_id):
        r = self.store.db.execute("SELECT * FROM job WHERE job_id=?", (job_id,)).fetchone()
        return dict(r) if r else None

    # --- dispatch ----------------------------------------------------------
    def next_job(self):
        """Returns (job_or_None, reason). The extension only ever receives allowlisted URLs."""
        with self.lock:
            stop = self.stop_state()
            if stop:
                return None, f"stopped:{stop['reason']}"
            now = self.clock()
            busy = self.store.db.execute("SELECT job_id, dispatched_at FROM job WHERE state='dispatched'").fetchone()
            if busy:
                if now - self.store.get_state("dispatch_ts", 0) < DISPATCH_TIMEOUT:
                    return None, "busy"
                self.store.db.execute("UPDATE job SET state='failed' WHERE job_id=?", (busy["job_id"],))
                self.stop("dispatch_timeout")
                return None, "stopped:dispatch_timeout"
            if self.pages_today() >= self.cfg["pacing"]["daily_cap"]:
                return None, "daily_cap"
            wait = self.store.get_state("next_allowed", 0) - now
            if wait > 0:
                return None, f"pacing:{int(wait) + 1}"
            r = self.store.db.execute("SELECT * FROM job WHERE state='queued' ORDER BY created_at, rowid LIMIT 1").fetchone()
            if not r:
                return None, "empty"
            if not urls.is_allowed(r["url"]):
                self.store.db.execute("UPDATE job SET state='failed' WHERE job_id=?", (r["job_id"],))
                self.stop("url_not_allowlisted")
                return None, "stopped:url_not_allowlisted"
            if r["kind"] == "upload_stage" and upload_stage_cfg(self.cfg).get("enabled") is not True:
                self.store.db.execute("UPDATE job SET state='failed' WHERE job_id=?", (r["job_id"],))
                return None, "upload_stage_off"
            if r["kind"] == "upload_metadata" and upload_metadata_cfg(self.cfg).get("enabled") is not True:
                self.store.db.execute("UPDATE job SET state='failed' WHERE job_id=?", (r["job_id"],))
                return None, "upload_metadata_off"
            p = self.cfg["pacing"]
            self.store.set_state("next_allowed", now + p["min_gap_seconds"] + self.rng() * p["jitter_seconds"])
            self.store.set_state("dispatch_ts", now)
            day = self._day()
            self.store.set_state("day", {"day": day, "count": self.pages_today() + 1})
            self.store.db.execute("UPDATE job SET state='dispatched', dispatched_at=? WHERE job_id=?",
                                  (self.store.now(), r["job_id"]))
            job = {"job_id": r["job_id"], "kind": r["kind"], "url": r["url"]}
            if r["kind"] == "upload_stage":
                files = json.loads(r["params"])["files"]
                job["files"] = [{"index": i, "name": f["name"], "size": f["size"], "sha256": f["sha256"]} for i, f in enumerate(files)]
                job["stage_timeout_seconds"] = upload_stage_cfg(self.cfg)["stage_timeout_seconds"]
                job["require_empty"] = json.loads(r["params"]).get("require_empty") is True
            if r["kind"] == "upload_metadata":
                prm = json.loads(r["params"])
                job["files"] = [{"index": 0, "name": prm["files"][0]["name"], "size": prm["files"][0]["size"], "sha256": prm["files"][0]["sha256"]}]
                job["count"], job["flags"] = prm["count"], prm["flags"]
                job["step_timeout_seconds"] = upload_metadata_cfg(self.cfg)["step_timeout_seconds"]
            return job, "dispatched"

    def stage_file(self, job_id, index):
        """The file record for one index of a dispatched upload_stage job, or None. Only these files can leave the bridge."""
        j = self.job(job_id)
        if not j or j["state"] != "dispatched":
            return None
        if j["kind"] == "upload_stage":
            on = upload_stage_cfg(self.cfg).get("enabled") is True
        elif j["kind"] == "upload_metadata":
            on = upload_metadata_cfg(self.cfg).get("enabled") is True
        else:
            on = False
        if not on:
            return None
        files = json.loads(j["params"])["files"]
        return files[index] if isinstance(index, int) and 0 <= index < len(files) else None

    # --- completion -----------------------------------------------------------
    def complete(self, job_id, payload):
        with self.lock:
            j = self.job(job_id)
            if not j or j["state"] != "dispatched":
                return {"ok": False, "error": "job_not_dispatched"}
            params = json.loads(j["params"])
            if j["kind"] == "search":
                exp = urls.expected_filters(params["keyword"], params["media_type"], params["ai_filter"], params["order"])
                parsed = parsers.parse_search(payload, exp)
            elif j["kind"] == "asset":
                parsed = parsers.parse_asset(payload)
                if parsed["status"] == "ok" and parsed["asset_id"] != params["asset_id"]:
                    parsed = {"status": "unknown", "reason": "asset_id_mismatch", "parser_version": parsers.PARSER_VERSION}
            elif j["kind"] == "portfolio":
                parsed = parsers.parse_portfolio(payload)
            elif j["kind"] == "probe":
                parsed = parsers.parse_probe(payload)
            elif j["kind"] == "outcomes":
                parsed = parsers.parse_outcomes(payload)
            elif j["kind"] == "upload_stage":
                parsed = parsers.parse_upload_stage(payload, [f["name"] for f in params["files"]])
            elif j["kind"] == "upload_metadata":
                parsed = parsers.parse_upload_metadata(payload, params["count"], params.get("flags"))
            else:
                parsed = parsers.parse_contributor(payload)
            obs_id = self.store.add_observation(j["kind"], j["url"], params, payload, parsed)
            self.store.db.execute("UPDATE job SET state=?, obs_id=? WHERE job_id=?",
                                  ("done" if parsed["status"] == "ok" else "failed", obs_id, job_id))
            if j["kind"] == "upload_stage":
                self.store.set_state("stage_result:" + job_id, {k: v for k, v in parsed.items() if k != "parser_version"})
                if parsed["status"] != "ok":  # a partial or unverified stage must not be retried blindly: it could add files twice
                    self.stop("upload_stage:" + str(parsed["reason"]))
                else:
                    staged = self.store.get_state("staged", {})
                    staged.update({f["sha256"]: {"name": f["name"], "job_id": job_id, "at": self.store.now()} for f in params["files"]})
                    self.store.set_state("staged", staged)
                    self.store.set_state("failures", 0)
            elif j["kind"] == "upload_metadata":
                self.store.set_state("metadata_result:" + job_id, {k: v for k, v in parsed.items() if k != "parser_version"})
                if parsed["status"] != "ok":  # stop and let the user look: the portal may hold a half-applied state
                    self.stop("upload_metadata:" + str(parsed["reason"]))
                else:
                    self.store.set_state("failures", 0)
            elif parsed["status"] == "ok":
                self.store.set_state("failures", 0)
            elif parsed["status"] == "blocked":
                self.stop(parsed["reason"])
            elif parsed["reason"] in SHAPE_REASONS:
                self.stop("unknown_page_shape:" + parsed["reason"])
            else:
                f = self.store.get_state("failures", 0) + 1
                self.store.set_state("failures", f)
                if f > self.cfg["stop"]["max_consecutive_parse_failures"]:
                    self.stop("repeated_parse_failures")
            return {"ok": True, "obs_id": obs_id, "status": parsed["status"], "reason": parsed.get("reason")}

    def status(self):
        c = {r["state"]: r["c"] for r in self.store.db.execute("SELECT state, count(*) c FROM job GROUP BY state")}
        return {"stop": self.stop_state(), "jobs": c, "pages_today": self.pages_today(),
                "daily_cap": self.cfg["pacing"]["daily_cap"]}
