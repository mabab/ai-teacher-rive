#!/usr/bin/env python3
"""Reference image for the 3D model: the teacher full body, front view, A-pose, neutral face,
on plain white (what image-to-3D generators read best). Face from art/src/head_1.png.
Output: model/ref_<n>.png. Run: python3 gen/gen_model_ref.py [n ...]
"""
import base64
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEY = os.environ.get("OPENAI_API_KEY") or re.search(r"^OPENAI_API_KEY=(.*)$", Path(os.environ.get(
    "OPENAI_ENV_FILE", "/Users/mabab/projects/allright/backend/env/.env")).read_text(), re.M).group(1).strip().strip("\"'")
PROMPT = (
    "Character turnaround reference for a 3D model: the woman from the reference image (same face shape, same "
    "round thin dark glasses, same chestnut-brown hair in a high bun with two loose strands, same freckles and "
    "small gold stud earrings), now with eyes open, gentle eyebrows and a soft closed-mouth smile. Full body, "
    "standing perfectly straight, FRONT view, symmetrical A-POSE: arms straight and held about 30 degrees away "
    "from the body, palms facing the thighs, fingers together, legs slightly apart, feet flat. She wears a teal "
    "crew-neck sweater over a white shirt collar, navy straight trousers and white sneakers. Stylised 3D cartoon "
    "look of a modern kids' learning app, soft clay shading, even studio light, no strong shadows. Plain pure "
    "white background, the whole figure in frame with margin, no props, no text. {v}"
)
VARIANTS = {"1": "", "2": "Slightly chunkier cartoon proportions, a slightly larger head."}


def gen(n):
    out = ROOT / "model" / f"ref_{n}.png"
    if out.exists():
        return f"skip {n}"
    r = subprocess.run(
        ["curl", "-s", "https://api.openai.com/v1/images/edits", "-H", f"Authorization: Bearer {KEY}",
         "-F", "model=gpt-image-1.5", "-F", f"prompt={PROMPT.format(v=VARIANTS[n])}", "-F", "size=1024x1536",
         "-F", "quality=high", "-F", f"image[]=@{ROOT / 'art' / 'src' / 'head_1.png'}"],
        capture_output=True, text=True, timeout=500)
    d = json.loads(r.stdout)
    if "error" in d:
        return f"FAIL {n} {d['error'].get('message', '')[:200]}"
    out.write_bytes(base64.b64decode(d["data"][0]["b64_json"]))
    return f"ok {n}"


if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=2) as pool:
        for line in pool.map(gen, sys.argv[1:] or list(VARIANTS)):
            print(line, flush=True)
