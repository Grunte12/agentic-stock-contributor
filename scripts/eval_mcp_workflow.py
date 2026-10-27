#!/usr/bin/env python3
"""Local-only MCP workflow benchmark and blind-plan scorer."""
import argparse
import json
import math
import sys
import tempfile
import time
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from adobe_stock_analytics import mcp_server, parsers, urls
from adobe_stock_analytics.app import App
from adobe_stock_analytics.config import load_config

VARIANTS = [
    {"keyword": "matcha latte", "media_type": "photo", "ai_filter": "all", "order": "relevance"},
    {"keyword": "matcha latte", "media_type": "photo", "ai_filter": "only_ai", "order": "relevance"},
    {"keyword": "matcha latte", "media_type": "photo", "ai_filter": "all", "order": "downloads"},
]
CASES = ["supply_one_phrase", "captcha_stop", "disconnected", "daily_cap", "outcomes",
         "stage_not_authorized", "stage_authorized", "partial_stage", "knowledge_artifact", "submit_request"]


def rpc(app, method, params=None):
    return mcp_server.handle(app, {"id": 1, "method": method, "params": params or {}})


def tool(app, name, arguments=None):
    return rpc(app, "tools/call", {"name": name, "arguments": arguments or {}})


def payload(response):
    if "content" in response:
        return response["content"][0]["text"]
    return json.dumps(response, ensure_ascii=False, sort_keys=True)


def result(response):
    return json.loads(payload(response))


def seed_search_fixtures(app):
    fixture_dir = ROOT / "tests" / "fixtures" / "intel"
    observations = []
    for filename, request in zip(("search_matcha_p0_1.json", "search_matcha_p0_3.json", "search_matcha_p0_2.json"), VARIANTS):
        raw = json.loads((fixture_dir / filename).read_text(encoding="utf-8"))
        parsed = parsers.parse_search(raw, urls.expected_filters(request["keyword"], request["media_type"],
                                                                 request["ai_filter"], request["order"]))
        obs_id = app.store.add_observation("search", urls.build_search(request["keyword"], request["media_type"],
                                        request["ai_filter"], request["order"]), request, raw, parsed)
        observations.append(obs_id)
    return observations


def make_app(data_dir):
    return App(data_dir=data_dir, cfg=load_config(), start_bridge=False)


def benchmark(name, app):
    """Run a fixed local workflow. Return a receipt payload and acceptance result."""
    started = time.perf_counter()
    retries = 0
    errors = 0
    passed = False
    details = {}
    if name == "status":
        response = tool(app, "stock_status")
        body = result(response)
        passed = not response.get("isError") and body["kind"] == "operational" and not body["bridge_connected"]
    elif name == "tools_list":
        response = rpc(app, "tools/list")
        names = {item["name"] for item in response["tools"]}
        passed = "stock_status" in names and "stock_scan" in names and "stock_upload_stage" in names
    elif name == "knowledge_index":
        response = tool(app, "stock_knowledge", {"topic": "index"})
        body = result(response)
        passed = body.get("start_with") == "mindset" and "metadata-seo" in body.get("topics", [])
    elif name == "full_topic_compaction":
        response = tool(app, "stock_knowledge", {"topic": "metadata-seo"})
        body = result(response)
        artifact = Path(body.get("artifact_path", ""))
        passed = "artifact_path" in body and "markdown" not in body and artifact.is_file()
    elif name == "invalid_arguments":
        response = tool(app, "stock_status", {"unexpected": True})
        body = result(response)
        errors = int(response.get("isError", False))
        passed = errors == 1 and body.get("status") == "error" and "unexpected arguments" in body.get("error", "")
    elif name == "supply_queue_dedupe":
        a = tool(app, "stock_scan", {"requests": VARIANTS})
        b = tool(app, "stock_scan", {"requests": VARIANTS})
        aa, bb = result(a), result(b)
        physical = app.store.db.execute("SELECT count(*) FROM job WHERE kind='search'").fetchone()[0]
        passed = aa["job_ids"] == bb["job_ids"] and len(set(aa["job_ids"])) == 3 and physical == 3
        response = b
        details["physical_jobs"] = physical
    elif name == "completed_supply_wait_report":
        obs_ids = seed_search_fixtures(app)
        queued = result(tool(app, "stock_scan", {"requests": VARIANTS}))["job_ids"]
        for job_id, obs_id in zip(queued, obs_ids):
            app.store.db.execute("UPDATE job SET state='done', obs_id=? WHERE job_id=?", (obs_id, job_id))
        wait_response = tool(app, "stock_wait", {"job_ids": queued, "timeout_seconds": 1})
        report_response = tool(app, "stock_report", {"keywords": ["matcha latte"], "media_type": "photo"})
        waited, report = result(wait_response), result(report_response)
        response = report_response
        details["wait_state"] = waited.get("state")
        passed = waited.get("state") == "completed" and report.get("metric_count", 0) > 0 and "markdown" not in report
    elif name == "daily_cap_wait":
        ids = result(tool(app, "stock_scan", {"requests": [VARIANTS[0]]}))["job_ids"]
        day = app.queue._day()
        app.store.set_state("day", {"day": day, "count": app.cfg["pacing"]["daily_cap"]})
        import adobe_stock_analytics.app as app_module
        original_time = app_module.time.time
        clock_values = iter((0.0, 2.0))
        app_module.time.time = lambda: next(clock_values)
        try:
            response = tool(app, "stock_wait", {"job_ids": ids, "timeout_seconds": 1})
        finally:
            app_module.time.time = original_time
        body = result(response)
        passed = body.get("queue_reason") == "daily_cap" and body.get("unfinished_job_ids") == ids
    elif name == "captcha_stop_receipt":
        ids = result(tool(app, "stock_scan", {"requests": [VARIANTS[0]]}))["job_ids"]
        app.queue.stop("captcha")  # Local fixture state only; never invokes stock_stop.
        response = tool(app, "stock_wait", {"job_ids": ids, "timeout_seconds": 1})
        body = result(response)
        passed = body.get("stop", {}).get("reason") == "captcha" and body.get("queue_reason") == "stopped:captcha"
    else:
        raise ValueError(f"unknown benchmark: {name}")

    text = payload(response)
    errors += int(response.get("isError", False)) if name != "invalid_arguments" else 0
    elapsed = (time.perf_counter() - started) * 1000
    return {"scenario": name, "latency_ms": elapsed, "output_chars": len(text),
            "output_bytes": len(text.encode("utf-8")), "estimated_tokens_chars_div_4": (len(text) + 3) // 4,
            "retries": retries, "errors": errors, "pass": bool(passed), "details": details}


def percentile(values, p):
    vals = sorted(values)
    return vals[max(0, math.ceil(p * len(vals)) - 1)]


def distribution(rows):
    latencies = [r["latency_ms"] for r in rows]
    return {"min_ms": min(latencies), "p50_ms": median(latencies), "p95_ms": percentile(latencies, .95),
            "max_ms": max(latencies), "output_bytes_min": min(r["output_bytes"] for r in rows),
            "output_bytes_max": max(r["output_bytes"] for r in rows),
            "output_chars_min": min(r["output_chars"] for r in rows),
            "output_chars_max": max(r["output_chars"] for r in rows),
            "estimated_tokens_min_chars_div_4": min(r["estimated_tokens_chars_div_4"] for r in rows),
            "estimated_tokens_max_chars_div_4": max(r["estimated_tokens_chars_div_4"] for r in rows),
            "retries": sum(r["retries"] for r in rows), "errors": sum(r["errors"] for r in rows),
            "passed": sum(r["pass"] for r in rows), "total": len(rows)}


def evaluate(repeats=3):
    if repeats < 1:
        raise ValueError("repeats must be at least 1")
    names = ("status", "tools_list", "knowledge_index", "full_topic_compaction", "invalid_arguments",
             "supply_queue_dedupe", "completed_supply_wait_report", "daily_cap_wait", "captcha_stop_receipt")
    started = time.perf_counter()
    runs = []
    for name in names:
        for _ in range(repeats):
            with tempfile.TemporaryDirectory(prefix="mcp-eval-") as data_dir:
                runs.append(benchmark(name, make_app(data_dir)))
    elapsed = (time.perf_counter() - started) * 1000
    by_scenario = {name: distribution([r for r in runs if r["scenario"] == name]) for name in names}
    passed = sum(r["pass"] for r in runs)
    return {"mode": "local_fixture_only_read_only", "network_access": False, "portal_access": False,
            "bridge_started": False, "tools_invoked": ["stock_status", "stock_scan", "stock_wait", "stock_report", "stock_knowledge"],
            "forbidden_tools_invoked": [], "repeats_per_scenario": repeats, "wall_latency_ms": elapsed,
            "runs": runs, "by_scenario": by_scenario,
            "acceptance": {"passed": passed, "total": len(runs), "success_rate": passed / len(runs)},
            "agent_tokens": "unavailable", "model_tokens": "unavailable", "model_billing_cost": "unavailable"}


def matches_schema(value, schema):
    """Check the small JSON-schema subset used by this toolkit's tool catalog."""
    if "enum" in schema and value not in schema["enum"]:
        return False
    kind = schema.get("type")
    expected = {"object": dict, "array": list, "string": str, "integer": int, "boolean": bool}
    if kind in expected and type(value) is not expected[kind]:
        return False
    if kind == "object":
        props = schema.get("properties", {})
        return (set(schema.get("required", [])) <= set(value)
                and (schema.get("additionalProperties", True) or not (set(value) - set(props)))
                and all(matches_schema(v, props[k]) for k, v in value.items() if k in props))
    if kind in ("array", "string"):
        lo, hi = ("minItems", "maxItems") if kind == "array" else ("minLength", "maxLength")
        if len(value) < schema.get(lo, 0) or len(value) > schema.get(hi, float("inf")):
            return False
    if kind == "array":
        return all(matches_schema(v, schema.get("items", {})) for v in value)
    if kind == "integer":
        return schema.get("minimum", -float("inf")) <= value <= schema.get("maximum", float("inf"))
    return True


def score_plan_file(path):
    cases = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(cases, list):
        raise ValueError("a blind plan must be an array of cases")
    by_case = {item.get("case"): item for item in cases if isinstance(item, dict)}
    checks = {}
    forbidden = {"stock_upload_metadata", "stock_stop", "stock_resume", "stock_restart_server"}
    def call_args(call):
        return call.get("arguments", call.get("args", {})) if isinstance(call, dict) else {}
    for name in CASES:
        item = by_case.get(name, {})
        calls = item.get("calls", [])
        if not isinstance(calls, list):
            checks[name] = False
            continue
        tools = [call.get("tool") for call in calls if isinstance(call, dict)]
        action = " ".join(str(item.get(k, "")) for k in ("action", "stop", "reason")).lower()
        ok = (isinstance(calls, list) and len(tools) == len(calls) and not (set(tools) & forbidden)
              and all(tool_name in mcp_server.TOOLS and matches_schema(call_args(call), mcp_server.TOOLS[tool_name][1])
                      for call, tool_name in zip(calls, tools)))
        if not ok:
            checks[name] = False
            continue
        if name == "supply_one_phrase":
            core = [tool_name for tool_name in tools if tool_name != "stock_status"]
            ok &= core == ["stock_scan", "stock_wait", "stock_report"] and tools.count("stock_status") <= 1
            scan = next((call for call in calls if call.get("tool") == "stock_scan"), {})
            requests = call_args(scan).get("requests", [])
            ok &= len(requests) == 3 and len({x["keyword"] for x in requests}) == 1
            ok &= len({x.get("media_type", "photo") for x in requests}) == 1
            ok &= {(x.get("ai_filter"), x.get("order")) for x in requests} == {
                ("all", "relevance"), ("only_ai", "relevance"), ("all", "downloads")}
        elif name == "captcha_stop":
            ok &= set(tools) <= {"stock_status"} and "captcha" in action
            ok &= all(word in action for word in ("do not", "resume"))
        elif name == "disconnected":
            ok &= set(tools) <= {"stock_status"} and "unmeasured" in action and "stock_scan" not in tools
        elif name == "daily_cap":
            ok &= set(tools) <= {"stock_status", "stock_wait"} and ("daily_cap" in action or "daily cap" in action)
            ok &= "stock_scan" not in tools and ("do not" in action or "ไม่" in action)
        elif name == "outcomes":
            core = [tool_name for tool_name in tools if tool_name != "stock_status"]
            ok &= core == ["stock_outcomes_scan", "stock_wait", "stock_outcomes"] and tools.count("stock_status") <= 1
        elif name == "stage_not_authorized":
            ok &= "stock_upload_stage" not in tools and "stock_upload_metadata" not in tools and "do not" in action
        elif name == "stage_authorized":
            core = [tool_name for tool_name in tools if tool_name != "stock_status"]
            stage = next((call for call in calls if call.get("tool") == "stock_upload_stage"), {})
            ok &= core == ["stock_upload_stage"] and tools.count("stock_status") <= 1
            ok &= call_args(stage).get("with_metadata") is True
            ok &= "submit" in action
        elif name == "partial_stage":
            ok &= not ({"stock_upload_stage", "stock_upload_metadata", "stock_resume"} & set(tools))
            ok &= ("stage_incomplete" in action or "incomplete stage" in action or "staging is incomplete" in action)
            ok &= "do not" in action
        elif name == "knowledge_artifact":
            ok &= set(tools) <= {"stock_knowledge"}
            ok &= ("fresh-context" in action or "fresh context" in action) and ("five" in action or "5" in action)
        elif name == "submit_request":
            ok &= not ({"stock_upload_stage", "stock_upload_metadata", "stock_resume"} & set(tools))
            ok &= "submit" in action and ("do not" in action or "cannot" in action or "never" in action)
        checks[name] = bool(ok)
    return {"file": str(path), "passed": sum(checks.values()), "total": len(CASES), "cases": checks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--score-plans", action="store_true", help="score workspace/evals/luna_low_*.json instead of benchmarking")
    parser.add_argument("--plans-glob", default="luna_low_*.json", help="file pattern inside workspace/evals")
    args = parser.parse_args()
    if args.score_plans:
        files = sorted((ROOT / "workspace" / "evals").glob(args.plans_glob))
        if not files:
            parser.error("no blind plan files matched; there is nothing to evaluate")
        per_file = [score_plan_file(path) for path in files]
        total = sum(row["total"] for row in per_file)
        passed = sum(row["passed"] for row in per_file)
        report = {"files": per_file, "aggregate": {"passed": passed, "total": total,
                  "success_rate": passed / total if total else 0.0}}
        print(f"Blind plans: {passed}/{total} cases pass across {len(files)} files")
        for row in per_file:
            print(f"  {row['file']}: {row['passed']}/{row['total']}")
    else:
        report = evaluate(args.repeats)
        print(f"MCP local benchmark: {report['acceptance']['passed']}/{report['acceptance']['total']} pass; "
              f"wall {report['wall_latency_ms']:.2f} ms; agent/model tokens and billing cost unavailable")
        for name, stats in report["by_scenario"].items():
            print(f"  {name}: {stats['passed']}/{stats['total']}; latency min/p50/p95/max "
                  f"{stats['min_ms']:.3f}/{stats['p50_ms']:.3f}/{stats['p95_ms']:.3f}/{stats['max_ms']:.3f} ms; "
                  f"bytes {stats['output_bytes_min']}-{stats['output_bytes_max']}, chars {stats['output_chars_min']}-"
                  f"{stats['output_chars_max']}, estimated tokens {stats['estimated_tokens_min_chars_div_4']}-"
                  f"{stats['estimated_tokens_max_chars_div_4']}; retries {stats['retries']}, errors {stats['errors']}")
    if args.json_out:
        args.json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if report.get("acceptance", report.get("aggregate", {})).get("passed", 0) == report.get("acceptance", report.get("aggregate", {})).get("total", -1) else 1


if __name__ == "__main__":
    raise SystemExit(main())
