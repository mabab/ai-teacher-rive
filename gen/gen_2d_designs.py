#!/usr/bin/env python3
"""Character design options for the 2D teacher (head and shoulders, front view, neutral friendly face,
closed mouth: the base for a cut-out rig). OpenAI gpt-image-1.5.
Output: art2d/designs/<name>.png. Run: python3 gen/gen_2d_designs.py [name ...]
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
COMMON = ("Character design of a friendly young female English teacher for kids aged 6-10, head and shoulders, front "
          "view, looking straight at the viewer, head upright and centred, a warm closed-mouth smile, eyes open, the "
          "whole head with some margin in frame, cut at mid-chest. Appealing, kind, trustworthy, clearly an adult "
          "teacher (not a child). Plain pure white background, no text, no logos.")
DESIGNS = {
    "pixar": "Stylised 3D animated-film look with soft clay shading: chestnut hair in a high messy bun with two loose strands, round thin dark glasses, freckles, teal sweater over a white shirt collar.",
    "flat": "Clean flat 2D vector cartoon illustration with bold smooth outlines and cel shading, like a modern kids' TV show: chestnut hair in a high bun with two loose strands, round dark glasses, rosy cheeks, teal sweater over a white collar.",
    "brand": "Polished 2D cartoon illustration with soft gradients, a modern edtech mascot feel: wavy shoulder-length dark-brown hair with a purple hair clip, big expressive eyes, round glasses, a soft purple cardigan (#6a50ec) over a white top, a small star-shaped badge.",
    "storybook": "Warm 2D storybook illustration with gentle painted textures and soft line art: auburn hair in a loose low braid over one shoulder, round tortoiseshell glasses, a mustard-yellow cardigan over a white blouse, a small pencil behind her ear.",
}


def gen(name):
    out = ROOT / "art2d" / "designs" / f"{name}.png"
    if out.exists():
        return f"skip {name}"
    body = json.dumps({"model": "gpt-image-1.5", "prompt": f"{COMMON} {DESIGNS[name]}", "size": "1024x1024", "quality": "high"}).encode()
    req = urllib.request.Request("https://api.openai.com/v1/images/generations", data=body,
                                 headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=400) as r:
            d = json.load(r)
    except urllib.error.HTTPError as e:
        return f"FAIL {name} {e.code} {e.read()[:200]}"
    out.write_bytes(base64.b64decode(d["data"][0]["b64_json"]))
    return f"ok {name}"


if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=4) as pool:
        for line in pool.map(gen, sys.argv[1:] or list(DESIGNS)):
            print(line, flush=True)
