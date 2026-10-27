"""Minimal MCP server over stdio (newline-delimited JSON-RPC 2.0). No third-party dependency."""
import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path

from . import __version__
from .app import App

STR = {"type": "string"}
INT = {"type": "integer"}
MAX_MCP_RESULT_CHARS = 1800
ALWAYS_COMPACT = {"stock_knowledge", "stock_report"}
SCAN_ITEM = {"type": "object", "required": ["keyword"], "additionalProperties": False, "properties": {
    "keyword": {"type": "string", "minLength": 1, "maxLength": 100},
    "media_type": {"enum": ["photo", "illustration", "vector", "video"]},
    "ai_filter": {"enum": ["all", "only_ai", "no_ai"]},
    "order": {"enum": ["relevance", "downloads", "creation", "undiscovered"]}}}


def obj(props, required=()):
    return {"type": "object", "properties": props, "required": list(required), "additionalProperties": False}


TOOLS = {
    "stock_status": ("Extension connection, queue and stop state.", obj({})),
    "stock_scan": ("Queue 1-20 structured searches. One supply rating needs three variants per phrase in one call: all/relevance, only_ai/relevance, all/downloads.",
                   obj({"requests": {"type": "array", "minItems": 1, "maxItems": 20, "items": SCAN_ITEM}}, ["requests"])),
    "stock_asset": ("Queue 1-20 asset page reads (keywords) by asset id.", obj({"asset_ids": {"type": "array", "minItems": 1, "maxItems": 20, "items": {"type": "integer", "minimum": 1}}}, ["asset_ids"])),
    "stock_contributor": ("Queue a contributor gallery read.", obj({"creator_id": {"type": "integer", "minimum": 1}}, ["creator_id"])),
    "stock_wait": ("Wait for jobs to finish (max 120 s). Returns compact state counts and unfinished or failed job ids.",
                   obj({"job_ids": {"type": "array", "minItems": 1, "maxItems": 20, "items": STR},
                        "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 120}}, ["job_ids"])),
    "stock_observation": ("Compact stored-observation summary with provenance; full rows are saved to an evidence file for a subagent.", obj({"obs_id": STR}, ["obs_id"])),
    "stock_import_trends": ("Import a Google Trends CSV exported by the user.", obj({"path": STR}, ["path"])),
    "stock_import_portfolio": ("Import the user's own portfolio CSV (downloads per asset, optional group = sub-niche).", obj({"path": STR}, ["path"])),
    "stock_import_groups": ("Import asset_id,group mapping (sub-niche labels) for the user's dashboard assets.", obj({"path": STR}, ["path"])),
    "stock_import_group_keywords": ("Import group,keyword[,media_type]: the search phrase standing for each of the user's groups (for calibration).", obj({"path": STR}, ["path"])),
    "stock_import_upload_dates": ("Import asset_id,uploaded_on (YYYY-MM-DD) from the user's own records; used to suggest a recency cut.", obj({"path": STR}, ["path"])),
    "stock_import_related": ("Import a Google Trends related-queries CSV (TOP/RISING) exported by the user, for a seed phrase.", obj({"path": STR, "seed": STR}, ["path", "seed"])),
    "stock_fetch_attention": ("Store a weekly attention series from a public API: wikipedia (page views of an article) or gdelt (news volume of a query). Measures interest, not stock-image demand. GDELT may answer 429: wait, do not loop.",
                              obj({"source": {"type": "string", "enum": ["wikipedia", "gdelt"]}, "query": STR, "term": STR, "weeks": INT}, ["source", "query"])),
    "stock_probe": ("Queue a read-only structure dump of one own-dashboard page (portfolio or uploads), stored raw for parser design.",
                    obj({"page": {"enum": ["portfolio", "uploads"]}}, ["page"])),
    "stock_outcomes_scan": ("Queue a read-only read of the Not accepted list (/en/uploads/rejected) with Adobe's cause per asset. One queue job makes one page load plus one paced read per asset.", obj({})),
    "stock_outcomes": ("Compact latest outcome counts; full per-asset evidence is saved to a file for a subagent.", obj({})),
    "stock_outcome_report": ("Accepted / quality-rejected / similar-rejected / pending counts, rates and 95% intervals per group (sub-niche or batch) and per content tag, from the latest stored outcomes and portfolio reads. groups_csv: group plus asset_id, name or name_contains; tags_csv: asset_id or name plus tag columns; submitted_folder lists submitted JPEGs so undecided ones count as pending; ledger_out writes the joined per-file CSV; qc_decisions (the batch's qc_decisions.json) adds tag local_qc to measure how many Adobe refusals the local QC caught. Read knowledge topic outcomes before drawing conclusions.",
                             obj({"groups_csv": STR, "tags_csv": STR, "submitted_folder": STR, "ledger_out": STR, "min_n": INT, "qc_decisions": STR})),
    "stock_portfolio": ("Queue a read-only read of the user's own contributor dashboard (downloads, earnings, per-asset downloads).", obj({})),
    "stock_knowledge": ("Adobe Stock know-how. Index is returned inline; full topics are saved to a file for a subagent to summarize.",
                        obj({"topic": STR})),
    "stock_upload_stage": ("Stage the verified files of a prepared plan (`prepare-plan` JSON, ready_for_upload true) on the Uploads page so they appear in the portal's New list. Waits up to ~110 s and returns a compact result. NEVER submits: the user clicks Submit. Refused unless the user turned upload_stage.enabled on. `only` stages a subset of file names.",
                           obj({"plan_path": STR, "only": {"type": "array", "items": STR}}, ["plan_path"])),
    "stock_upload_metadata": ("Apply the plan's CSV (title, keywords, category) to the files staged in the portal's New list, then set generative AI, people/property and include-in-submission for all of them and save. Waits up to ~110 s. NEVER submits: the user clicks Submit. Refused unless the user turned upload_metadata.enabled on.",
                              obj({"plan_path": STR}, ["plan_path"])),
    "stock_upload_result": ("Compact result of a stage or metadata job (counts, steps, files not seen). Use when stock_upload_stage or stock_upload_metadata said not finished.", obj({"job_id": STR}, ["job_id"])),
    "stock_metrics": ("Compute metrics and return a compact receipt; full metric evidence is saved to a file for a subagent.",
                      obj({"keywords": {"type": "array", "items": STR}, "media_type": STR, "as_of": STR}, ["keywords"])),
    "stock_report": ("Render the verified decision table to an evidence file and return only a compact receipt. Delegate reading the file; do not load it into the main context.",
                     obj({"keywords": {"type": "array", "items": STR}, "media_type": STR, "trends": {"type": "array", "items": STR},
                          "creators": {"type": "array", "items": INT}, "lead_as_of": STR, "as_of": STR,
                          "portfolio": {"type": "boolean"}, "calibration": {"type": "boolean"}, "own_keywords": {"type": "boolean"}, "related": {"type": "array", "items": STR},
                          "opportunities": {"type": "array", "items": obj({"keyword": STR, "term": STR}, ["keyword", "term"])}})),
    "stock_dashboard": ("Refresh metrics and return a localhost link to the visual dashboard (charts) for the user to open.", obj({"refresh": {"type": "boolean"}})),
    "stock_verify_doc": ("Fail a decision doc that has untraceable numbers or edited tables.", obj({"path": STR}, ["path"])),
    "stock_stop": ("Stop the queue now.", obj({})),
    "stock_restart_server": ("Restart this MCP server in place after returning. Preserves queued jobs and the stop state; does not resume the queue.", obj({})),
    "stock_resume": ("Resume only after the user explicitly instructs it in the current chat; also refused unless their config allows it. Never call automatically.", obj({})),
}


INSTRUCTIONS = ("Adobe Stock tools. Code makes every number; you choose keywords and decide. Never type a count, volume or sale from memory: "
                "say unmeasured. Tool results are compact by default; bulky evidence is saved as artifact_path. Never open that file in the main agent: delegate it to a fresh-context subagent and keep only its short decision summary. Never click Submit; stock_upload_stage only fills "
                "the portal New list and stock_upload_metadata only fills its fields; each works only when the user turned its enabled switch on. Stop on any stop state; only the user resumes. "
                "First time: call stock_knowledge(topic=index); delegate only the needed topic artifact.")


def _artifact(app, name, result):
    raw = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    sha = hashlib.sha256(raw.encode()).hexdigest()
    folder = Path(app.data_dir) / "artifacts" / "mcp"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}-{sha[:16]}.json"
    if not path.exists():
        path.write_text(raw, encoding="utf-8")
    return raw, sha, str(path.resolve())


def _summarize_result(app, name, result):
    """Keep operational facts inline; spill analysis payloads before they reach the lead context."""
    if name == "stock_knowledge" and "topics" in result:
        return {"start_with": result.get("start_with"),
                "topics": [topic["topic"] for topic in result["topics"]]}
    if name == "stock_wait" and "jobs" in result:
        states = Counter(j.get("state") for j in result["jobs"])
        pending = [j["job_id"] for j in result["jobs"] if j.get("state") in ("queued", "dispatched")]
        failed = [j["job_id"] for j in result["jobs"] if j.get("state") == "failed"]
        out = {
            "state": "stopped" if result.get("stop") else "pending" if pending else "failed" if failed else "completed",
            "job_count": len(result["jobs"]),
            "job_state_counts": dict(states),
            "stop": result.get("stop"),
        }
        if pending:
            out["unfinished_job_ids"] = pending
        if failed:
            out["failed_job_ids"] = failed
        observations = {j["job_id"]: j["obs_id"] for j in result["jobs"]
                        if j.get("state") == "done" and j.get("obs_id") and j.get("kind") != "search"}
        if observations:
            out["observations"] = observations
        for key in ("queue_reason", "next"):
            if result.get(key):
                out[key] = result[key]
        return out
    raw = json.dumps(result, ensure_ascii=False)
    force = name in ALWAYS_COMPACT or (name == "stock_observation" and "rows" in result)
    if not force and len(raw) <= MAX_MCP_RESULT_CHARS:
        return result

    raw, sha, path = _artifact(app, name, result)
    keep = ("kind", "ok", "status", "state", "stop", "reason", "error_type", "error", "next", "note", "job_id", "obs_id", "read_at",
            "topic", "render_sha256", "expected", "added", "before", "after", "count", "rows_count", "all_count",
            "submit_count", "tiles_with_keywords", "ai_checked", "include_checked", "fictional_checked", "ready_for_upload",
            "accepted_ids_read", "accepted_obs_id", "accepted_total", "outcomes_obs_id", "outcomes_read_at",
            "portfolio_obs_id", "portfolio_read_at")
    out = {k: result[k] for k in keep if k in result}

    if "observation" in result:
        out["observation"] = result["observation"]
    if "search_count" in result:
        out["search_count"] = result["search_count"]
    if "counts" in result:
        out["counts"] = result["counts"]
    if "overall" in result:
        out["overall"] = result["overall"]
    if "rows" in result:
        out["rows_count"] = len(result["rows"])
    if "accepted" in result:
        out["accepted_count"] = len(result["accepted"])
    if "accepted_asset_ids" in result:
        out["accepted_asset_count"] = len(result["accepted_asset_ids"])
    if "metrics" in result:
        out["metric_count"] = len(result["metrics"])
        out["metric_status_counts"] = dict(Counter(m.get("status") for m in result["metrics"]))
    if "metric_ids" in result:
        out["metric_count"] = len(result["metric_ids"])
    if "markdown" in result:
        out["markdown_chars"] = len(result["markdown"])
    if "by_group" in result:
        out["group_count"] = len(result["by_group"])
    if "by_tag" in result:
        out["tag_count"] = len(result["by_tag"])
    if "jobs" in result:
        states = Counter(j.get("state") for j in result["jobs"])
        pending = [j["job_id"] for j in result["jobs"] if j.get("state") in ("queued", "dispatched")]
        failed = [j["job_id"] for j in result["jobs"] if j.get("state") == "failed"]
        out["state"] = "stopped" if result.get("stop") else "pending" if pending else "failed" if failed else "completed"
        out["job_count"] = len(result["jobs"])
        out["job_state_counts"] = dict(states)
        if failed:
            out["failed_job_ids"] = failed
        if pending:
            out["unfinished_job_ids"] = pending
    if "asset" in result:
        asset = result["asset"]
        out["asset"] = {k: asset[k] for k in ("obs_id", "asset_id", "title", "keywords_shown", "keywords_total") if k in asset}
    for key in ("failures", "names_not_seen"):
        if key in result:
            out[f"{key}_count"] = len(result[key])
            if result[key]:
                out[f"{key}_preview"] = result[key][:3]

    out.update({"artifact_path": path, "artifact_sha256": sha, "artifact_chars": len(raw), "artifact_bytes": len(raw.encode())})
    return out


def _compact_result(app, name, result):
    """Apply one size boundary to every tool-result path, including wait and STOP."""
    out = _summarize_result(app, name, result)
    if len(json.dumps(out, ensure_ascii=False)) <= MAX_MCP_RESULT_CHARS:
        return out
    raw, sha, path = _artifact(app, name, result)
    receipt = {"artifact_path": path, "artifact_sha256": sha,
               "artifact_chars": len(raw), "artifact_bytes": len(raw.encode()), "summary_trimmed": True}
    for key in ("status", "state", "reason", "error", "next", "job_id", "obs_id"):
        if key in out:
            receipt[key] = str(out[key])[:160]
    if "stop" in out:
        stop = out["stop"]
        receipt["stop"] = {"reason": str(stop.get("reason", "unknown") if isinstance(stop, dict) else stop)[:160]} if stop else stop
    if len(json.dumps(receipt, ensure_ascii=False)) > MAX_MCP_RESULT_CHARS:
        # Retain the complete evidence path even for unusually deep data-directory names.
        receipt = {"artifact_path": path, "summary_trimmed": True,
                   "state": "stopped" if out.get("stop") else str(out.get("state", out.get("status", "stored")))[:80]}
        if out.get("stop"):
            receipt["stop"] = {"reason": "see evidence; do not resume automatically"}
    if len(json.dumps(receipt, ensure_ascii=False)) > MAX_MCP_RESULT_CHARS:
        raise ValueError("evidence path exceeds the MCP result limit; use a shorter data directory")
    return receipt


def handle(app, msg):
    mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
    if method == "initialize":
        return {"protocolVersion": params.get("protocolVersion", "2025-06-18"), "capabilities": {"tools": {}},
                "serverInfo": {"name": "adobe-stock-analytics", "version": __version__}, "instructions": INSTRUCTIONS}
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": [{"name": n, "description": d, "inputSchema": s} for n, (d, s) in TOOLS.items()]}
    if method == "tools/call":
        name, args = params.get("name"), params.get("arguments") or {}
        if name not in TOOLS:
            return {"content": [{"type": "text", "text": f"unknown tool {name}"}], "isError": True}
        allowed = set(TOOLS[name][1]["properties"])
        extra = set(args) - allowed
        try:
            if extra:
                raise ValueError(f"unexpected arguments: {sorted(extra)}")
            res = _compact_result(app, name, getattr(app, name)(**args))
            return {"content": [{"type": "text", "text": json.dumps(res, ensure_ascii=False)}], "isError": False}
        except Exception as e:  # tool errors are reported to the agent, not raised
            try:
                res = _compact_result(app, name, {"status": "error", "error_type": type(e).__name__, "error": str(e)})
            except ValueError:
                res = {"status": "error", "error": "MCP evidence path is too long; use a shorter data directory"}
            return {"content": [{"type": "text", "text": json.dumps(res, ensure_ascii=False)}], "isError": True}
    raise KeyError(method)


def serve(app, stdin=None, stdout=None):
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if "id" not in msg:  # notification
            continue
        try:
            out = {"jsonrpc": "2.0", "id": msg["id"], "result": handle(app, msg)}
        except KeyError:
            out = {"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32601, "message": "method not found"}}
        stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
        stdout.flush()
        if app.restart_requested:
            app.restart_requested = False
            if app.bridge:
                app.bridge.stop()
            original = getattr(sys, "orig_argv", None) or sys.argv
            os.execv(sys.executable, [sys.executable, *original[1:]])


def main():
    serve(App(start_bridge=True))
