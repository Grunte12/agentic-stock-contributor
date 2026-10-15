"""Decision-doc checker: blocks numbers the tool did not produce."""
import hashlib
import re

from . import metrics as M
from .report import BLOCK_RE, render_body

CITE = re.compile(r"\[m:([0-9a-f]{16})\]")
NUM = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?%?")
DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


def _strip(line):
    line = re.sub(r"`[^`]*`", " ", line)
    line = re.sub(r"\]\([^)]*\)", "]", line)
    line = DATE.sub(" ", line)
    return re.sub(r"^\s*(?:[-*]\s+)?\d+[.)]\s+", "", line)


def verify_doc(store, text):
    problems = []
    for m in BLOCK_RE.finditer(text):
        ids = [i for i in m["ids"].split(",") if i]
        metrics = [store.metric(i) for i in ids]
        missing = [i for i, x in zip(ids, metrics) if x is None]
        if missing:
            problems.append({"type": "unknown_metric_in_table", "ids": missing})
            continue
        body = render_body(sorted(metrics, key=lambda x: x["metric_id"]))
        if body != m["body"] or hashlib.sha256(body.encode()).hexdigest() != m["sha"]:
            problems.append({"type": "table_mismatch", "ids": ids[:3]})
    outside = BLOCK_RE.sub("", text)
    in_fence = False
    for no, raw in enumerate(outside.splitlines(), 1):
        if raw.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or raw.startswith("#"):
            continue
        cites = CITE.findall(raw)
        cited = {}
        for cid in cites:
            mm = store.metric(cid)
            if mm is None:
                problems.append({"type": "unknown_metric_cite", "line": no, "id": cid})
            else:
                cited[cid] = M.forms(mm["value"])
        allowed = set().union(*cited.values()) if cited else set()
        for tok in NUM.findall(CITE.sub(" ", _strip(raw))):
            if tok not in allowed:
                problems.append({"type": "untraceable_number", "line": no, "number": tok})
    return {"ok": not problems, "problems": problems}
