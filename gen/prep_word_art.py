#!/usr/bin/env python3
"""Crops the generated word-scene renders to their content and shrinks them.

art/gen/words/<name>.png  ->  art/words/<name>.png  (+ art/words/sizes.json)
"""
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "art" / "gen" / "words"
DST = ROOT / "art" / "words"
MAX_SIDE = 256
# frames that swap in place must share one crop
SHARED_CROP = {"cat": ["cat", "cat_closed"]}

DST.mkdir(parents=True, exist_ok=True)


def content_box(im):
    return im.getchannel("A").point(lambda a: 255 if a > 24 else 0).getbbox()


shared = {}
for group in SHARED_CROP.values():
    boxes = [content_box(Image.open(SRC / f"{n}.png").convert("RGBA")) for n in group]
    union = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
    shared.update({n: union for n in group})

sizes = {}
for src in sorted(SRC.glob("*.png")):
    if src.stem in ("sheet", "cats"):
        continue
    im = Image.open(src).convert("RGBA")
    im = im.crop(shared.get(src.stem) or content_box(im))
    im.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    im.save(DST / src.name, optimize=True)
    sizes[src.stem] = im.size
    print(f"{src.stem:8s} {im.size}")
(DST / "sizes.json").write_text(json.dumps(sizes, indent=1))
