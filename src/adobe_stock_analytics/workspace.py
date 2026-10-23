"""The shared working state every agent reads and keeps: workspace/STATE.md (now), LOG.md (append-only history) and
PLAYBOOK.md (lessons from evidence and the user's standing choices). Code, not a model, edits the playbook: one entry
at a time with an id and counters, never a rewrite. Stdlib only."""

import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .config import ROOT

WORKSPACE = ROOT / "workspace"
TEMPLATES = ROOT / "examples" / "workspace"
FILES = ("STATE.md", "LOG.md", "PLAYBOOK.md")
STATE_MAX_LINES = 150
PLAYBOOK_MAX_LINES = 200
AGENTS_MAX_LINES = 100
CLAIM_STALE_HOURS = 12

ENTRY = re.compile(r"^- \[(?P<id>[LC]-\d{3})\] (?P<text>.+?) \| \+(?P<up>\d+) -(?P<down>\d+) \| "
                   r"(?P<src>evidence|source): (?P<ev>.+?) \| tags: (?P<tags>[^|]*) \| added (?P<added>\d{4}-\d{2}-\d{2})$")
LOG_HEAD = re.compile(r"^## \[(\d{4}-\d{2}-\d{2})\] [a-z]+ \| [^|]+ \| .+$")
DECISION = re.compile(r"^- \[D-\d{3}\] \d{4}-\d{2}-\d{2} .+")
CLAIM = re.compile(r"^Working now: (?:none|.+ since (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) UTC on .+)$")
SECTIONS = {"STATE.md": ("## Focus", "## Runs", "## Waiting on the user", "## Stops and blockers", "## Next"),
            "PLAYBOOK.md": ("## Standing choices (user)", "## Lessons", "## Retired")}


def init(ws=WORKSPACE, today=None):
    """Create STATE.md, LOG.md and PLAYBOOK.md from the templates when missing; never overwrite."""
    ws = Path(ws)
    ws.mkdir(parents=True, exist_ok=True)
    created, kept = [], []
    for name in FILES:
        (kept if (ws / name).exists() else created).append(name)
        if name in created:
            text = (TEMPLATES / name).read_text(encoding="utf-8")
            (ws / name).write_text(text.replace("Updated: YYYY-MM-DD by <agent>", f"Updated: {(today or date.today()).isoformat()} by init"), encoding="utf-8")
    return {"ok": True, "workspace": str(ws), "created": created, "kept": kept}


def _entries(lines):
    return [(i, m) for i, line in enumerate(lines) if (m := ENTRY.match(line))]


def _section_end(lines, heading):
    start = lines.index(heading)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("## "):
            return j
    return len(lines)


def _resolve(path, ws):
    p = Path(path)
    return p if p.is_absolute() else (ROOT / p if (ROOT / p).exists() else Path(ws).parent / p)


def _clean(text):
    text = " ".join(str(text).split())
    if not text or "|" in text:
        raise ValueError("text must be one line without '|'")
    return text


def add(text, kind="lesson", evidence=(), source=None, tags=(), ws=WORKSPACE, today=None):
    """Append one lesson (needs evidence files that exist) or one standing choice (needs a source such as 'chat 2026-10-17')."""
    ws = Path(ws)
    pb = ws / "PLAYBOOK.md"
    lines = pb.read_text(encoding="utf-8").splitlines()
    text = _clean(text)
    if kind == "lesson":
        if not evidence:
            raise ValueError("a lesson needs --evidence: a file a reader can open (run report, outcome ledger, tool output)")
        missing = [e for e in evidence if not _resolve(e, ws).exists()]
        if missing:
            raise ValueError(f"evidence not found: {', '.join(missing)}")
        prefix, src, value, heading = "L", "evidence", "; ".join(_clean(e) for e in evidence), "## Lessons"
    elif kind == "choice":
        if not source:
            raise ValueError("a choice needs --source, for example 'chat 2026-10-17'")
        prefix, src, value, heading = "C", "source", _clean(source), "## Standing choices (user)"
    else:
        raise ValueError("kind must be lesson or choice")
    ids = [int(m[1]) for line in lines if (m := re.match(rf"^- \[{prefix}-(\d{{3}})\]", line))]  # retired ids too
    eid = f"{prefix}-{max(ids, default=0) + 1:03d}"
    if any(m["text"].lower() == text.lower() for _, m in _entries(lines)):
        raise ValueError("the same text is already in the playbook: vote on it instead")
    tag_text = ", ".join(_clean(t) for t in tags) if tags else "-"
    line = f"- [{eid}] {text} | +0 -0 | {src}: {value} | tags: {tag_text} | added {(today or date.today()).isoformat()}"
    lines.insert(_section_end(lines, heading), line)
    pb.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"ok": True, "id": eid, "line": line}


def vote(eid, verdict, evidence, ws=WORKSPACE):
    """Count one use of a lesson as helpful or harmful, with the evidence of that use appended."""
    if verdict not in ("helpful", "harmful"):
        raise ValueError("verdict must be helpful or harmful")
    ws = Path(ws)
    if not _resolve(evidence, ws).exists():
        raise ValueError(f"evidence not found: {evidence}")
    pb = ws / "PLAYBOOK.md"
    lines = pb.read_text(encoding="utf-8").splitlines()
    for i, m in _entries(lines):
        if m["id"] == eid:
            up, down = int(m["up"]) + (verdict == "helpful"), int(m["down"]) + (verdict == "harmful")
            ev = m["ev"] if _clean(evidence) in m["ev"].split("; ") else f"{m['ev']}; {_clean(evidence)}"
            lines[i] = f"- [{eid}] {m['text']} | +{up} -{down} | {m['src']}: {ev} | tags: {m['tags']} | added {m['added']}"
            pb.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return {"ok": True, "id": eid, "line": lines[i]}
    raise ValueError(f"{eid} not found")


def retire(eid, reason, ws=WORKSPACE, today=None):
    """Move a wrong or outdated entry to '## Retired' with the reason; it is kept, never deleted."""
    ws = Path(ws)
    pb = ws / "PLAYBOOK.md"
    lines = pb.read_text(encoding="utf-8").splitlines()
    for i, m in _entries(lines):
        if m["id"] == eid:
            if i > lines.index("## Retired"):
                raise ValueError(f"{eid} is already retired")
            line = lines.pop(i) + f" | retired {(today or date.today()).isoformat()}: {_clean(reason)}"
            lines.insert(_section_end(lines, "## Retired"), line)
            pb.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return {"ok": True, "id": eid, "line": line}
    raise ValueError(f"{eid} not found")


def lint(ws=WORKSPACE, agents=ROOT / "AGENTS.md", now=None):
    """Mechanical health check of the shared state: structure, size caps, stale claim, decision ids, log order, evidence paths."""
    ws = Path(ws)
    now = now or datetime.now(timezone.utc)
    problems, warnings = [], []
    for name in FILES:
        if not (ws / name).is_file():
            problems.append(f"{name} missing: run python3 stock.py init")
    if problems:
        return {"ok": False, "problems": problems, "warnings": warnings}
    texts = {n: (ws / n).read_text(encoding="utf-8") for n in FILES}
    for name, heads in SECTIONS.items():
        lines = texts[name].splitlines()
        problems += [f"{name}: section '{h}' missing" for h in heads if h not in lines]

    state = texts["STATE.md"].splitlines()
    if len(state) > STATE_MAX_LINES:
        warnings.append(f"STATE.md has {len(state)} lines (cap {STATE_MAX_LINES}): move archived runs out")
    if not any(re.match(r"^Updated: \d{4}-\d{2}-\d{2} by .+", l) for l in state):
        problems.append("STATE.md: 'Updated: YYYY-MM-DD by <agent>' line missing")
    claims = [l for l in state if l.startswith("Working now:")]
    if len(claims) != 1 or not CLAIM.match(claims[0]):
        problems.append("STATE.md: need one 'Working now: none' or 'Working now: <agent> since YYYY-MM-DD HH:MM UTC on <task>' line")
    elif (m := CLAIM.match(claims[0])) and m.group(1):
        since = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
        if now - since > timedelta(hours=CLAIM_STALE_HOURS):
            warnings.append(f"STATE.md: claim since {m.group(1)} UTC is older than {CLAIM_STALE_HOURS} h: ask the user before taking over")
    if "## Waiting on the user" in state:
        for l in state[state.index("## Waiting on the user") + 1:_section_end(state, "## Waiting on the user")]:
            if l.startswith("- ") and not DECISION.match(l):
                problems.append(f"STATE.md: decision line needs '- [D-NNN] YYYY-MM-DD ...': {l[:60]}")

    last = None
    for l in texts["LOG.md"].splitlines():
        if l.startswith("## "):
            m = LOG_HEAD.match(l)
            if not m:
                problems.append(f"LOG.md: header must be '## [YYYY-MM-DD] op | run | agent': {l[:60]}")
            elif last and m.group(1) < last:
                problems.append(f"LOG.md: entries out of date order at {m.group(1)} (append only, newest last)")
            else:
                last = m.group(1) if m else last

    pb = texts["PLAYBOOK.md"].splitlines()
    if len(pb) > PLAYBOOK_MAX_LINES:
        warnings.append(f"PLAYBOOK.md has {len(pb)} lines (cap {PLAYBOOK_MAX_LINES}): retire or merge lessons")
    seen = set()
    for l in pb:
        if re.match(r"^- \[[LC]-", l) and not ENTRY.match(l.split(" | retired ")[0]):
            problems.append(f"PLAYBOOK.md: entry not in the tool's format (use stock.py lesson): {l[:60]}")
    retired_at = pb.index("## Retired") if "## Retired" in pb else len(pb)
    for i, m in _entries(pb) + [(i, ENTRY.match(l.split(" | retired ")[0])) for i, l in enumerate(pb) if i > retired_at and " | retired " in l]:
        if not m:
            continue
        if m["id"] in seen:
            problems.append(f"PLAYBOOK.md: duplicate id {m['id']}")
        seen.add(m["id"])
        if i > retired_at:
            continue
        if m["src"] == "evidence":
            for e in m["ev"].split("; "):
                if not _resolve(e, ws).exists():
                    problems.append(f"PLAYBOOK.md {m['id']}: evidence not found: {e}")
        if int(m["down"]) > int(m["up"]):
            warnings.append(f"PLAYBOOK.md {m['id']}: more harmful than helpful uses: review it with the user or retire it")

    if Path(agents).is_file():
        n = len(Path(agents).read_text(encoding="utf-8").splitlines())
        if n > AGENTS_MAX_LINES:
            warnings.append(f"AGENTS.md has {n} lines (cap {AGENTS_MAX_LINES}): keep it a map, move detail into knowledge/ or workspace READMEs")
    return {"ok": not problems, "problems": problems, "warnings": warnings}
