"""Verified file staging for the Uploads page. Staging adds files to the portal's New list; it never submits them.

The plan is the JSON that `prepare-plan` wrote (ready_for_upload, failures, package_digest,
folder, files[path, sha256]). This module trusts nothing in it beyond what it can re-check on disk: every file is
re-hashed, must sit directly in the plan's folder, and the folder must not be a protected one.
"""
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .config import upload_metadata_cfg, upload_stage_cfg

IMAGE_EXT = {".jpg", ".jpeg", ".png"}
SUBMIT_RE = re.compile(r"^Submit\s+(\d+)\s+files?$", re.I)
HEX64 = re.compile(r"^[0-9a-f]{64}$")


class StageError(ValueError):
    pass


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _plan_age_hours(created_at, now):
    try:
        t = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
    except ValueError:
        raise StageError("plan has no readable created_at")
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return (now - t).total_seconds() / 3600


def load_plan(plan_path, cfg, only=None, now=None, switch="upload_stage"):
    """Validate a prepared upload plan and return the files that may be staged. Raises PermissionError or StageError.
    `switch` names the user's on/off switch that must be on: upload_stage (default) or upload_metadata."""
    c = upload_stage_cfg(cfg)
    if switch == "upload_metadata":
        if upload_metadata_cfg(cfg).get("enabled") is not True:
            raise PermissionError("metadata upload is off: the user sets upload_metadata.enabled in config/stock_analytics.json")
    elif c.get("enabled") is not True:
        raise PermissionError("upload staging is off: the user sets upload_stage.enabled in config/stock_analytics.json")
    p = Path(plan_path)
    if not p.is_file():
        raise StageError("plan file not found")
    try:
        plan = json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        raise StageError("plan is not valid JSON")
    if not isinstance(plan, dict) or plan.get("ready_for_upload") is not True or plan.get("failures"):
        raise StageError("plan is not ready_for_upload (run prepare-plan and fix its failures)")
    digest = plan.get("package_digest")
    if not isinstance(digest, str) or not HEX64.match(digest):
        raise StageError("plan has no package_digest")
    now = now or datetime.now(timezone.utc)
    age = _plan_age_hours(plan.get("created_at"), now)
    if age > c["max_plan_age_hours"] or age < -1:
        raise StageError(f"plan is older than {c['max_plan_age_hours']} h: run prepare-plan again")
    folder = Path(str(plan.get("folder", ""))).resolve()
    if not folder.is_dir():
        raise StageError("plan folder not found")
    if any(m.lower() in str(folder).lower() for m in c["protected_markers"]):
        raise StageError("plan folder is protected and can never be staged")
    entries = plan.get("files")
    if not isinstance(entries, list) or not entries:
        raise StageError("plan lists no files")
    files = []
    for e in entries:
        if not isinstance(e, dict) or not isinstance(e.get("path"), str) or not HEX64.match(str(e.get("sha256", ""))):
            raise StageError("plan file entry needs path and sha256")
        fp = Path(e["path"]).resolve()
        if fp.parent != folder:
            raise StageError(f"{fp.name} is not directly inside the plan folder")
        if fp.suffix.lower() not in IMAGE_EXT or not fp.is_file():
            raise StageError(f"{fp.name} is not an existing image file")
        files.append({"name": fp.name, "path": str(fp), "sha256": e["sha256"], "size": fp.stat().st_size})
    names = [f["name"] for f in files]
    if len(set(names)) != len(names):
        raise StageError("plan lists the same file name twice")
    if only is not None:
        if not isinstance(only, list) or not only or not all(isinstance(n, str) for n in only):
            raise StageError("only must be a non-empty list of file names")
        unknown = sorted(set(only) - set(names))
        if unknown:
            raise StageError(f"only names not in the plan: {unknown}")
        files = [f for f in files if f["name"] in set(only)]
    if len(files) > c["max_files"]:
        raise StageError(f"more than {c['max_files']} files in one stage")
    if sum(f["size"] for f in files) > c["max_total_mb"] * 1024 * 1024:
        raise StageError(f"more than {c['max_total_mb']} MB in one stage")
    for f in files:
        if sha256_file(f["path"]) != f["sha256"]:
            raise StageError(f"{f['name']} changed after the plan was made (sha256 differs)")
    return {"package_digest": digest, "folder": str(folder), "files": sorted(files, key=lambda f: f["name"]), "csv_entries": plan.get("csv")}


def submit_count(text):
    """'Submit 3 files' -> 3; anything else -> None."""
    m = SUBMIT_RE.match((text or "").strip())
    return int(m.group(1)) if m else None
