"""Minimal MCP server over stdio (newline-delimited JSON-RPC 2.0). No third-party dependency."""
import json
import sys

from .app import App

STR = {"type": "string"}
INT = {"type": "integer"}
SCAN_ITEM = {"type": "object", "required": ["keyword"], "additionalProperties": False, "properties": {
    "keyword": STR,
    "media_type": {"enum": ["photo", "illustration", "vector", "video"]},
    "ai_filter": {"enum": ["all", "only_ai", "no_ai"]},
    "order": {"enum": ["relevance", "downloads", "creation", "undiscovered"]}}}


def obj(props, required=()):
    return {"type": "object", "properties": props, "required": list(required), "additionalProperties": False}


TOOLS = {
    "stock_status": ("Extension connection, queue and stop state.", obj({})),
    "stock_scan": ("Queue Adobe Stock searches (structured params, no URLs). Returns job ids; paced by config.",
                   obj({"requests": {"type": "array", "items": SCAN_ITEM}}, ["requests"])),
    "stock_asset": ("Queue asset page reads (keywords) by asset id.", obj({"asset_ids": {"type": "array", "items": INT}}, ["asset_ids"])),
    "stock_contributor": ("Queue a contributor gallery read.", obj({"creator_id": INT}, ["creator_id"])),
    "stock_wait": ("Wait for jobs to finish (max 120 s). Returns states and obs ids.",
                   obj({"job_ids": {"type": "array", "items": STR}, "timeout_seconds": INT}, ["job_ids"])),
    "stock_observation": ("Stored observation by obs_id: counts, rows or asset keywords, with provenance.", obj({"obs_id": STR}, ["obs_id"])),
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
    "stock_outcomes": ("Latest stored Not accepted list: asset id, original name, Adobe cause (quality / similar / other), plus accepted asset ids from the latest portfolio read.", obj({})),
    "stock_outcome_report": ("Accepted / quality-rejected / similar-rejected / pending counts, rates and 95% intervals per group (sub-niche or batch) and per content tag, from the latest stored outcomes and portfolio reads. groups_csv: group plus asset_id, name or name_contains; tags_csv: asset_id or name plus tag columns; submitted_folder lists submitted JPEGs so undecided ones count as pending; ledger_out writes the joined per-file CSV; qc_decisions (the batch's qc_decisions.json) adds tag local_qc to measure how many Adobe refusals the local QC caught. Read knowledge topic outcomes before drawing conclusions.",
                             obj({"groups_csv": STR, "tags_csv": STR, "submitted_folder": STR, "ledger_out": STR, "min_n": INT, "qc_decisions": STR})),
    "stock_portfolio": ("Queue a read-only read of the user's own contributor dashboard (downloads, earnings, per-asset downloads).", obj({})),
    "stock_knowledge": ("Adobe Stock know-how as markdown: mindset, niche method, production workflow, QC, metadata, upload and portal flow, community evidence. topic=index lists them with when to read each; read mindset first, then only what the task needs.",
                        obj({"topic": STR})),
    "stock_upload_stage": ("Stage the verified files of a prepared plan (`prepare-plan` JSON, ready_for_upload true) on the Uploads page so they appear in the portal's New list. Waits up to ~110 s and returns a compact result. NEVER submits: the user clicks Submit. Refused unless the user turned upload_stage.enabled on. `only` stages a subset of file names.",
                           obj({"plan_path": STR, "only": {"type": "array", "items": STR}}, ["plan_path"])),
    "stock_upload_metadata": ("Apply the plan's CSV (title, keywords, category) to the files staged in the portal's New list, then set generative AI, people/property and include-in-submission for all of them and save. Waits up to ~110 s. NEVER submits: the user clicks Submit. Refused unless the user turned upload_metadata.enabled on.",
                              obj({"plan_path": STR}, ["plan_path"])),
    "stock_upload_result": ("Compact result of a stage or metadata job (counts, steps, files not seen). Use when stock_upload_stage or stock_upload_metadata said not finished.", obj({"job_id": STR}, ["job_id"])),
    "stock_metrics": ("Compute and return metrics (with metric ids) for keywords from stored observations.",
                      obj({"keywords": {"type": "array", "items": STR}, "media_type": STR, "as_of": STR}, ["keywords"])),
    "stock_report": ("Render the decision table from metrics. Paste it unchanged; cite numbers as [m:<metric_id>].",
                     obj({"keywords": {"type": "array", "items": STR}, "media_type": STR, "trends": {"type": "array", "items": STR},
                          "creators": {"type": "array", "items": INT}, "lead_as_of": STR, "as_of": STR,
                          "portfolio": {"type": "boolean"}, "calibration": {"type": "boolean"}, "own_keywords": {"type": "boolean"}, "related": {"type": "array", "items": STR},
                          "opportunities": {"type": "array", "items": obj({"keyword": STR, "term": STR}, ["keyword", "term"])}})),
    "stock_dashboard": ("Refresh metrics and return a localhost link to the visual dashboard (charts) for the user to open.", obj({"refresh": {"type": "boolean"}})),
    "stock_verify_doc": ("Fail a decision doc that has untraceable numbers or edited tables.", obj({"path": STR}, ["path"])),
    "stock_stop": ("Stop the queue now.", obj({})),
    "stock_resume": ("Resume the queue (refused unless the user config allows it).", obj({})),
}


INSTRUCTIONS = ("Adobe Stock tools. Code makes every number; you choose keywords, read tables and decide. Never type a count, volume or sale from memory: "
                "say unmeasured. Paste stock_report tables unchanged and cite numbers as [m:<metric_id>]. Never click Submit; stock_upload_stage only fills "
                "the portal New list and stock_upload_metadata only fills its fields; each works only when the user turned its enabled switch on. Stop on any stop state; only the user resumes. "
                "First time: call stock_knowledge (topic index), read mindset, then only the topic the task needs.")


def handle(app, msg):
    mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
    if method == "initialize":
        return {"protocolVersion": params.get("protocolVersion", "2025-06-18"), "capabilities": {"tools": {}},
                "serverInfo": {"name": "adobe-stock-analytics", "version": "0.1.0"}, "instructions": INSTRUCTIONS}
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
            res = getattr(app, name)(**args)
            return {"content": [{"type": "text", "text": json.dumps(res, ensure_ascii=False)}], "isError": False}
        except Exception as e:  # tool errors are reported to the agent, not raised
            return {"content": [{"type": "text", "text": f"{type(e).__name__}: {e}"}], "isError": True}
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


def main():
    serve(App(start_bridge=True))
