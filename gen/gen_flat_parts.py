#!/usr/bin/env python3
"""Parts for the flat 2D teacher (art2d/designs/flat.png): mouth shapes and eye states that change
only the mouth / eyes (cut out and layered in Rive), plus whole-pose images for some states.
OpenAI gpt-image-1.5 edits with input_fidelity high. Output: art2d/flat/<name>.png
Run: python3 gen/gen_flat_parts.py [name ...]
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
BASE = ROOT / "art2d" / "designs" / "flat.png"
SOURCES = {"lw_closed": "p_listen", "w_alt": "p_wave"}     # parts edited from a pose image instead of the base
OUT = ROOT / "art2d" / "flat"
KEY = os.environ.get("OPENAI_API_KEY") or re.search(r"^OPENAI_API_KEY=(.*)$", Path(os.environ.get(
    "OPENAI_ENV_FILE", "/Users/mabab/projects/allright/backend/env/.env")).read_text(), re.M).group(1).strip().strip("\"'")
KEEP = ("Exactly the same image, pixel-identical in every other way: same character, flat cartoon style with the same "
        "outlines, same pose, framing, size, position, hair, glasses, clothes and plain white background. ")
MOUTH = (KEEP + "Change ONLY the mouth, drawn in the same flat style with the same outline: {}. The jaw, chin and face "
         "outline stay exactly where they are; the whole mouth fits inside the face, well above the chin line.")
ARM = (KEEP.replace("same pose, ", "") + "Her head, face, hair, glasses, expression and body stay EXACTLY the same and in exactly the same place. "
       "Change ONLY her arm: ")
PARTS = {
    "m_rest": MOUTH.format("lips closed in a gentle relaxed smile"),
    "m_mbp": MOUTH.format("lips pressed together in a flat closed line, as when saying 'm'"),
    "m_fv": MOUTH.format("upper teeth resting on the lower lip, as when saying 'f'"),
    "m_dt": MOUTH.format("slightly open, teeth a little apart, as when saying 't'"),
    "m_aa": MOUTH.format("open, a rounded opening about as tall as it is wide and no bigger than the eye, upper teeth and the tongue visible, as when saying 'ah'; the face shape and size are unchanged"),
    "m_ee": MOUTH.format("wide and stretched sideways showing both rows of teeth, as when saying 'ee'"),
    "m_oh": MOUTH.format("rounded open 'o' shape, as when saying 'oh'"),
    "m_oo": MOUTH.format("small round pucker pushed forward, as when saying 'oo'"),
    "m_ch": MOUTH.format("teeth together with lips slightly open and pushed forward, as when saying 'sh'"),
    "e_closed": KEEP + "She still wears the same round dark glasses, unchanged. Change ONLY the eyes behind the lenses: both eyes fully closed as in a blink, drawn as curved lash lines.",
    "e_half": KEEP + "Change ONLY the eyes: both upper eyelids halfway down, a relaxed half-closed look.",
    "p_listen": KEEP.replace("same pose, ", "") + "She raises her right hand and cups it behind her right ear, palm forward, "
                "trying to hear better, head tilted slightly toward that hand, curious friendly smile.",
    "p_read": KEEP.replace("same pose, ", "") + "She holds an open picture book in both hands in front of her chest and reads "
              "it, eyes looking down at the pages, a calm content smile. The book cover is purple.",
    "g_palm": KEEP.replace("same pose, ", "") + "Her head, face, hair, glasses and expression stay EXACTLY the same. Change ONLY her right arm: she raises her right hand in front of her chest, palm open and turned up, an explaining gesture, the hand below her chin.",
    "g_both": KEEP.replace("same pose, ", "") + "Her head, face, hair, glasses and expression stay EXACTLY the same. Change ONLY her arms: both hands raised in front of her chest, palms open and up, a welcoming explaining gesture, hands below her chin.",
    "g_thumb": KEEP.replace("same pose, ", "") + "Her head, face, hair, glasses and expression stay EXACTLY the same. Change ONLY her right arm: a thumbs-up with her right hand in front of her chest, below her chin.",
    "g_count": KEEP.replace("same pose, ", "") + "Her head, face, hair, glasses and expression stay EXACTLY the same. Change ONLY her hands: in front of her chest she counts on her fingers, her right index finger touching her left hand, below her chin.",
    "e_left": KEEP + "Change ONLY the pupils: both eyes look to the viewer's left (pupils moved to the left side of the eyes).",
    "e_right": KEEP + "Change ONLY the pupils: both eyes look to the viewer's right (pupils moved to the right side of the eyes).",
    "e_up": KEEP + "Change ONLY the pupils: both eyes look up and slightly to the side, as when thinking.",
    "b_up": KEEP + "Change ONLY the eyebrows: both eyebrows raised a little higher, an interested, lively look.",
    "lw_closed": KEEP + "She still wears the same glasses. Change ONLY the eyes behind the lenses: both eyes fully closed as in a blink, drawn as curved lash lines.",
    "w_alt": KEEP + "Change ONLY her raised right hand: the same waving hand tilted the other way, about 25 degrees toward her head, fingers spread, as the next frame of a wave. Nothing else moves.",
    "a_listen": KEEP.replace("same pose, ", "") + "Her head, face, hair, glasses, expression and body stay EXACTLY the same and in exactly the same place, the head NOT tilted. Change ONLY her right arm (on the viewer's left): she raises her right hand and cups it behind her right ear, palm forward, as if listening carefully; the sleeve runs from the bottom edge of the picture up to the hand.",
    "a_read": KEEP.replace("same pose, ", "") + "Her head, face, hair, glasses, expression and shoulders stay EXACTLY the same and in exactly the same place. Change ONLY her hands: at the bottom of the picture, in front of her chest and well below her chin, she holds an open book with a purple cover in both hands, the pages facing her.",
    "e_down": KEEP + "Change ONLY the pupils: both eyes look down, as when reading a book held low.",
    # in-betweens (breakdowns) for the arm moves: the arm partway from hanging at her side to the key pose
    "i_listen1": ARM + "her right hand (on the viewer's right) has just come up from her side: the forearm raised in front of her shoulder, elbow bent and low, the open hand at the height of her collar, palm facing forward, fingers relaxed.",
    "i_listen2": ARM + "her right hand (on the viewer's right) is on its way to her ear: elbow bent and lifted outward, the open hand beside her jaw and neck, a little below and outside her right ear, palm forward, fingers slightly curved.",
    "i_wave1": ARM + "her right hand (on the viewer's right) is coming up to wave: the forearm rising beside her body, elbow bent, the open hand at the height of her shoulder, palm forward, fingers together.",
    "i_palm1": ARM + "on the RIGHT side of the picture, her hand is coming up from below: the forearm low in front of the right side of her body, the relaxed open hand near the bottom edge of the picture, palm up. Her other arm stays down.",
    "i_thumb1": ARM + "on the LEFT side of the picture, in front of her body (inside the outline of her sweater, not beside it), a loose fist is rising near the bottom edge of the picture, thumb starting to lift. Her other arm stays down.",
    "i_count1": ARM + "both hands are coming up from below: loosely open hands just entering the bottom of the picture, close together in front of her waist.",
    "i_both1": ARM + "both hands are coming up from below: relaxed open hands low at the bottom corners of the picture, palms turning up.",
    "p_wave": KEEP.replace("same pose, ", "") + "She waves hello with her right hand raised beside her head, a big happy smile, mouth closed.",
}


def edit(name):
    out = OUT / f"{name}.png"
    if out.exists():
        return f"skip {name}"
    r = subprocess.run(["curl", "-s", "https://api.openai.com/v1/images/edits", "-H", f"Authorization: Bearer {KEY}",
                        "-F", "model=gpt-image-1.5", "-F", f"prompt={PARTS[name]}", "-F", "size=1024x1024",
                        "-F", "quality=high", "-F", "input_fidelity=high", "-F", f"image[]=@{OUT / (SOURCES[name] + '.png') if name in SOURCES else BASE}"],
                       capture_output=True, text=True, timeout=500)
    d = json.loads(r.stdout)
    if "error" in d:
        return f"FAIL {name} {d['error'].get('message', '')[:160]}"
    out.write_bytes(base64.b64decode(d["data"][0]["b64_json"]))
    return f"ok {name}"


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=7) as pool:
        for line in pool.map(edit, sys.argv[1:] or list(PARTS)):
            print(line, flush=True)
