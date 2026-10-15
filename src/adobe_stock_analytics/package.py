"""Local batch tooling (stdlib only): the steps between "images exist" and "a verified upload plan".

Everything here is read-only except the functions that write a file the caller names (`build_csv`, `prepare_plan`).
Nothing talks to Adobe. A result of `ok: true` means local checks passed; it is not Adobe acceptance.
"""
import csv
import hashlib
import json
import re
import struct
from datetime import date, datetime, timezone
from pathlib import Path

from .upload_metadata import _check_rows
from .upload_stage import StageError, sha256_file

# Adobe contributor help pages (read 2026-10-13): JPEG, 4-100 megapixels, file <= 45 MB.
MIN_MP, MAX_MP, MAX_MB = 4.0, 100.0, 45
QC_MODES = {"parallel", "sequential", "single-pass", "user"}
SOF = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
# Phrases a prompt must not contain (policy: no artists, brands, trademarks, text on the image).
BAD_PROMPT = [(r"\bin the style of\b", False), (r"\bby (?:the )?artist\b", False), (r"\btrademark(?:ed)?\b", True), (r"\bwatermark(?:ed)?\b", True)]
TITLE_AI_WORDS = re.compile(r"\b(ai[- ]generated|ai image|ai art|generative ai|midjourney|firefly|dall-?e|gpt|stable diffusion)\b", re.I)
NEGATION_OK = re.compile(r"\b(no|without|never|avoid|free of|blank)\b[^.,;]{0,40}$", re.I)


def jpeg_size(path):
    """(width, height) read from the JPEG header, or None when the file is not a JPEG."""
    with open(path, "rb") as f:
        if f.read(2) != b"\xff\xd8":
            return None
        while True:
            b = f.read(1)
            if not b:
                return None
            if b != b"\xff":
                continue
            m = f.read(1)
            while m == b"\xff":
                m = f.read(1)
            if not m or m[0] in (0x00, 0x01) or 0xD0 <= m[0] <= 0xD9:
                continue
            seg = f.read(2)
            if len(seg) < 2:
                return None
            n = struct.unpack(">H", seg)[0]
            if m[0] in SOF:
                body = f.read(5)
                if len(body) < 5:
                    return None
                h, w = struct.unpack(">HH", body[1:5])
                return w, h
            f.seek(n - 2, 1)


def check_images(folder):
    """Technical gate for a folder of final JPEGs. Returns per-file facts and a list of problems."""
    d = Path(folder)
    if not d.is_dir():
        raise StageError("folder not found")
    files, problems, by_sha = [], [], {}
    for p in sorted(d.iterdir()):
        if p.suffix.lower() not in (".jpg", ".jpeg"):
            continue
        size = p.stat().st_size
        dims = jpeg_size(p)
        sha = sha256_file(p)
        row = {"name": p.name, "sha256": sha, "bytes": size, "width": dims[0] if dims else None, "height": dims[1] if dims else None}
        if dims is None:
            problems.append(f"{p.name}: not a readable JPEG")
        else:
            mp = dims[0] * dims[1] / 1e6
            row["megapixels"] = round(mp, 2)
            if not MIN_MP <= mp <= MAX_MP:
                problems.append(f"{p.name}: {mp:.1f} MP, Adobe needs {MIN_MP:g}-{MAX_MP:g} MP")
        if size > MAX_MB * 1024 * 1024:
            problems.append(f"{p.name}: {size / 1048576:.1f} MB, Adobe allows {MAX_MB} MB")
        if sha in by_sha:
            problems.append(f"{p.name}: exact duplicate of {by_sha[sha]}")
        by_sha.setdefault(sha, p.name)
        files.append(row)
    if not files:
        problems.append("no .jpg files in the folder")
    return {"ok": not problems, "count": len(files), "files": files, "problems": problems}


def lint_registry(path, max_title=200, min_keywords=5, max_keywords=49):
    """Check a prompt/metadata registry: {"scenarios": {id: {prompt, title, keywords, category, ...}}}."""
    reg = json.loads(Path(path).read_text(encoding="utf-8"))
    sc = reg.get("scenarios") if isinstance(reg, dict) else None
    if not isinstance(sc, dict) or not sc:
        return {"ok": False, "problems": ["registry needs a non-empty 'scenarios' object keyed by scenario id"], "count": 0}
    problems, warnings = [], []
    ids = list(sc)
    for a in ids:
        for b in ids:
            if a != b and a in b:
                problems.append(f"id '{a}' is contained in '{b}': file names could match both")
    for sid, s in sc.items():
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", sid):
            problems.append(f"{sid}: id must be lowercase letters, digits and dashes")
        title, kws = str(s.get("title", "")).strip(), s.get("keywords")
        if not title or len(title) > max_title:
            problems.append(f"{sid}: title empty or over {max_title} characters")
        if not isinstance(kws, list) or not min_keywords <= len(kws) <= max_keywords or len({str(k).lower() for k in kws}) != len(kws):
            problems.append(f"{sid}: need {min_keywords}-{max_keywords} unique keywords")
        if not isinstance(s.get("category"), int):
            problems.append(f"{sid}: category must be Adobe's numeric code")
        if TITLE_AI_WORDS.search(title):
            problems.append(f"{sid}: title mentions AI or a model name (tick the portal's generative AI box instead)")
        if isinstance(kws, list) and kws:
            tw = set(re.findall(r"[a-z]{3,}", title.lower()))
            kw0 = set(re.findall(r"[a-z]{3,}", str(kws[0]).lower()))
            if not any(x == y or x.startswith(y) or y.startswith(x) for x in tw for y in kw0):
                problems.append(f"{sid}: first keyword '{kws[0]}' shares no word with the title")
        warnings.extend(_soft_seo(sid, title, kws))
        prompt = str(s.get("prompt", ""))
        if len(prompt) < 40:
            problems.append(f"{sid}: prompt missing or too short")
        for pat, negatable in BAD_PROMPT:
            for m in re.finditer(pat, prompt, re.I):
                if not (negatable and NEGATION_OK.search(prompt[:m.start()][-60:])):
                    problems.append(f"{sid}: prompt contains '{m.group(0)}'")
    return {"ok": not problems, "count": len(sc), "problems": problems, "warnings": warnings,
            "note": "warnings are soft SEO conventions (knowledge topic metadata-seo); breaking one is allowed with a reason"}


CAMERA_SPEC = re.compile(r"\b(\d+k|uhd|hdr|iso ?\d*|f/?\d+(\.\d+)?|\d+ ?mm|dslr|canon|nikon|sony|fujifilm|leica)\b", re.I)


def _soft_seo(sid, title, kws):
    """Soft conventions from the community (warnings only): title <= 70, 15-35 keywords, title nouns in keywords 1-10, no camera specs."""
    out = []
    if len(title) > 70:
        out.append(f"{sid}: title is {len(title)} characters (about 70 or fewer reads best)")
    if isinstance(kws, list):
        if not 15 <= len(kws) <= 35:
            out.append(f"{sid}: {len(kws)} keywords (15-35 suggested)")
        top = " ".join(str(k).lower() for k in kws[:10])
        missing = [w for w in re.findall(r"[a-z]{4,}", title.lower()) if w not in STOP and w.rstrip("s") not in top]
        if missing:
            out.append(f"{sid}: title words not in keywords 1-10: {', '.join(sorted(set(missing)))}")
        spec = [str(k) for k in kws if CAMERA_SPEC.search(str(k))]
        if spec:
            out.append(f"{sid}: camera-spec keywords: {', '.join(spec)}")
    return out


STOP = {"with", "from", "into", "onto", "over", "under", "near", "their", "this", "that", "while", "during", "using", "beside", "behind", "front", "next", "and", "the", "for"}


def match_scenarios(registry, names):
    """Map each file name to one scenario id (the id must appear in the file name). Returns (mapping, problems)."""
    sc = registry["scenarios"]
    mapping, problems = {}, []
    for n in names:
        hits = [sid for sid in sc if re.search(r"(?<![a-z0-9])" + re.escape(sid) + r"(?![a-z0-9])", n.lower())]
        if not hits:
            problems.append(f"{n}: no scenario id appears in the file name")
        else:
            mapping[n] = max(hits, key=len)
    return mapping, problems


def build_csv(registry_path, folder, out_path, cfg_meta=None):
    """Write the Adobe upload CSV (Filename, Title, Keywords, Category, Releases) for the JPEGs in `folder`.
    Titles and keywords come from the registry: rewrite them from the final pixels before calling this."""
    reg = json.loads(Path(registry_path).read_text(encoding="utf-8"))
    names = [p.name for p in sorted(Path(folder).iterdir()) if p.suffix.lower() in (".jpg", ".jpeg")]
    mapping, problems = match_scenarios(reg, names)
    if problems:
        return {"ok": False, "problems": problems}
    cfg_meta = cfg_meta or {"max_title_chars": 200, "min_keywords": 5, "max_keywords": 49}
    out = Path(out_path)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Filename", "Title", "Keywords", "Category", "Releases"])
        for n in names:
            s = reg["scenarios"][mapping[n]]
            w.writerow([n, str(s["title"]).strip(), ",".join(str(k).strip() for k in s["keywords"]), s["category"], ""])
    try:
        _check_rows(out.read_text(encoding="utf-8"), names, cfg_meta)
    except StageError as e:
        return {"ok": False, "problems": [str(e)], "csv": str(out)}
    return {"ok": True, "csv": str(out), "rows": len(names), "sha256": sha256_file(out)}


def check_qc(qc_path, names_sha):
    """Validate a qc_decisions.json against {file name: sha256}. Rules: every image in `pass`, none in `fail`,
    `reviewer` and `mode` set; a recorded sha256 must equal the current bytes. Never write a QC record no reviewer produced."""
    q = json.loads(Path(qc_path).read_text(encoding="utf-8"))
    problems = []
    if not str(q.get("reviewer", "")).strip():
        problems.append("qc: reviewer not set")
    if q.get("mode") not in QC_MODES:
        problems.append(f"qc: mode must be one of {sorted(QC_MODES)}")
    passed, failed = set(q.get("pass") or []), set(q.get("fail") or [])
    if failed:
        problems.append(f"qc: {len(failed)} image(s) in fail: {sorted(failed)}")
        if not str(q.get("confirmed_by", "")).strip():
            problems.append("qc: fails need confirmed_by")
    missing = sorted(set(names_sha) - passed)
    if missing:
        problems.append(f"qc: not in pass: {missing}")
    extra = sorted(passed - set(names_sha))
    if extra:
        problems.append(f"qc: pass lists files not in the package: {extra}")
    for n, sha in (q.get("sha256") or {}).items():
        if n in names_sha and names_sha[n] != sha:
            problems.append(f"qc: {n} changed after review (sha256 differs)")
    return {"ok": not problems, "problems": problems}


def prepare_plan(folder, csv_path, qc_path, out_path, protected_markers=(), max_files=20):
    """Run every local gate and write the plan JSON that `upload-stage` / `upload-metadata` read.
    `ready_for_upload: true` means local gates passed; it is not Adobe acceptance."""
    d = Path(folder).resolve()
    failures = []
    if any(m.lower() in str(d).lower() for m in protected_markers):
        failures.append("folder is protected and can never be uploaded")
    img = check_images(d)
    failures += img["problems"]
    if img["count"] > max_files:
        failures.append(f"{img['count']} files; staging takes at most {max_files} per wave: split the package into waves")
    names_sha = {f["name"]: f["sha256"] for f in img["files"]}
    c = Path(csv_path).resolve()
    if c.parent != d:
        failures.append("the CSV must sit directly in the package folder")
        csv_ok = False
    else:
        try:
            _check_rows(c.read_text(encoding="utf-8-sig"), list(names_sha), {"max_title_chars": 200, "min_keywords": 5, "max_keywords": 49})
            csv_ok = True
        except (StageError, OSError) as e:
            failures.append(f"csv: {e}")
            csv_ok = False
    failures += check_qc(qc_path, names_sha)["problems"]
    digest = hashlib.sha256(("\n".join(f"{n}:{s}" for n, s in sorted(names_sha.items())) + ("\ncsv:" + sha256_file(c) if csv_ok else "")).encode()).hexdigest()
    plan = {"kind": "adobe_stock_upload_plan", "ready_for_upload": not failures, "failures": failures, "package_digest": digest,
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "folder": str(d),
            "files": [{"path": str(d / f["name"]), "sha256": f["sha256"]} for f in img["files"]],
            "csv": [{"path": str(c), "sha256": sha256_file(c)}] if csv_ok else [],
            "note": "Local gates only. Not Adobe acceptance and not visual approval beyond the recorded QC."}
    Path(out_path).write_text(json.dumps(plan, indent=1), encoding="utf-8")
    return {"ok": not failures, "plan": str(out_path), "ready_for_upload": not failures, "failures": failures, "files": len(img["files"])}


def qc_tiles(image_path, out_dir, grid=3, frame_px=1600):
    """Optional (needs Pillow): write a 1600 px full frame and grid x grid native-resolution tiles for visual QC."""
    try:
        from PIL import Image
    except ImportError:
        raise SystemExit("qc-tiles needs Pillow: python3 -m pip install Pillow (everything else here is stdlib)")
    im = Image.open(image_path).convert("RGB")
    out = Path(out_dir) / Path(image_path).stem
    out.mkdir(parents=True, exist_ok=True)
    full = im.copy()
    full.thumbnail((frame_px, frame_px))
    full.save(out / "frame.jpg", quality=92)
    w, h = im.size
    paths = [str(out / "frame.jpg")]
    for r in range(grid):
        for c in range(grid):
            t = im.crop((c * w // grid, r * h // grid, (c + 1) * w // grid, (r + 1) * h // grid))
            p = out / f"r{r + 1}c{c + 1}.jpg"
            t.save(p, quality=92)
            paths.append(str(p))
    return {"image": str(image_path), "size": [w, h], "files": paths}


GENERATION_QUESTIONS = {
    "provider": "Which image generator or route? (for example an image API, a chat-based bridge, Codex image gen, Google Flow, a local model; any other is fine)",
    "model": "Which model, mode or effort?",
    "account": "Which account, key or profile may be used? (name only, never the secret)",
    "scenario_count": "How many scenarios (images) in this run?",
    "variants": "How many outputs per prompt? (suggested: 1; Adobe wants distinct concepts, not many outputs of one prompt)",
    "size": "Which aspect ratio and size?",
    "output_folder": "Which folder receives the raw output? (suggested: runs/<RUN>/raw)",
    "spend": "May this run spend money or quota? Up to how much?",
    "terms": "Do the provider's terms allow commercial stock use? (user has checked)",
    "canary": "How many images in the first canary before the rest?",
    "on_failure": "If a scenario fails: skip, write a new concept, or stop?",
    "go_ahead": "Explicit go-ahead to start live generation for this run?",
}


COUNT_KEYS = ("scenario_count", "variants", "canary")
YES_KEYS = ("terms", "go_ahead")
YES = ("yes", "true", "go", "y")
NOT_ANSWERS = ("", "unknown", "?", "tbd", "n/a", "none yet", "undecided", "not sure", "ask later", "later")


def _answered(key, v):
    """True when v is a real answer: counts are positive whole numbers, spend is a finite number >= 0 or a word,
    terms/go_ahead are yes-like; never a container, an 'unknown' phrase or 'I do not know'."""
    if key in YES_KEYS and v is True:
        return True
    if v is None or isinstance(v, (bool, list, dict)):
        return False
    text = str(v).strip().lower()
    if text in NOT_ANSWERS or "know" in text and ("not" in text or "n't" in text or "dunno" in text):
        return False
    if key in COUNT_KEYS:
        try:
            f = float(text)
        except ValueError:
            return False
        return f == int(f) and f > 0 if f == f and abs(f) != float("inf") else False
    if key == "spend":
        try:
            f = float(text)
            return f == f and abs(f) != float("inf") and f >= 0
        except ValueError:
            return True
    if key in YES_KEYS:
        return text in YES or text in ("no", "false", "n")  # a clear no is an answer; check_decisions turns it into a problem
    return isinstance(v, str)


def check_decisions(path):
    """A generation_decisions.json passes only when every question has a value, dated and labelled as decided by the user.
    It records answers; it cannot prove who typed them. Open items are listed to ask."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    items = data.get("decisions") if isinstance(data, dict) else None
    if not isinstance(items, dict):
        raise ValueError('expected {"decisions": {<key>: {"value", "decided_by", "asked_on"}}}')
    open_items, problems = [], []
    for key, question in GENERATION_QUESTIONS.items():
        d = items.get(key)
        if not isinstance(d, dict) or not _answered(key, d.get("value")):
            open_items.append({"key": key, "ask": question})
            continue
        if str(d.get("decided_by", "")).strip().lower() != "user":
            problems.append(f"{key}: decided_by must be 'user' (the agent never decides); ask again")
        try:
            if date.fromisoformat(str(d.get("asked_on", ""))) > date.today():
                problems.append(f"{key}: asked_on is in the future")
        except ValueError:
            problems.append(f"{key}: asked_on must be a real date YYYY-MM-DD")
        if key in YES_KEYS and str(d.get("value")).strip().lower() not in YES:
            problems.append(f"{key}: value must be yes; anything else means do not generate")
    return {"ok": not open_items and not problems, "open": open_items, "problems": problems,
            "note": "ok means every item has a dated answer labelled as the user's; it records answers and cannot prove who gave them. It is not a quality or Adobe result"}
