"""Look-alike screen (needs Pillow): 8x8 average hash per image, pairs within a Hamming distance, and groups of near-variants.

A proxy only. Adobe's similarity check is not visible; a clean screen is not clearance and a flagged pair is a review item,
not a forecast. Compare new finals against everything already submitted, including files whose upload state is unknown.
"""
from pathlib import Path

EXTS = (".jpg", ".jpeg", ".png", ".webp")


def ahash(path, size=8):
    from PIL import Image, ImageOps
    with Image.open(path) as im:
        g = ImageOps.exif_transpose(im).convert("L").resize((size, size), Image.LANCZOS)
        pixels = getattr(g, "get_flattened_data", g.getdata)
        px = list(pixels())
    mean = sum(px) / len(px)
    return sum(1 << i for i, v in enumerate(px) if v >= mean)


def _files(folder):
    d = Path(folder).expanduser()
    if not d.is_dir():
        raise ValueError(f"folder not found: {d}")
    return sorted(p for p in d.rglob("*") if p.suffix.lower() in EXTS and p.is_file())


def screen(folder, against=(), threshold=8, max_group=3):
    try:
        import PIL  # noqa: F401
    except ImportError:
        return {"ok": False, "reason": "needs Pillow: python3 -m pip install Pillow (ask the user first)"}
    new = [(p, "new") for p in _files(folder)]
    old = [(p, "earlier") for a in against for p in _files(a)]
    hashes = [(str(p), src, ahash(p)) for p, src in new + old]
    pairs, parent = [], list(range(len(hashes)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i in range(len(hashes)):
        for j in range(i + 1, len(hashes)):
            a, b = hashes[i], hashes[j]
            if a[1] == b[1] == "earlier":
                continue
            d = bin(a[2] ^ b[2]).count("1")
            if d <= threshold:
                pairs.append({"a": a[0], "b": b[0], "distance": d, "kind": "within_new" if a[1] == b[1] else "new_vs_earlier"})
                parent[root(i)] = root(j)
    groups = {}
    for i, h in enumerate(hashes):
        groups.setdefault(root(i), []).append(h[0])
    big = [g for g in groups.values() if len(g) > max_group]
    return {"ok": True, "new_files": len(new), "earlier_files": len(old), "threshold": threshold,
            "pairs": sorted(pairs, key=lambda p: p["distance"]), "groups_over_max": big,
            "note": ("Average-hash proxy, not Adobe's check. For each pair: keep the stronger image, or put the two in different "
                     "waves after a human look; a pair with an earlier file means a new image may repeat one already submitted. "
                     f"Groups over {max_group} near-variants of one concept go to the user (one source cites Adobe's GenAI FAQ for "
                     "at most 3 similar iterations per concept). Never drop files automatically.")}
