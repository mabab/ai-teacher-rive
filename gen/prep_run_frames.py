#!/usr/bin/env python3
"""Aligns the generated run frames (gen/gen_run_frames.py) into a sprite set: crops each to
the figure, scales them to one head size, and places them so the head stays put (the rig
adds the stride's bob). Output: art/run/f_<i>.png (same canvas) + art/run/frames.json.
Run: python3 gen/prep_run_frames.py
"""
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "art" / "src" / "frames"
OUT = ROOT / "art" / "run"
N = 8


def figure(im):
    a = np.array(im)
    lab, n = ndimage.label(a[:, :, 3] > 40)
    if n > 1:                                   # keep the figure, drop stray specks
        sizes = ndimage.sum(np.ones_like(lab), lab, range(1, n + 1))
        a[:, :, 3] *= (lab == 1 + int(np.argmax(sizes)))
    im = Image.fromarray(a)
    return im.crop(im.getchannel("A").point(lambda v: 255 if v > 40 else 0).getbbox())


def head_box(im):
    """Top of the bun, and the horizontal centre of the head (the top 28% of the figure)."""
    a = np.array(im)[:, :, 3] > 40
    h = int(im.height * 0.28)
    cols = np.where(a[:h].any(axis=0))[0]
    return cols.min(), cols.max()


if __name__ == "__main__":
    frames = [figure(Image.open(SRC / f"frame_{i}.png").convert("RGBA")) for i in range(N)]
    heads = [head_box(f) for f in frames]
    widths = [r - l for l, r in heads]
    target = float(np.median(widths))
    scaled = []
    for f, (l, r) in zip(frames, heads):
        k = target / (r - l)
        g = f.resize((round(f.width * k), round(f.height * k)), Image.LANCZOS)
        scaled.append((g, (l + r) / 2 * k))
    W = int(max(max(cx, g.width - cx) for g, cx in scaled) * 2 + 20)
    H = max(g.height for g, _ in scaled) + 10
    for i, (g, cx) in enumerate(scaled):
        c = Image.new("RGBA", (W, H))
        c.alpha_composite(g, (int(W / 2 - cx), 5))     # head centre on the canvas centre, bun at the top
        c.save(OUT / f"f_{i}.png", optimize=True)
    (OUT / "frames.json").write_text(json.dumps({"w": W, "h": H, "n": N}))
    print("canvas", W, H)
