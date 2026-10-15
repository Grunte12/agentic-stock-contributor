"""Google Trends "related queries" CSV exported by the user (TOP and RISING sections).

Related queries are search demand relative to the seed, geo and period chosen at export. "Breakout" is not a volume, and none
of this is stock-image demand. The agent picks queries from these lists and scans them on Adobe; supply is measured there.
"""
import csv
import hashlib
import io
from pathlib import Path

from . import metrics as M


def import_related(store, path, seed):
    seed = " ".join(seed.lower().split())
    if not seed or "|" in seed or len(seed) > 100:
        raise ValueError("seed must be a short phrase without |")
    raw = Path(path).read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if store.db.execute("SELECT 1 FROM trend_related WHERE file_sha256=? AND seed=? LIMIT 1", (sha, seed)).fetchone():
        return {"file_sha256": sha, "top": 0, "rising": 0, "already_imported": True}
    rows, section = [], None
    for line in csv.reader(io.StringIO(raw.decode("utf-8-sig"))):
        if not line or not any(c.strip() for c in line):
            continue
        head = line[0].strip()
        if len(line) == 1 and head.upper() in ("TOP", "RISING"):
            section = head.lower()
        elif head.lower() == "query" or section is None:
            if section is None and head.lower() != "query":
                raise ValueError("unknown related-queries format: expected a TOP or RISING section")
        elif len(line) >= 2 and line[1].strip():
            rows.append((section, head, line[1].strip()))
        else:
            raise ValueError(f"unknown related-queries row: {line!r}")  # never accept a partial import
    if not rows:
        raise ValueError("no related queries found")
    counts = {"top": 0, "rising": 0}
    for sec, q, v in rows:
        counts[sec] += 1
        store.db.execute("INSERT INTO trend_related VALUES(?,?,?,?,?,?)", (sha, seed, sec, counts[sec], q, v))
    return {"file_sha256": sha, **counts, "already_imported": False}


def compute_related(store, cfg, seed):
    seed = " ".join(seed.lower().split())
    r = store.db.execute("SELECT file_sha256 FROM trend_related WHERE seed=? ORDER BY rowid DESC LIMIT 1", (seed,)).fetchone()
    out = []
    for sec in ("top", "rising"):
        rows = [[x["query"], x["value_text"]] for x in store.db.execute(
            "SELECT query, value_text FROM trend_related WHERE file_sha256=? AND seed=? AND section=? ORDER BY rank",
            (r["file_sha256"], seed, sec))] if r else []
        m = M.mk(cfg, f"related_{sec}", f"related:{seed}", rows or None, [f"file:{r['file_sha256']}"] if r else [])
        store.put_metric(m)
        out.append(m)
    return out
