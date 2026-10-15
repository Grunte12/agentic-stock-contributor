"""Upscale raws with Real-ESRGAN (realesrgan-ncnn-vulkan, model realesrgan-x4plus), then resize to the long edge and save JPEG.

This is the route the authoring account used for its 2026 batches. It never falls back to a plain resize, never overwrites,
and writes nothing without confirm_write. The final resize needs Pillow.
"""
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

BIN = "realesrgan-ncnn-vulkan"
EXTS = (".png", ".jpg", ".jpeg", ".webp")
OPTIONS = ("realesrgan-ncnn-vulkan (free, local, no Python; github.com/xinntao/Real-ESRGAN releases): what this project used",
           "Upscayl (free desktop app with Real-ESRGAN-family models): easiest without a terminal; run it yourself, then check-images",
           "Topaz Gigapixel or Photoshop (paid): community suggestions, not tested by this project")


def find_binary(binary=None):
    if binary:
        p = Path(binary).expanduser()
        return str(p) if p.is_file() else None
    return shutil.which(BIN)


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def run(src_dir, out_dir, binary=None, long_edge=3840, quality=95, model="realesrgan-x4plus", confirm_write=False):
    src, out = Path(src_dir).expanduser(), Path(out_dir).expanduser()
    if not src.is_dir():
        raise ValueError(f"source folder not found: {src}")
    exe = find_binary(binary)
    if not exe:
        return {"ok": False, "reason": f"{BIN} not found (pass --bin PATH or put it on PATH)", "options": OPTIONS,
                "note": "ask the user which upscaler to use; installing one needs their yes. Never replace it with a plain resize."}
    todo, skip = [], []
    for f in sorted(src.iterdir()):
        if f.suffix.lower() in EXTS:
            dst = out / f"{f.stem}.jpg"
            (skip if dst.exists() else todo).append((f, dst))
    plan = {"binary": exe, "model": model, "long_edge": long_edge, "quality": quality, "out": str(out),
            "to_upscale": [f.name for f, _ in todo], "already_done": [d.name for _, d in skip]}
    if not confirm_write:
        return {"ok": True, "written": False, **plan, "note": "dry run: nothing written; add --confirm-write after the user agreed"}
    try:
        from PIL import Image
    except ImportError:
        return {"ok": False, "reason": "the final resize needs Pillow: python3 -m pip install Pillow (ask the user first)"}
    out.mkdir(parents=True, exist_ok=True)
    models = Path(exe).parent / "models"
    done, failed = [], []
    for f, dst in todo:
        with tempfile.TemporaryDirectory() as tmp:
            mid = Path(tmp) / "x4.png"
            cmd = [exe, "-i", str(f), "-o", str(mid), "-n", model, "-s", "4"] + (["-m", str(models)] if models.is_dir() else [])
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode or not mid.is_file():
                failed.append({"file": f.name, "error": (r.stderr or r.stdout or f"exit {r.returncode}").strip()[-300:]})
                continue
            with Image.open(mid) as im:
                im = im.convert("RGB")
                w, h = im.size
                edge = long_edge or max(w, h)  # 0 keeps the full x4 size
                if max(w, h) < edge:
                    failed.append({"file": f.name, "error": f"upscaled size {w}x{h} is below the {long_edge} px target; not stretched"})
                    continue
                k = edge / max(w, h)
                if k != 1:
                    im = im.resize((round(w * k), round(h * k)), Image.LANCZOS)
                part = dst.with_name(dst.name + ".part")
                im.save(part, "JPEG", quality=quality)
            part.replace(dst)
            done.append({"file": dst.name, "source": f.name, "size": [round(w * k), round(h * k)], "sha256": _sha(dst)})
    manifest = out / "upscale_manifest.json"
    old = json.loads(manifest.read_text()) if manifest.is_file() else {"files": []}
    old["files"] += [{**d, "backend": f"{BIN} {model}", "long_edge": long_edge, "quality": quality} for d in done]
    manifest.write_text(json.dumps(old, indent=1))
    return {"ok": not failed, "written": True, **plan, "done": done, "failed": failed, "manifest": str(manifest),
            "note": "next: check-images on the out folder, then visual QC of the finals (knowledge topic qc-upscale)"}
