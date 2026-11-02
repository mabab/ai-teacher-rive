#!/usr/bin/env python3
"""Generates the teacher's head render (no eyes, brows or mouth: the rig draws
those) with OpenAI gpt-image-1.5. Output: art/src/head_<n>.png.
Run: python3 gen/gen_teacher_art.py [n ...]
"""
import base64
import json
import os
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEY = os.environ.get("OPENAI_API_KEY") or re.search(r"^OPENAI_API_KEY=(.*)$", Path(os.environ.get(
    "OPENAI_ENV_FILE", "/Users/mabab/projects/allright/backend/env/.env")).read_text(), re.M).group(1).strip().strip("\"'")

PROMPT = (
    "Front view of the head only (cut off just under the chin, no neck, no shoulders) of a friendly young woman "
    "who is an English teacher for kids. Stylised 3D cartoon look of a modern kids' learning app: soft clay-like "
    "shading, warm key light from the top left, gentle rim light, smooth matte skin. {variant} "
    "IMPORTANT: the face has NO eyes, NO eyebrows and NO mouth - only smooth blank skin where they would be, "
    "because eyes, brows and mouth are animated separately and drawn on top later. Keep a small cute nose and soft "
    "pink blush on the cheeks. Perfectly symmetric, looking straight at the viewer, centred, the head filling most "
    "of the square, plain transparent background, no text."
)
VARIANTS = {
    "1": "Warm light skin with a few freckles, chestnut-brown hair in a neat high bun with two loose strands framing the face, small ears with tiny gold stud earrings.",
    "2": "Warm medium-tan skin, dark brown wavy hair in a short rounded bob with a side fringe, small ears.",
    "3": "Fair skin, copper-red hair tied in a soft low ponytail hidden behind the head, a yellow pencil tucked behind one ear, small ears.",
}


def gen(n):
    out = ROOT / "art" / "src" / f"head_{n}.png"
    if out.exists():
        return f"skip {n}"
    body = json.dumps({"model": "gpt-image-1.5", "prompt": PROMPT.format(variant=VARIANTS[n]), "size": "1024x1024",
                       "background": "transparent", "quality": "high"}).encode()
    req = urllib.request.Request("https://api.openai.com/v1/images/generations", data=body,
                                 headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            d = json.load(r)
    except urllib.error.HTTPError as e:
        return f"FAIL {n} {e.code} {e.read()[:300]}"
    out.write_bytes(base64.b64decode(d["data"][0]["b64_json"]))
    return f"ok {n}"


if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=3) as pool:
        for line in pool.map(gen, sys.argv[1:] or list(VARIANTS)):
            print(line, flush=True)
