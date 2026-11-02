#!/usr/bin/env python3
"""Run-cycle frames one by one: each pose comes from the rig's own run (art/src/pose/pose_<i>.png,
anatomically right), and the image model redraws her in exactly that pose in the render's
style. Output: art/src/frames/frame_<i>.png. Run: python3 gen/gen_run_frames.py [i ...]
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
    "Image 1 is a rough pose guide of a running woman (side view, facing right). Redraw her in EXACTLY the same "
    "pose: the same angles of both thighs, knees, shins and feet, the same arm swing and elbow bend, the same "
    "torso lean and head position, the same overall size and placement in the frame. Make her look like the "
    "character in images 2 and 3: the same face, round thin dark glasses, chestnut-brown hair in a high bun with "
    "two loose strands, teal sweater with a white shirt collar, plus navy trousers and white sneakers, all in the "
    "same polished stylised 3D cartoon look with soft clay shading. Real natural arms and legs (no tubes), clean "
    "silhouette, full body visible. Plain transparent background, no shadow, no ground, no text."
)


def gen(i):
    out = ROOT / "art" / "src" / "frames" / f"frame_{i}.png"
    if out.exists():
        return f"skip {i}"
    r = subprocess.run(
        ["curl", "-s", "https://api.openai.com/v1/images/edits", "-H", f"Authorization: Bearer {KEY}",
         "-F", "model=gpt-image-1.5", "-F", f"prompt={PROMPT}", "-F", "size=1024x1024",
         "-F", "background=transparent", "-F", "quality=high", "-F", "input_fidelity=high",
         "-F", f"image[]=@{ROOT / 'art' / 'src' / 'pose' / f'pose_{i}.png'}",
         "-F", f"image[]=@{ROOT / 'art' / 'src' / 'torso_2.png'}",
         "-F", f"image[]=@{ROOT / 'art' / 'src' / 'head_1.png'}"],
        capture_output=True, text=True, timeout=500)
    d = json.loads(r.stdout)
    if "error" in d:
        return f"FAIL {i} {d['error'].get('message', '')[:200]}"
    out.write_bytes(base64.b64decode(d["data"][0]["b64_json"]))
    return f"ok {i}"


if __name__ == "__main__":
    (ROOT / "art" / "src" / "frames").mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=8) as pool:
        for line in pool.map(gen, [int(a) for a in sys.argv[1:]] or range(8)):
            print(line, flush=True)
