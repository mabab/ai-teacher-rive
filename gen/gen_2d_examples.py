#!/usr/bin/env python3
"""Expression examples for each design option: talking, blinking, listening. Edits of
art2d/designs/<name>.png. Output: art2d/designs/<name>_<pose>.png
Run: python3 gen/gen_2d_examples.py
"""
import base64
import json
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "art2d" / "designs"
KEY = os.environ.get("OPENAI_API_KEY") or re.search(r"^OPENAI_API_KEY=(.*)$", Path(os.environ.get(
    "OPENAI_ENV_FILE", "/Users/mabab/projects/allright/backend/env/.env")).read_text(), re.M).group(1).strip().strip("\"'")
KEEP = ("Exactly the same image, pixel-identical in every other way: same character, art style, pose, framing, size, "
        "position, lighting, hair, glasses, clothes and plain white background. ")
POSES = {
    "talk": KEEP + "Change ONLY the mouth: open it wide as when saying 'ah', showing the upper teeth and the inside of the mouth.",
    "blink": KEEP + "Change ONLY the eyes: both eyes fully closed, upper eyelids down, lashes resting on the cheeks, as in a blink.",
    "listen": KEEP + "Change ONLY her right arm and head: she raises her right hand and cups it right behind her right ear, palm "
              "forward, as if trying to hear better, and tilts her head slightly toward that hand with a curious smile.",
}


def edit(args):
    name, pose = args
    out = D / f"{name}_{pose}.png"
    if out.exists():
        return f"skip {out.name}"
    r = subprocess.run(["curl", "-s", "https://api.openai.com/v1/images/edits", "-H", f"Authorization: Bearer {KEY}",
                        "-F", "model=gpt-image-1.5", "-F", f"prompt={POSES[pose]}", "-F", "size=1024x1024",
                        "-F", "quality=high", "-F", "input_fidelity=high", "-F", f"image[]=@{D / (name + '.png')}"],
                       capture_output=True, text=True, timeout=500)
    d = json.loads(r.stdout)
    if "error" in d:
        return f"FAIL {out.name} {d['error'].get('message', '')[:160]}"
    out.write_bytes(base64.b64decode(d["data"][0]["b64_json"]))
    return f"ok {out.name}"


if __name__ == "__main__":
    jobs = [(n, p) for n in ("pixar", "flat", "brand", "storybook") for p in POSES]
    with ThreadPoolExecutor(max_workers=6) as pool:
        for line in pool.map(edit, jobs):
            print(line, flush=True)
