"""Outcome report: join Adobe's verdicts (Not accepted list + accepted portfolio) with the user's groups and content tags.

Every number comes from stored read-only observations and the user's CSV files. Rates are descriptive, not causes.
"""
import csv
import io
import json
import math
import re
from pathlib import Path

OUTCOME = {"quality": "rej_quality", "similar": "rej_similar", "other": "rej_other", "unknown": "rej_unknown"}
COLS = ["asset_id", "name", "group", "outcome", "downloads", "width", "height"]


def _csv(path):
    raw = Path(path).read_bytes().decode("utf-8-sig")
    rd = csv.DictReader(io.StringIO(raw))
    lower = {(c or "").strip().lower(): c for c in (rd.fieldnames or [])}
    return lower, [{k: (r.get(c) or "").strip() for k, c in lower.items()} for r in rd]


def _wilson(k, n, z=1.96):
    if not n:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 3), round(min(1.0, c + h), 3)]


def _summary(rows, min_n):
    s = {"accepted": 0, "rej_quality": 0, "rej_similar": 0, "rej_other": 0, "rej_unknown": 0, "pending": 0, "downloads": 0}
    for r in rows:
        s[r["outcome"]] += 1
        s["downloads"] += r["downloads"] or 0
    decided = len(rows) - s["pending"]
    rej = decided - s["accepted"]
    s.update(files=len(rows), decided=decided,
             accept_rate=round(s["accepted"] / decided, 3) if decided else None,
             accept_rate_95ci=_wilson(s["accepted"], decided),
             quality_reject_rate=round(s["rej_quality"] / decided, 3) if decided else None,
             similar_reject_rate=round(s["rej_similar"] / decided, 3) if decided else None,
             downloads_per_accepted=round(s["downloads"] / s["accepted"], 2) if s["accepted"] else None,
             too_few=decided < min_n, rejected=rej)
    return s


def build(store, groups_csv=None, tags_csv=None, submitted_folder=None, min_n=5, qc_decisions=None):
    o = store.latest_outcomes()
    if not o:
        raise ValueError("no outcomes observation yet: run stock_outcomes_scan first")
    pf = store.db.execute("SELECT p.obs_id, o.read_at FROM pf_overview p JOIN observation o USING(obs_id) WHERE o.status='ok' "
                          "ORDER BY o.read_at DESC LIMIT 1").fetchone()
    rows = {}
    for r in o["rows"]:
        rows[int(r["asset_id"])] = {"asset_id": int(r["asset_id"]), "name": r["original_name"] or "", "outcome": OUTCOME.get(r["outcome_class"], "rej_other"),
                                    "downloads": 0, "width": r["width"], "height": r["height"]}
    if pf:
        names = {r["asset_id"]: r["original_name"] for r in store.db.execute("SELECT asset_id, original_name FROM pf_name WHERE obs_id=?", (pf["obs_id"],))}
        dls = {r["asset_id"]: r["downloads"] for r in store.db.execute("SELECT asset_id, downloads FROM pf_asset WHERE obs_id=?", (pf["obs_id"],))}
        for a in set(names) | set(dls):
            rows.setdefault(int(a), {"asset_id": int(a), "name": names.get(a) or "", "outcome": "accepted", "downloads": dls.get(a) or 0, "width": None, "height": None})
    seen_names = {r["name"] for r in rows.values() if r["name"]}
    pending = []
    if submitted_folder:
        d = Path(submitted_folder).expanduser()
        if not d.is_dir():
            raise ValueError(f"submitted_folder not found: {d}")
        for f in sorted(d.iterdir()):
            if f.suffix.lower() in (".jpg", ".jpeg") and f.name not in seen_names:
                pending.append({"asset_id": None, "name": f.name, "outcome": "pending", "downloads": 0, "width": None, "height": None})
    allrows = list(rows.values()) + pending

    # groups: the CSV first (asset_id, name, then name_contains), then the map imported with stock_import_groups
    gmap = {r["asset_id"]: r["grp"] for r in store.db.execute("SELECT asset_id, grp FROM group_map")}
    by_id, by_name, contains = {}, {}, []
    if groups_csv:
        cols, grows = _csv(groups_csv)
        if "group" not in cols or not ({"asset_id", "name", "name_contains"} & set(cols)):
            raise ValueError("groups CSV needs a group column and one of asset_id, name, name_contains")
        for g in grows:
            if not g.get("group"):
                continue
            if g.get("asset_id", "").isdigit():
                by_id[int(g["asset_id"])] = g["group"]
            elif g.get("name"):
                by_name[g["name"]] = g["group"]
            elif g.get("name_contains"):
                contains.append((g["name_contains"], g["group"]))
    for r in allrows:
        g = by_id.get(r["asset_id"]) or by_name.get(r["name"])
        if not g and r["name"]:
            g = next((grp for part, grp in contains if part in r["name"]), None)
        g = g or gmap.get(r["asset_id"])
        r["group"] = g or "(ungrouped)"

    tag_cols, tags = [], {}
    if tags_csv:
        cols, trows = _csv(tags_csv)
        if not ({"asset_id", "name"} & set(cols)):
            raise ValueError("tags CSV needs an asset_id or name column")
        tag_cols = [c for c in cols if c not in ("asset_id", "name", "tagger", "notes")]
        for t in trows:
            key = int(t["asset_id"]) if t.get("asset_id", "").isdigit() else t.get("name")
            if key:
                tags[key] = {c: t.get(c, "") for c in tag_cols}
    for r in allrows:
        t = tags.get(r["asset_id"]) or tags.get(r["name"]) or {}
        r["tags"] = {c: t.get(c) or "(untagged)" for c in tag_cols}
    if qc_decisions:
        # the local QC verdict becomes one more tag: Adobe's rates per verdict show how much the QC caught
        q = json.loads(Path(qc_decisions).expanduser().read_text(encoding="utf-8"))
        if not isinstance(q.get("pass"), list) or not isinstance(q.get("fail"), list):
            raise ValueError("qc_decisions needs pass and fail lists of file names")
        verdict = {**{n: "pass" for n in q["pass"]}, **{n: "fail" for n in q["fail"]}}
        tag_cols.append("local_qc")
        for r in allrows:
            r["tags"]["local_qc"] = verdict.get(r["name"]) or _qc_by_id(verdict, r["name"]) or "(not in record)"

    groups = {}
    for r in allrows:
        groups.setdefault(r["group"], []).append(r)
    by_tag = {c: {v: _summary([r for r in allrows if r["tags"][c] == v], min_n) for v in sorted({r["tags"][c] for r in allrows})} for c in tag_cols}
    return {
        "outcomes_obs_id": o["obs_id"], "outcomes_read_at": o["read_at"],
        "portfolio_obs_id": pf["obs_id"] if pf else None, "portfolio_read_at": pf["read_at"] if pf else None,
        "overall": _summary(allrows, min_n),
        "by_group": {g: _summary(v, min_n) for g, v in sorted(groups.items())},
        "by_tag": by_tag,
        "rows": allrows,
        "note": ("Descriptive counts from read-only portal reads, not causes and not a forecast. accept_rate = accepted / decided; "
                 "95% interval is Wilson. too_few = fewer than min_n decided files: do not draw a conclusion. Accepted files beyond portfolio "
                 "page 1 have no name, so a submitted file may show as pending although Adobe accepted it. Groups (batches) often differ in "
                 "content, date and size at once, and looking at many tag cuts finds chance patterns: treat each pattern as a hypothesis to test "
                 "(see knowledge topic outcomes). by_tag.local_qc, when given, compares the local QC verdict with Adobe's: rej_quality under pass are refusals the QC missed."),
    }


def _qc_by_id(verdict, name):
    """Older records list scenario ids, not file names: match an id that appears whole in the file name (longest wins)."""
    stem = Path(name).stem.lower() if name else ""
    hits = [k for k in verdict if "." not in k and re.search(r"(?<![a-z0-9])" + re.escape(k.lower()) + r"(?![a-z0-9])", stem)]
    return verdict[max(hits, key=len)] if hits else None


def write_ledger(report, path):
    tag_cols = sorted({c for r in report["rows"] for c in r["tags"]})
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(COLS + tag_cols)
        for r in sorted(report["rows"], key=lambda r: (r["group"], r["name"], r["asset_id"] or 0)):
            w.writerow([r.get(c) if r.get(c) is not None else "" for c in COLS] + [r["tags"][c] for c in tag_cols])
    return str(path)
