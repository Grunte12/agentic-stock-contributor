"""Metadata for staged files: the plan's own CSV (title, keywords, category), checked row by row before the extension may apply it.

The CSV is the one `prepare-plan` listed in the plan with its sha256. Nothing here talks to the portal; the
extension applies it (CSV upload, then generative AI / people / include flags for all files, then Save work). Submit is never clicked.
"""
import csv
import io
import re
from pathlib import Path

from . import upload_stage
from .config import upload_metadata_cfg
from .upload_stage import StageError, sha256_file

REQUIRED = ["Filename", "Title", "Keywords", "Category"]
PEOPLE = {"no", "yes", "later"}


def _check_rows(text, names, c):
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or any(h not in reader.fieldnames for h in REQUIRED):
        raise StageError(f"CSV header must contain {REQUIRED}")
    rows = {}
    for r in reader:
        fn = (r.get("Filename") or "").strip()
        if fn in rows:
            raise StageError(f"CSV lists {fn} twice")
        title = (r.get("Title") or "").strip()
        kws = [k.strip() for k in (r.get("Keywords") or "").split(",") if k.strip()]
        if not title or len(title) > c["max_title_chars"]:
            raise StageError(f"{fn}: title is empty or longer than {c['max_title_chars']} characters")
        if not c["min_keywords"] <= len(kws) <= c["max_keywords"]:
            raise StageError(f"{fn}: {len(kws)} keywords, need {c['min_keywords']}-{c['max_keywords']}")
        if len({k.lower() for k in kws}) != len(kws):
            raise StageError(f"{fn}: duplicate keywords")
        if not re.fullmatch(r"\d{1,3}", (r.get("Category") or "").strip()):
            raise StageError(f"{fn}: category must be Adobe's numeric code")
        rows[fn] = r
    if set(rows) != set(names):
        raise StageError(f"CSV rows and plan files differ: only in CSV {sorted(set(rows) - set(names))}, only in plan {sorted(set(names) - set(rows))}")
    return len(rows)


def load_metadata_plan(plan_path, cfg, now=None):
    """Validate the plan (same gates as staging) and its CSV. Returns what the queue needs; raises PermissionError or StageError."""
    c = upload_metadata_cfg(cfg)
    plan = upload_stage.load_plan(plan_path, cfg, None, now, switch="upload_metadata")
    entries = plan.pop("csv_entries")
    if not isinstance(entries, list) or len(entries) != 1 or not isinstance(entries[0], dict):
        raise StageError("plan must list exactly one CSV")
    p = Path(str(entries[0].get("path", ""))).resolve()
    if p.parent != Path(plan["folder"]) or p.suffix.lower() != ".csv" or not p.is_file():
        raise StageError("the plan's CSV must be an existing .csv directly in the plan folder")
    if not upload_stage.HEX64.match(str(entries[0].get("sha256", ""))) or sha256_file(p) != entries[0]["sha256"]:
        raise StageError("the CSV changed after the plan was made (sha256 differs)")
    if p.stat().st_size > 20 * 1024 * 1024:
        raise StageError("CSV is larger than Adobe's 20 MB limit")
    rows = _check_rows(p.read_text(encoding="utf-8-sig"), [f["name"] for f in plan["files"]], c)
    if str(c.get("people_property")).lower() not in PEOPLE:
        raise StageError("upload_metadata.people_property must be no, yes or later")
    if str(c.get("people_property")).lower() != "no":
        raise StageError("the extension can only answer 'No' to 'Add recognizable people or property?'; set it by hand in the portal for yes or later")
    flags = {"generative_ai": c.get("mark_generative_ai") is True, "people_property": str(c["people_property"]).lower(),
             "include_in_submission": c.get("include_in_submission") is True,
             "people_property_fictional": c.get("people_property_fictional") is True}
    return {"package_digest": plan["package_digest"], "rows": rows, "flags": flags,
            "csv": {"name": p.name, "path": str(p), "sha256": entries[0]["sha256"], "size": p.stat().st_size},
            "names": [f["name"] for f in plan["files"]]}
