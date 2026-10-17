import argparse
import importlib.util
import json
import shutil
import sys
from pathlib import Path

from .app import App
from .config import DEFAULT_DATA
from .connect import AGENTS as C_AGENTS


AGENT_SKILL_DIRS = {"claude": ".claude/skills", "codex": ".agents/skills", "opencode": ".config/opencode/skills", "agents": ".agents/skills", "antigravity": ".gemini/config/skills"}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="adobe-stock-analytics")
    ap.add_argument("--data-dir", default=str(DEFAULT_DATA))
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("serve", help="run the MCP server (stdio) and the extension bridge")
    sub.add_parser("status")
    sub.add_parser("resume", help="clear the stop state (user only)")
    sub.add_parser("write-extension-token", help="write extension/token.js so the extension pairs without typing")
    sub.add_parser("token-path", help="print where the pairing token is stored")
    r = sub.add_parser("report")
    r.add_argument("keywords", nargs="*")
    r.add_argument("--media-type", default="photo")
    r.add_argument("--trend", action="append", default=[])
    r.add_argument("--lead-as-of")
    r.add_argument("--portfolio", action="store_true")
    r.add_argument("--calibration", action="store_true")
    r.add_argument("--own-keywords", action="store_true")
    r.add_argument("--related", action="append", default=[], metavar="SEED")
    r.add_argument("--opportunity", action="append", default=[], metavar="KEYWORD::TERM",
                   help="supply rating of KEYWORD combined with the stored trend series named TERM")
    us = sub.add_parser("upload-stage", help="stage a prepared plan's files on the Uploads page (New list); never submits")
    us.add_argument("plan")
    us.add_argument("--only", action="append", default=None, metavar="FILE", help="stage only this file name (repeatable)")
    um = sub.add_parser("upload-metadata", help="apply the plan's CSV and the AI/people/include flags to the staged files; never submits")
    um.add_argument("plan")
    sub.add_parser("reload-extension", help="ask the running extension to reload itself (after its files changed on disk)")
    sub.add_parser("reset-staged", help="forget which files were staged (user only; after clearing the portal New list)")
    sk = sub.add_parser("install-skill", help="copy the adobe-stock skill and its know-how docs into an agent skills folder (dry run without --confirm-write)")
    sk.add_argument("--agent", choices=sorted(AGENT_SKILL_DIRS), default="claude", help="which agent's skills folder to use (default claude)")
    sk.add_argument("--dest", default=None, help="skills folder to use instead of --agent's default")
    sk.add_argument("--confirm-write", action="store_true")
    sub.add_parser("doctor", help="check Python, config, pairing token, extension token and installed skills")
    pm = sub.add_parser("print-mcp-config", help="print the MCP server entry for this checkout (paste into your agent's MCP settings)")
    pm.add_argument("--format", choices=["json", "toml", "opencode"], default="json", help="json: mcpServers (Cursor, Antigravity, Claude, most hosts); toml: Codex; opencode: OpenCode")
    for name, text in (("connect", "add this checkout's MCP server to an agent's user config"), ("disconnect", "remove only the entry that connect added")):
        c = sub.add_parser(name, help=text + " (dry run without --confirm-write; backs up, adds or removes only our entry)")
        c.add_argument("--agent", required=True, choices=C_AGENTS)
        c.add_argument("--confirm-write", action="store_true")
    ci = sub.add_parser("check-images", help="technical gate for a folder of final JPEGs (format, 4-100 MP, <=45 MB, duplicates, sha256)")
    ci.add_argument("folder")
    lr = sub.add_parser("lint-registry", help="check a prompt/metadata registry JSON (ids, titles, keywords, category, prompt policy)")
    lr.add_argument("registry")
    bc = sub.add_parser("build-csv", help="write the Adobe upload CSV for a folder of finals from a registry (scenario id must appear in each file name)")
    bc.add_argument("registry")
    bc.add_argument("folder")
    bc.add_argument("--out", required=True)
    cq = sub.add_parser("check-qc", help="validate a qc_decisions.json against a folder of finals")
    cq.add_argument("qc")
    cq.add_argument("folder")
    gd = sub.add_parser("check-decisions", help="list the generation questions the user has not answered yet (generation_decisions.json)")
    gd.add_argument("decisions")
    pp = sub.add_parser("prepare-plan", help="run all local gates and write the upload plan JSON used by upload-stage / upload-metadata")
    pp.add_argument("folder")
    pp.add_argument("--csv", required=True)
    pp.add_argument("--qc", required=True)
    pp.add_argument("--out", required=True)
    qt = sub.add_parser("qc-tiles", help="(needs Pillow) write a 1600 px frame and 3x3 native tiles per image for visual QC")
    qt.add_argument("folder")
    qt.add_argument("--out", required=True)
    sm = sub.add_parser("similar", help="(needs Pillow) look-alike screen: average-hash pairs within new finals and against earlier submitted folders")
    sm.add_argument("folder")
    sm.add_argument("--against", action="append", default=[], help="a folder of earlier submitted files (repeatable)")
    sm.add_argument("--threshold", type=int, default=8, help="max Hamming distance of 64-bit average hashes counted as a pair")
    up = sub.add_parser("upscale", help="(needs Pillow) Real-ESRGAN x4plus via realesrgan-ncnn-vulkan, then resize to the long edge, JPEG (dry run without --confirm-write)")
    up.add_argument("folder")
    up.add_argument("--out", required=True)
    up.add_argument("--bin", default=None, help="path to realesrgan-ncnn-vulkan if it is not on PATH")
    up.add_argument("--long-edge", type=int, default=3840, help="final long edge in px; 0 keeps the full x4 size (a 1448x1086 raw gives 5792x4344, about 25 MP)")
    up.add_argument("--quality", type=int, default=95)
    up.add_argument("--confirm-write", action="store_true")
    orp = sub.add_parser("outcome-report", help="accept / reject counts and rates per group and per content tag from the stored outcomes and portfolio reads")
    orp.add_argument("--groups", default=None, help="CSV: group plus asset_id, name or name_contains")
    orp.add_argument("--tags", default=None, help="CSV: asset_id or name plus content tag columns")
    orp.add_argument("--submitted", default=None, help="folder of submitted JPEGs (undecided ones count as pending)")
    orp.add_argument("--ledger", default=None, help="write the joined per-file CSV here")
    orp.add_argument("--min-n", type=int, default=5)
    orp.add_argument("--qc", default=None, help="qc_decisions.json of the submitted batch: adds tag local_qc to compare QC verdicts with Adobe's")
    v = sub.add_parser("verify-doc")
    v.add_argument("path")
    d = sub.add_parser("dashboard", help="write a static HTML dashboard from stored metrics")
    d.add_argument("--out", required=True)
    w = sub.add_parser("fetch-wikipedia", help="store weekly Wikipedia pageviews for an article as an attention series")
    w.add_argument("article")
    w.add_argument("--as", dest="term", help="term name to store it under (default: the article title)")
    w.add_argument("--lang", default="en")
    w.add_argument("--weeks", type=int, default=20)
    g = sub.add_parser("fetch-gdelt", help="store weekly GDELT news-volume intensity for a query as an attention series")
    g.add_argument("query")
    g.add_argument("--as", dest="term", help="term name to store it under (default: 'gdelt: QUERY')")
    g.add_argument("--weeks", type=int, default=20)
    gk = sub.add_parser("import-group-keywords")
    gk.add_argument("path")
    ud = sub.add_parser("import-upload-dates")
    ud.add_argument("path")
    ir = sub.add_parser("import-related")
    ir.add_argument("path")
    ir.add_argument("--seed", required=True)
    sub.add_parser("init", help="create workspace/STATE.md, LOG.md and PLAYBOOK.md from the templates when missing (never overwrites)")
    sub.add_parser("lint-workspace", help="check the shared state files: structure, size caps, stale claim, decision ids, log order, lesson evidence")
    ls = sub.add_parser("lesson", help="change workspace/PLAYBOOK.md one entry at a time: add, vote, retire")
    lsub = ls.add_subparsers(dest="lesson_cmd", required=True)
    la = lsub.add_parser("add", help="add a lesson (needs --evidence) or a standing user choice (--kind choice --source)")
    la.add_argument("text")
    la.add_argument("--kind", choices=["lesson", "choice"], default="lesson")
    la.add_argument("--evidence", action="append", default=[], help="a file a reader can open (repeatable)")
    la.add_argument("--source", default=None, help="for a choice: where the user decided, for example 'chat 2026-10-17'")
    la.add_argument("--tags", default="", help="comma-separated, for example qc,upscale")
    lv = lsub.add_parser("vote", help="count one use of a lesson as helpful or harmful")
    lv.add_argument("id")
    lv.add_argument("verdict", choices=["helpful", "harmful"])
    lv.add_argument("--evidence", required=True)
    lt = lsub.add_parser("retire", help="move an entry to Retired with the reason")
    lt.add_argument("id")
    lt.add_argument("--reason", required=True)
    t = sub.add_parser("import-trends")
    t.add_argument("path")
    a = ap.parse_args(argv)
    if a.cmd == "serve":
        from .mcp_server import serve
        serve(App(a.data_dir, start_bridge=True))
        return 0
    app = App(a.data_dir)
    if a.cmd == "status":
        out = app.stock_status()
    elif a.cmd == "resume":
        app.queue.resume()
        out = {"stop": app.queue.stop_state()}
    elif a.cmd == "install-skill":
        from .config import ROOT
        dest = Path(a.dest).expanduser() if a.dest else Path.home() / AGENT_SKILL_DIRS[a.agent]
        target = dest / "adobe-stock"
        out = {"target": str(target), "exists": target.exists(), "written": False}
        if a.confirm_write:
            if target.exists():
                marker = target / "SKILL.md"
                if not marker.is_file() or "name: adobe-stock\n" not in marker.read_text(encoding="utf-8"):
                    raise SystemExit(f"{target} exists and is not this tool's skill folder; move it away first")
                shutil.rmtree(target)  # this tool's own folder, replaced as a whole
            (target / "references").mkdir(parents=True)
            shutil.copy2(ROOT / "skills" / "adobe-stock" / "SKILL.md", target / "SKILL.md")
            for f in sorted((ROOT / "knowledge").glob("*.md")):
                shutil.copy2(f, target / "references" / f.name)
            out["written"] = True
    elif a.cmd == "doctor":
        from .config import ROOT
        from .bridge import load_token
        checks = {"python>=3.11": sys.version_info >= (3, 11), "config": (ROOT / "config" / "stock_analytics.json").is_file(),
                  "pairing_token": bool(load_token(app.data_dir)), "extension_token_js": (ROOT / "extension" / "token.js").is_file(),
                  "pillow_for_qc_tiles": importlib.util.find_spec("PIL") is not None}
        skills = {k: str(Path.home() / v / "adobe-stock") for k, v in AGENT_SKILL_DIRS.items() if (Path.home() / v / "adobe-stock" / "SKILL.md").is_file()}
        from . import connect as C
        mcp = C.registered()
        hints = []
        if not mcp:
            hints.append("connect your agent (dry run first, then ask the user): python3 stock.py connect --agent claude   (or codex | cursor | antigravity | opencode); other agents: python3 stock.py print-mcp-config")
        if not checks["extension_token_js"]:
            hints.append("run: python3 stock.py write-extension-token, then the user loads extension/ in Chrome (INSTALL.md step 6)")
        if not skills:
            hints.append("install the skill: python3 stock.py install-skill --agent claude (dry run), then ask the user, then add --confirm-write (or codex / antigravity / agents / opencode)")
        out = {"ok": checks["python>=3.11"] and checks["config"], "checks": checks, "skills_installed": skills, "mcp_registered_in": mcp, "next": hints,
               "note": "ok means Python and the config are fine; setup items still open are listed in next. pillow_for_qc_tiles is optional; mcp_registered_in only checks agent config files; to test the live connection call stock_status from your agent"}
    elif a.cmd == "print-mcp-config":
        from . import connect as C
        if a.format == "toml":
            print(C.toml_block(), end="")
            return 0
        out = C.render(a.format)
    elif a.cmd in ("connect", "disconnect"):
        from . import connect as C
        out = C.plan(a.agent, a.confirm_write, remove=a.cmd == "disconnect")
    elif a.cmd in ("check-images", "lint-registry", "build-csv", "check-qc", "check-decisions", "prepare-plan", "qc-tiles"):
        from . import package as P
        from .upload_stage import StageError
        try:
            if a.cmd == "check-images":
                out = P.check_images(a.folder)
            elif a.cmd == "lint-registry":
                out = P.lint_registry(a.registry)
            elif a.cmd == "build-csv":
                out = P.build_csv(a.registry, a.folder, a.out)
            elif a.cmd == "check-qc":
                out = P.check_qc(a.qc, {f["name"]: f["sha256"] for f in P.check_images(a.folder)["files"]})
            elif a.cmd == "check-decisions":
                out = P.check_decisions(a.decisions)
            elif a.cmd == "prepare-plan":
                out = P.prepare_plan(a.folder, a.csv, a.qc, a.out, app.cfg["upload_stage"]["protected_markers"], app.cfg["upload_stage"]["max_files"])
            else:
                out = {"ok": True, "images": [P.qc_tiles(p, a.out) for p in sorted(Path(a.folder).glob("*.jp*g"))]}
        except (StageError, OSError, ValueError) as e:
            out = {"ok": False, "error": str(e)}
    elif a.cmd == "similar":
        from . import similar as SM
        try:
            out = SM.screen(a.folder, a.against, a.threshold)
        except (OSError, ValueError) as e:
            out = {"ok": False, "error": str(e)}
    elif a.cmd == "upscale":
        from . import upscale as U
        out = U.run(a.folder, a.out, a.bin, a.long_edge, a.quality, confirm_write=a.confirm_write)
    elif a.cmd == "outcome-report":
        out = app.stock_outcome_report(a.groups, a.tags, a.submitted, a.ledger, a.min_n, a.qc)
    elif a.cmd == "upload-stage":
        out = app.stock_upload_stage(a.plan, a.only)
    elif a.cmd == "upload-metadata":
        out = app.stock_upload_metadata(a.plan)
    elif a.cmd == "reload-extension":
        app.store.set_state("reload_extension", True)
        out = {"reload_requested": True, "note": "the extension reloads on its next poll (within about 30 s); needs extension 0.8.3 or newer to be loaded once"}
    elif a.cmd == "reset-staged":
        app.store.set_state("staged", {})
        out = {"staged": {}}
    elif a.cmd == "write-extension-token":
        from .bridge import load_token
        from .config import ROOT
        f = ROOT / "extension" / "token.js"
        f.write_text(f'const INTEL_TOKEN = "{load_token(app.data_dir)}";\n')
        f.chmod(0o600)
        out = {"written": str(f)}
    elif a.cmd == "token-path":
        from .bridge import load_token
        load_token(app.data_dir)
        out = {"path": str(app.data_dir / "token")}
    elif a.cmd == "report":
        out = app.stock_report(a.keywords, a.media_type, a.trend, lead_as_of=a.lead_as_of, portfolio=a.portfolio, calibration=a.calibration, own_keywords=a.own_keywords, related=a.related,
                               opportunities=[dict(zip(("keyword", "term"), x.split("::", 1))) for x in a.opportunity])
        print(out["markdown"])
        return 0
    elif a.cmd == "dashboard":
        from . import dashboard
        from .store import utcnow
        Path(a.out).write_text(dashboard.render(app.store, app.cfg, utcnow()), encoding="utf-8")
        out = {"written": a.out}
    elif a.cmd == "fetch-gdelt":
        from . import gdelt
        out = gdelt.fetch(app.store, a.query, a.term, a.weeks)
    elif a.cmd == "fetch-wikipedia":
        from . import wikipedia
        out = wikipedia.fetch(app.store, a.article, a.term, a.lang, a.weeks)
    elif a.cmd == "import-group-keywords":
        out = app.stock_import_group_keywords(a.path)
    elif a.cmd == "import-upload-dates":
        out = app.stock_import_upload_dates(a.path)
    elif a.cmd == "import-related":
        out = app.stock_import_related(a.path, a.seed)
    elif a.cmd in ("init", "lint-workspace", "lesson"):
        from . import workspace as WS
        try:
            if a.cmd == "init":
                out = WS.init()
            elif a.cmd == "lint-workspace":
                out = WS.lint()
            elif a.lesson_cmd == "add":
                out = WS.add(a.text, a.kind, a.evidence, a.source, [t for t in a.tags.split(",") if t.strip()])
            elif a.lesson_cmd == "vote":
                out = WS.vote(a.id, a.verdict, a.evidence)
            else:
                out = WS.retire(a.id, a.reason)
        except (OSError, ValueError) as e:
            out = {"ok": False, "error": str(e)}
    elif a.cmd == "verify-doc":
        out = app.stock_verify_doc(a.path)
    else:
        out = app.stock_import_trends(a.path)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0 if out.get("ok", True) else 1


if __name__ == "__main__":
    sys.exit(main())
