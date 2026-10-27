"""Tool implementations shared by the MCP server and the CLI. Outputs carry obs_id / metric_id for every number."""
import json
import os
import time
from pathlib import Path

from . import calibration, dashboard, metrics as M, portfolio, recency, related, report as R, trends, upload_metadata, upload_stage, urls, verify
from .bridge import Bridge, load_token
from .config import DEFAULT_DATA, ROOT, load_config, load_live_config
from .queue import Queue
from .store import Store, utcnow

MAX_SCANS = 20


class App:
    def __init__(self, data_dir=None, cfg=None, start_bridge=False, clock=time.time):
        self.cfg = cfg or {**load_live_config(), "_live_config": True}
        self.data_dir = Path(data_dir or DEFAULT_DATA)
        self.store = Store(self.data_dir)
        self.queue = Queue(self.store, self.cfg, clock=clock)
        self.bridge = None
        self.bridge_error = None
        self.want_bridge = start_bridge
        self.server_started_at = utcnow()
        self.server_instance_id = f"{os.getpid()}-{time.time_ns()}"
        self.restart_requested = False
        self.ensure_bridge()

    def ensure_bridge(self):
        """Start the extension bridge; retried on each status call if another process held the port."""
        if not self.want_bridge or self.bridge:
            return
        b = self.cfg["bridge"]
        try:
            self.bridge = Bridge(self.queue, load_token(self.data_dir), b["host"], b["port"],
                           dashboard=lambda: dashboard.render(self.store, self.cfg, utcnow(), live=True))
            self.bridge.start()
            self.bridge_error = None
        except OSError as e:  # another process owns the port; tools still work on stored data
            self.bridge_error = f"{type(e).__name__}: {e}"

    # -- tools ---------------------------------------------------------
    def stock_status(self):
        self.ensure_bridge()
        return {"kind": "operational", "bridge_connected": bool(self.bridge and self.bridge.connected()),
                "bridge_error": self.bridge_error,
                "extension_version": self.bridge.ext_version if self.bridge else None,
                "server_pid": os.getpid(), "server_started_at": self.server_started_at,
                "server_instance_id": self.server_instance_id,
                **self.queue.status()}

    def stock_scan(self, requests):
        if not isinstance(requests, list) or not requests or len(requests) > MAX_SCANS:
            raise ValueError(f"requests must be a list of 1 to {MAX_SCANS} items")
        ids = [self.queue.enqueue("search", r) for r in requests]
        return {"job_ids": ids}

    def stock_asset(self, asset_ids):
        if not isinstance(asset_ids, list) or not asset_ids or len(asset_ids) > MAX_SCANS:
            raise ValueError(f"asset_ids must be a list of 1 to {MAX_SCANS} integers")
        return {"job_ids": [self.queue.enqueue("asset", {"asset_id": a}) for a in asset_ids]}

    def stock_contributor(self, creator_id):
        return {"job_ids": [self.queue.enqueue("contributor", {"creator_id": creator_id})]}

    def stock_wait(self, job_ids, timeout_seconds=60):
        end = time.time() + min(max(int(timeout_seconds), 1), 120)
        while True:
            jobs = [self.queue.job(j) for j in job_ids]
            if any(j is None for j in jobs):
                raise ValueError("unknown job id")
            pending = [j for j in jobs if j["state"] in ("queued", "dispatched")]
            if not pending or self.queue.stop_state() or time.time() >= end:
                stop = self.queue.stop_state()
                reason = None
                next_action = None
                if pending and stop:
                    reason = "stopped:" + str(stop["reason"])
                    next_action = "report the stop; do not retry or resume without the user's explicit instruction"
                elif pending and self.queue.pages_today() >= self.cfg["pacing"]["daily_cap"]:
                    reason = "daily_cap"
                    next_action = "keep these unfinished job ids; wait for the next UTC day and do not scan again"
                elif pending and any(j["state"] == "dispatched" for j in pending):
                    reason = "dispatched"
                    next_action = "call stock_wait again with only these unfinished job ids"
                elif pending:
                    wait = self.store.get_state("next_allowed", 0) - self.queue.clock()
                    if wait > 0:
                        reason = f"pacing:{int(wait) + 1}"
                        next_action = "call stock_wait again with only these unfinished job ids"
                    elif not self.bridge or not self.bridge.connected():
                        reason = "extension_disconnected"
                        next_action = "reconnect the extension; keep these job ids and do not scan again"
                    else:
                        reason = "queued"
                        next_action = "call stock_wait again with only these unfinished job ids"
                return {"jobs": [{"job_id": j["job_id"], "kind": j["kind"], "state": j["state"], "obs_id": j["obs_id"]}
                                 for j in jobs], "stop": stop, "queue_reason": reason, "next": next_action}
            time.sleep(1)

    def stock_observation(self, obs_id):
        o = self.store.observation(obs_id)
        if not o:
            raise ValueError("unknown obs_id")
        out = {"observation": {k: o[k] for k in ("obs_id", "kind", "url", "read_at", "status", "status_reason", "parser_version")}}
        sc = self.store.db.execute("SELECT * FROM search_count WHERE obs_id=?", (obs_id,)).fetchone()
        if sc:
            out["search_count"] = {"obs_id": obs_id, "results": sc["results"], "results_text": sc["results_text"]}
        rows = self.store.rows(obs_id)
        if rows:
            out["rows"] = rows
        det = self.store.db.execute("SELECT * FROM asset_detail WHERE obs_id=?", (obs_id,)).fetchone()
        if det:
            out["asset"] = {"obs_id": obs_id, "asset_id": det["asset_id"], "title": det["title"],
                            "keywords": json.loads(det["keywords"]), "keywords_shown": det["keywords_shown"],
                            "keywords_total": det["keywords_total"]}
        return out

    def stock_import_trends(self, path):
        p = Path(path)
        if not p.is_file():
            raise ValueError("file not found")
        return trends.import_trends(self.store, p)

    def stock_import_portfolio(self, path):
        p = Path(path)
        if not p.is_file():
            raise ValueError("file not found")
        return portfolio.import_portfolio(self.store, p)

    def stock_import_groups(self, path):
        p = Path(path)
        if not p.is_file():
            raise ValueError("file not found")
        return portfolio.import_groups(self.store, p)

    def stock_import_group_keywords(self, path):
        p = Path(path)
        if not p.is_file():
            raise ValueError("file not found")
        return calibration.import_group_keywords(self.store, p)

    def stock_import_upload_dates(self, path):
        p = Path(path)
        if not p.is_file():
            raise ValueError("file not found")
        return recency.import_upload_dates(self.store, p)

    def stock_import_related(self, path, seed):
        p = Path(path)
        if not p.is_file():
            raise ValueError("file not found")
        return related.import_related(self.store, p, seed)

    def stock_fetch_attention(self, source, query, term=None, weeks=20):
        """Store a weekly attention series from a public API (read-only, no login)."""
        if source == "wikipedia":
            from . import wikipedia
            return wikipedia.fetch(self.store, query, term, "en", weeks)
        if source == "gdelt":
            from . import gdelt
            return gdelt.fetch(self.store, query, term, weeks)
        raise ValueError("source must be wikipedia or gdelt")

    def stock_portfolio(self):
        return {"job_ids": [self.queue.enqueue("portfolio", {})]}

    def stock_probe(self, page):
        return {"job_ids": [self.queue.enqueue("probe", {"page": page})]}

    def stock_outcomes_scan(self):
        return {"job_ids": [self.queue.enqueue("outcomes", {})]}

    def stock_outcomes(self):
        """Latest stored Not accepted list with Adobe's cause per asset, plus the accepted portfolio asset ids."""
        o = self.store.latest_outcomes()
        if not o:
            raise ValueError("no outcomes observation yet: run stock_outcomes_scan first")
        counts = {}
        for r in o["rows"]:
            counts[r["outcome_class"]] = counts.get(r["outcome_class"], 0) + 1
        pf = self.store.db.execute(
            "SELECT p.obs_id, o.read_at FROM pf_overview p JOIN observation o USING(obs_id) WHERE o.status='ok' "
            "ORDER BY o.read_at DESC LIMIT 1").fetchone()
        oid = pf["obs_id"] if pf else None
        accepted = [dict(r) for r in self.store.db.execute(
            "SELECT asset_id, original_name, created_ms FROM pf_name WHERE obs_id=? ORDER BY asset_id", (oid,))] if pf else []
        ids = [r["asset_id"] for r in self.store.db.execute("SELECT asset_id FROM pf_asset WHERE obs_id=?", (oid,))] if pf else []
        total = self.store.db.execute("SELECT all_count FROM pf_overview WHERE obs_id=?", (oid,)).fetchone() if pf else None
        all_ids = sorted(set(ids) | {a["asset_id"] for a in accepted})
        return {**o, "counts": counts, "accepted": accepted, "accepted_asset_ids": all_ids, "accepted_ids_read": len(all_ids),
                "accepted_obs_id": oid, "accepted_total": total["all_count"] if total else None,
                "note": "accepted_asset_ids covers every portfolio page the read reached (extension 0.10.0 or later); compare accepted_ids_read "
                        "with accepted_total. Names (accepted) exist for page 1 only; for later pages match by asset id."}

    def stock_outcome_report(self, groups_csv=None, tags_csv=None, submitted_folder=None, ledger_out=None, min_n=5, qc_decisions=None):
        """Accept and reject counts and rates per group (sub-niche or batch) and per content tag, from stored portal reads."""
        from . import outcomes
        rep = outcomes.build(self.store, groups_csv, tags_csv, submitted_folder, min_n, qc_decisions)
        if ledger_out:
            rep["ledger"] = outcomes.write_ledger(rep, Path(ledger_out).expanduser())
        rep["rows_count"] = len(rep.pop("rows"))
        return rep

    def stock_knowledge(self, topic="index"):
        """Adobe Stock know-how (mindset, niche method, workflow, QC, metadata, upload). `index` lists topics; read only what you need."""
        docs = {f.stem: f for f in sorted((ROOT / "knowledge").glob("*.md"))}
        def split(f):
            t = f.read_text(encoding="utf-8")
            if t.startswith("---\n") and "\n---\n" in t[4:]:
                head, body = t[4:].split("\n---\n", 1)
                return next((l.split(":", 1)[1].strip() for l in head.splitlines() if l.startswith("description:")), ""), body.lstrip("\n")
            return "", t
        if topic == "index":
            return {"start_with": "mindset", "topics": [{"topic": k, "read_when": split(f)[0]} for k, f in docs.items()]}
        if topic not in docs:
            raise ValueError(f"unknown topic {topic!r}; one of {sorted(docs)}")
        return {"topic": topic, "markdown": split(docs[topic])[1]}

    def stock_upload_stage(self, plan_path, only=None, with_metadata=False):
        """Stage the files of a prepared, ready_for_upload plan on the Uploads page (portal New list). Never submits."""
        if with_metadata:
            if only is not None:
                raise ValueError("combined staging requires the complete wave; recover subsets with separate staging")
            return self.stock_upload_ready(plan_path)
        return self._upload_stage(plan_path, only)

    def _upload_stage(self, plan_path, only=None, require_empty=False):
        plan = upload_stage.load_plan(plan_path, self.cfg, only)
        staged = self.store.get_state("staged", {})
        dup = sorted(f["name"] for f in plan["files"] if f["sha256"] in staged)
        if dup:
            raise ValueError(f"already staged: {dup}. Stage only the rest with only=[...]; if the user cleared the New list, they run `reset-staged`")
        jid = self.queue.enqueue("upload_stage", {"package_digest": plan["package_digest"], "files": plan["files"],
                                                  "require_empty": require_empty})
        end = time.time() + 110
        while time.time() < end:
            j = self.queue.job(jid)
            if j["state"] not in ("queued", "dispatched") or self.queue.stop_state():
                break
            time.sleep(1)
        return self.stock_upload_result(jid)

    def stock_upload_metadata(self, plan_path):
        """Apply the plan's CSV (title, keywords, category) to the staged files and set generative AI, people/property and
        include-in-submission for all of them. Never submits. Refused unless the user turned upload_metadata.enabled on."""
        plan = upload_metadata.load_metadata_plan(plan_path, self.cfg)
        jid = self.queue.enqueue("upload_metadata", {"package_digest": plan["package_digest"], "csv": plan["csv"],
                                                     "count": len(plan["names"]), "flags": plan["flags"]})
        end = time.time() + 110
        while time.time() < end:
            j = self.queue.job(jid)
            if j["state"] not in ("queued", "dispatched") or self.queue.stop_state():
                break
            time.sleep(1)
        return self.stock_upload_result(jid)

    def stock_upload_ready(self, plan_path):
        """Preflight both operations; stage a complete wave into empty New, then set metadata. Never submits."""
        plan = upload_metadata.load_metadata_plan(plan_path, self.cfg)
        staged = self._upload_stage(plan_path, require_empty=True)
        if staged.get("status") != "ok" or staged.get("stop"):
            return {**staged, "phase": "stage"}
        if staged.get("before") != 0 or staged.get("after") != len(plan["names"]):
            self.queue.stop("upload_stage:unexpected_new_contents")
            return {**staged, "phase": "stage", "status": "unknown", "reason": "unexpected_new_contents",
                    "stop": self.queue.stop_state()}
        metadata = self.stock_upload_metadata(plan_path)
        if metadata.get("status") != "ok" or metadata.get("stop"):
            return {**metadata, "phase": "metadata", "stage_job_id": staged.get("job_id")}
        return {"phase": "complete", "status": "ok", "stop": None,
                "stage_job_id": staged.get("job_id"), "metadata_job_id": metadata.get("job_id"),
                "expected": staged.get("expected"), "added": staged.get("added"),
                "before": staged.get("before"), "after": metadata.get("all_count"),
                "submit_count": metadata.get("submit_count"),
                "tiles_with_keywords": metadata.get("tiles_with_keywords"),
                "ai_checked": metadata.get("ai_checked"), "include_checked": metadata.get("include_checked"),
                "fictional_checked": metadata.get("fictional_checked"),
                "next": "metadata and flags are verified; files remain in New and the user clicks Submit"}

    def stock_upload_result(self, job_id):
        """Compact result of a stage job: how many files the portal's All (N) count rose by, and what is missing."""
        j = self.queue.job(job_id)
        if not j or j["kind"] not in ("upload_stage", "upload_metadata"):
            raise ValueError("unknown upload_stage or upload_metadata job id")
        meta = j["kind"] == "upload_metadata"
        out = {"job_id": job_id, "state": j["state"], "stop": self.queue.stop_state(), "obs_id": j["obs_id"]}
        r = self.store.get_state(("metadata_result:" if meta else "stage_result:") + job_id)
        if r:
            out.update(r)
            ok_next = "metadata and flags are set and saved, files are counted by Submit, not submitted: the user clicks Submit" if meta else "files are in the New list, not submitted: the user clicks Submit"
            out["next"] = ok_next if r["status"] == "ok" else "do not retry blindly: look at the portal New list by hand, then the user runs `resume`"
        else:
            out["note"] = "not finished: the extension has not reported (check stock_status bridge_connected); call stock_upload_result again"
        return out

    def stock_metrics(self, keywords, media_type="photo", as_of=None):
        ms = []
        for k in keywords:
            ms += M.compute_keyword(self.store, self.cfg, k, media_type, as_of=as_of)
        return {"metrics": ms}

    def stock_report(self, keywords=(), media_type="photo", trends=(), creators=(), lead_as_of=None, as_of=None, portfolio=False, opportunities=(), calibration=False, own_keywords=False, related=()):
        kws = [{"keyword": k, "media_type": media_type} for k in keywords]
        r = R.report(self.store, self.cfg, kws, trends, creators, as_of=as_of, lead_as_of=lead_as_of, portfolio=portfolio,
                     opportunities=[{**o, "media_type": media_type} for o in opportunities], calibration=calibration, own_keywords=own_keywords, related=related)
        return {"markdown": r["markdown"], "render_sha256": r["render_sha256"],
                "metric_ids": [m["metric_id"] for m in r["metrics"]]}

    def stock_dashboard(self, refresh=True):
        """Recompute metrics from stored observations and return the localhost link to the dashboard."""
        self.ensure_bridge()
        if not self.bridge:
            raise RuntimeError(f"dashboard needs the bridge in this server process: {self.bridge_error or 'not started'}")
        done = dashboard.refresh(self.store, self.cfg, utcnow()[:10]) if refresh else None
        return {"url": self.bridge.dashboard_url(), "refreshed": done,
                "note": "Open the link in your browser. It is read-only, works only on this computer, and reloads itself every minute."}

    def stock_verify_doc(self, path):
        return verify.verify_doc(self.store, Path(path).read_text(encoding="utf-8"))

    def stock_stop(self):
        self.queue.stop("agent_requested")
        return {"stop": self.queue.stop_state()}

    def stock_restart_server(self):
        """Ask the stdio loop to exec itself after returning this tool result."""
        self.restart_requested = True
        return {"restart_requested": True, "stop": self.queue.stop_state(),
                "note": "The server restarts in place; queued jobs and the stop state are preserved."}

    def stock_resume(self):
        if not self.cfg["stop"]["allow_agent_resume"]:
            raise PermissionError("resume is user-only: run `adobe-stock-analytics resume` in a terminal")
        self.queue.resume()
        return {"stop": self.queue.stop_state()}
