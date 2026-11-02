#!/usr/bin/env python3
"""2D cutout teacher: one bust illustration (the base) and edits of it that change only the
mouth or the eyes, so the parts can be cut out and layered in Rive. OpenAI gpt-image-1.5,
input_fidelity high to keep everything else identical.
Run: python3 gen/gen_2d_bust.py base | mouths | eyes   (existing files are skipped)
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
OUT = ROOT / "art2d"
KEY = os.environ.get("OPENAI_API_KEY") or re.search(r"^OPENAI_API_KEY=(.*)$", Path(os.environ.get(
    "OPENAI_ENV_FILE", "/Users/mabab/projects/allright/backend/env/.env")).read_text(), re.M).group(1).strip().strip("\"'")

BASE = ("Head-and-shoulders portrait of the woman from the reference image, exactly the same character and art style "
        "(same face, same round thin dark glasses, same chestnut hair in a high bun with two loose strands, same "
        "freckles and gold stud earrings, teal crew-neck sweater over a white shirt collar). Front view, looking "
        "straight at the viewer, head upright and centred, a friendly closed-mouth smile, eyes open. The bun fully in "
        "frame at the top with some margin; the frame cut at mid-chest. Stylised 3D cartoon look, soft even light. "
        "Plain pure white background, no text.")
MOUTHS = {
    "rest": "lips closed in a gentle relaxed smile",
    "mbp": "lips pressed together flat, as when saying 'm' or 'b'",
    "fv": "upper teeth lightly touching the lower lip, as when saying 'f'",
    "dt": "mouth slightly open, teeth a little apart, tongue tip behind the upper teeth, as when saying 't'",
    "aa": "mouth wide open, jaw dropped, as when saying 'ah'",
    "ee": "mouth wide and stretched sideways with teeth showing, as when saying 'ee'",
    "oh": "lips rounded into an open 'o', as when saying 'oh'",
    "oo": "lips pushed forward into a small round pucker, as when saying 'oo'",
    "ch": "teeth together, lips slightly open and pushed forward, as when saying 'sh'",
}
EYES = {"closed": "both eyes gently closed as in a blink, eyelids down with lashes", "half": "both eyes half closed, upper lids halfway down"}


def edit(prompt, src, out):
    if out.exists():
        return f"skip {out.name}"
    r = subprocess.run(
        ["curl", "-s", "https://api.openai.com/v1/images/edits", "-H", f"Authorization: Bearer {KEY}",
         "-F", "model=gpt-image-1.5", "-F", f"prompt={prompt}", "-F", "size=1024x1024", "-F", "quality=high",
         "-F", "input_fidelity=high", "-F", f"image[]=@{src}"],
        capture_output=True, text=True, timeout=500)
    d = json.loads(r.stdout)
    if "error" in d:
        return f"FAIL {out.name} {d['error'].get('message', '')[:160]}"
    out.write_bytes(base64.b64decode(d["data"][0]["b64_json"]))
    return f"ok {out.name}"


def change(what):
    return (f"Exactly the same image, pixel-identical in every other way: same pose, framing, size, position, lighting, "
            f"hair, glasses and clothes. Change ONLY {what}. Nothing else moves.")


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    job = sys.argv[1] if len(sys.argv) > 1 else "base"
    base = OUT / "base.png"
    if job == "base":
        print(edit(BASE, ROOT / "model" / "ref_1.png", base))
    else:
        items = MOUTHS if job == "mouths" else EYES
        kind = "mouth" if job == "mouths" else "eyes"
        tasks = [(change(f"the mouth: {d}") if kind == "mouth" else change(f"the eyes: {d}"), base, OUT / f"{kind}_{k}.png")
                 for k, d in items.items()]
        with ThreadPoolExecutor(max_workers=5) as pool:
            for line in pool.map(lambda t: edit(*t), tasks):
                print(line, flush=True)
