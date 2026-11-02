#!/usr/bin/env python3
"""Layers for the flat 2D teacher rig (Rive), from art2d/designs/flat.png and art2d/flat/*.png.

- base pose split into head (turns about the neck) and body, white keyed out;
- arms (and the book) as layers of their own: the region where an arm pose differs from the base,
  so every pose shares one head and body and the arms move in and out of frame;
- patches: mouths, blink and half lids, gaze (left/right/up), raised brows, hand gestures,
  a blink for the listen pose and the second frame of the wave. Each patch is the region where
  its image differs from its source, feathered and cut to the figure's silhouette.
All in one crop box; positions in art/layout.json. Run: python3 gen/prep_flat.py
"""
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "art2d"
P = SRC / "flat"
OUT = ROOT / "flat" / "art"
BASE = SRC / "designs" / "flat.png"
ARMS = {"listen": "a_listen", "read": "a_read", "wave": "p_wave", "palm": "g_palm", "both": "g_both", "thumb": "g_thumb", "count": "g_count",
        # in-betweens on the way to those, and the second drawing of the wave
        "listen1": "i_listen1", "listen2": "i_listen2", "wave1": "i_wave1", "wave2": "w_alt",
        "palm1": "i_palm1", "thumb1": "i_thumb1", "count1": "i_count1", "both1": "i_both1"}
NECK_CUT, OVERLAP, SIDE_CUT = 588, 8, 622     # head = rows above the cut (lower at the sides, where the strands hang)
PIVOT = (512, 640)                             # the head turns about the base of the neck
BUN_PIVOT = (517, 150)                         # the bun sways about where it sits on the head
def bun_cut(x):                                # its lower outline: a shallow arc
    return 140 + 0.0016 * (x - 517) ** 2
# patch: (file, source image, search region x0, y0, x1, y1, pad, feather)
PATCHES = {
    **{f"mouth_{m}": (f"m_{m}", BASE, (380, 380, 650, 560), 14, 12) for m in ("mbp", "fv", "dt", "aa", "ee", "oh", "oo", "ch")},
    "eyes_closed": ("e_closed", BASE, (330, 300, 700, 430), 10, 10),
    "eyes_half": ("e_half", BASE, (330, 300, 700, 430), 10, 10),
    "gaze_left": ("e_left", BASE, (330, 320, 700, 430), 6, 6),
    "gaze_right": ("e_right", BASE, (330, 320, 700, 430), 6, 6),
    "gaze_up": ("e_up", BASE, (330, 320, 700, 430), 6, 6),
    "brow_up": ("b_up", BASE, (330, 230, 700, 330), 8, 8),
}


def key_white(im):
    """Alpha from a flood fill of near-white pixels connected to the border (the outline stops it)."""
    a = np.array(im.convert("RGB")).astype(np.int16)
    lab, _ = ndimage.label(a.min(-1) > 232)
    border = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
    bg = ndimage.binary_dilation(np.isin(lab, list(border)), iterations=1)
    alpha = np.array(Image.fromarray(((~bg) * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.8)))
    return Image.fromarray(np.dstack([a.astype(np.uint8), alpha]), "RGBA")


def changed_box(src_img, part, region):
    x0, y0, x1, y1 = region
    a = np.array(Image.open(part).convert("RGB")).astype(float)
    b = np.array(Image.open(src_img).convert("RGB")).astype(float)
    d = np.zeros(a.shape[:2], bool)
    d[y0:y1, x0:x1] = (np.abs(a - b).mean(-1) > 45)[y0:y1, x0:x1]
    d = ndimage.binary_opening(d, iterations=2)
    ys, xs = np.nonzero(d)
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def arm(part, light_ok=False):
    """The pixels where an arm pose differs from the base, closed and filled into solid shapes,
    cut to the pose's silhouette; returns the full-size RGBA."""
    a = np.array(Image.open(part).convert("RGB")).astype(float)
    b = np.array(Image.open(BASE).convert("RGB")).astype(float)
    d = ndimage.binary_opening(np.abs(a - b).mean(-1) > 40, iterations=2)
    lab, n = ndimage.label(d)
    sizes = ndimage.sum(d, lab, range(1, n + 1))
    d = np.isin(lab, [i + 1 for i, v in enumerate(sizes) if v > 600])
    d = ndimage.binary_fill_holes(ndimage.binary_closing(d, iterations=24))
    # the sleeve is the sweater's colour, so the diff misses it: run each column down to the frame's edge
    sil = np.array(key_white(Image.open(part)).getchannel("A")) > 20
    ys, xs = np.nonzero(d)
    low = np.full(d.shape[1], -1)
    np.maximum.at(low, xs, ys)
    bottom = np.nonzero(sil.any(1))[0].max()
    for x in np.nonzero(low >= 0)[0]:
        if bottom - low[x] < 160:
            d[low[x]:, x] = True
    d &= sil
    # nothing below the bust's lower edge: that is out of frame (a hand entering from below is cut there)
    base_sil = np.array(key_white(Image.open(BASE)).getchannel("A")) > 20
    rows = np.arange(d.shape[0])[:, None]
    edge = np.where(base_sil.any(0), d.shape[0] - 1 - np.argmax(base_sil[::-1], 0), np.nonzero(base_sil.any(1))[0].max())
    d &= rows <= edge[None, :]
    lab, n = ndimage.label(d)                  # stray strands of hair that moved a little: not part of the arm
    sizes = ndimage.sum(d, lab, range(1, n + 1))
    d = np.isin(lab, [i + 1 for i, v in enumerate(sizes) if v > 0.08 * sizes.max()])
    # white enclosed between the arm and the head is background (it is background in the base), and so is its grey fringe
    gap = (a.min(-1) > 225) & (np.array(key_white(Image.open(BASE)).getchannel("A")) < 128)
    fringe = ndimage.binary_dilation(gap, iterations=3) & (a.min(-1) > 110) & (a.max(-1) - a.min(-1) < 45)
    # hair the edit redrew next to the hand belongs to the head, with its light rim
    r_, g_, b_ = a[..., 0], a[..., 1], a[..., 2]
    hair = (r_ > 90) & (r_ < 200) & (g_ > 40) & (g_ < 100) & (b_ < 80) & (r_ - b_ > 60)
    hair = ndimage.binary_opening(hair, iterations=1)
    rim = ndimage.binary_dilation(hair, iterations=4) & (a.min(-1) > 150) & (a.max(-1) - a.min(-1) < 60)
    whitish = (a.min(-1) > 85) & (a.max(-1) - a.min(-1) < 50)    # an arm has no white or grey edge on white (the book has)
    d &= ~(gap | fringe | hair | rim | (whitish & ~np.bool_(light_ok)))
    d = ndimage.binary_opening(d, iterations=3)          # thin leftovers: a strand's outline
    lab, n = ndimage.label(d)
    sizes = ndimage.sum(d, lab, range(1, n + 1))
    d = np.isin(lab, [i + 1 for i, v in enumerate(sizes) if v > 0.08 * sizes.max()])
    m = np.array(Image.fromarray((ndimage.binary_dilation(d, iterations=3) * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2)))
    k = key_white(Image.open(part))
    alpha = np.array(k.getchannel("A")).astype(np.float32) * m / 255
    if not light_ok:                           # the grey of an outline's edge against the white: fade it out
        sat = a.max(-1) - a.min(-1)
        alpha *= 1 - np.clip((a.min(-1) - 70) / 60, 0, 1) * (sat < 50)
    alpha = alpha.astype(np.uint8)
    return Image.fromarray(np.dstack([np.array(k)[..., :3], alpha]), "RGBA")


MOUTH_LIFT: dict = {}                         # px to raise a mouth that an edit drew down past the chin


def chin_line():
    """Row of the jaw outline in each column of the base (below the smile), so a mouth never crosses it."""
    b = np.array(Image.open(BASE).convert("RGB")).astype(int)
    dark = b[530:700].min(-1) < 70
    return np.where(dark.any(0), 530 + np.argmax(dark, 0), 10 ** 4)


def patch(part, box, pad, feather, lift=0):
    x0, y0, x1, y1 = box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad
    keyed = np.array(key_white(Image.open(part)).getchannel("A").crop((x0, y0, x1, y1))).astype(np.float32) / 255
    crop = np.array(Image.open(part).convert("RGB").crop((x0, y0, x1, y1)))
    h, w = crop.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.minimum.reduce([xx, yy, w - 1 - xx, h - 1 - yy]).astype(np.float32)
    m = np.clip(d / feather, 0, 1) ** 1.5 * keyed
    if part.name.startswith("m_"):             # a mouth stops short of the jaw line, wherever it lands
        chin = chin_line()[x0:x1]
        m *= np.clip((chin[None, :] - 7 - (y0 - lift + yy)) / 5, 0, 1)
    return Image.fromarray(np.dstack([crop, (m * 255).astype(np.uint8)]), "RGBA"), (x0, y0 - lift)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    base = key_white(Image.open(BASE))
    keyed = {"base": base, **{k: arm(P / f"{v}.png", k == "read") for k, v in ARMS.items()}}
    boxes = [np.array(im.getchannel("A").point(lambda v: 255 if v > 20 else 0).getbbox()) for im in keyed.values()]
    bx0, by0 = np.min([b[:2] for b in boxes], 0) - 6
    bx1, by1 = np.max([b[2:] for b in boxes], 0) + 6
    crop = (int(bx0), int(by0), int(bx1), int(by1))
    arms = {}
    for k in ARMS:
        im = keyed[k].crop(crop)
        x0, y0, x1, y1 = im.getchannel("A").point(lambda v: 255 if v > 20 else 0).getbbox()
        im.crop((x0, y0, x1, y1)).save(OUT / f"arm_{k}.png", optimize=True)
        bottom = np.nonzero(np.array(im.getchannel("A"))[y1 - 3] > 20)[0]
        arms[k] = [x0, y0, x1 - x0, y1 - y0, int(bottom.mean()) if len(bottom) else (x0 + x1) // 2]
    # head / body split of the base
    a = np.array(base)
    H, W = a.shape[:2]
    cut = np.full(W, NECK_CUT)
    cut[:400] = SIDE_CUT; cut[630:] = SIDE_CUT
    rows = np.arange(H)[:, None]
    head, body = a.copy(), a.copy()
    head[..., 3] = np.where(rows < cut[None, :] + OVERLAP, a[..., 3], 0)
    body[..., 3] = np.where(rows >= cut[None, :], a[..., 3], 0)
    # the bun as its own layer over a full copy in the head: it only sways a pixel or two, so no hole shows
    xs = np.arange(W)[None, :]
    in_bun = (rows < bun_cut(xs)) & (xs > 380) & (xs < 660)
    bun = a.copy(); bun[..., 3] = np.where(in_bun, a[..., 3], 0)
    Image.fromarray(bun, "RGBA").crop(crop).save(OUT / "base_bun.png", optimize=True)
    Image.fromarray(head, "RGBA").crop(crop).save(OUT / "base_head.png", optimize=True)
    Image.fromarray(body, "RGBA").crop(crop).save(OUT / "base_body.png", optimize=True)
    # each arm drawing comes with its own body (below the same cut), so the arm is never stuck onto the base body
    bodies = []
    for k, v in ARMS.items():
        if k == "read":                        # the book is held in front of the base body
            continue
        pa = np.array(key_white(Image.open(P / f"{v}.png")))
        pa[..., 3] = np.where(rows >= cut[None, :], pa[..., 3], 0)
        rgb = pa[..., :3].astype(int)          # white shut in between the arm and the head: background, as in the base
        light = (rgb.min(-1) > 150) & (rgb.max(-1) - rgb.min(-1) < 45)
        pa[..., 3] = np.where(light & (np.array(base.getchannel("A")) < 128), 0, pa[..., 3])
        im = Image.fromarray(pa, "RGBA").crop(crop)
        im.quantize(256, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE).save(OUT / f"body_{k}.png", optimize=True)
        bodies.append(k)
    layout = {"crop": crop, "bodies": bodies, "size": [crop[2] - crop[0], crop[3] - crop[1]], "pivot": [PIVOT[0] - crop[0], PIVOT[1] - crop[1]], "bun_pivot": [BUN_PIVOT[0] - crop[0], BUN_PIVOT[1] - crop[1]], "patches": {}, "arms": arms}
    # every mouth patch covers the union of all mouth changes, so the base smile never shows through
    boxes = {n: changed_box(src, P / f"{part}.png", region) for n, (part, src, region, *_ ) in PATCHES.items()}
    mouths = [b for n, b in boxes.items() if n.startswith("mouth_")]
    union = (min(b[0] for b in mouths), min(b[1] for b in mouths), max(b[2] for b in mouths), max(b[3] for b in mouths))
    for n in boxes:
        if n.startswith("mouth_"):
            boxes[n] = union
    for name, (part, src, region, pad, feather) in PATCHES.items():
        f = P / f"{part}.png"
        box = boxes[name]
        im, (x, y) = patch(f, box, pad, feather, MOUTH_LIFT.get(name, 0))
        im.save(OUT / f"{name}.png", optimize=True)
        layout["patches"][name] = [x - crop[0], y - crop[1], im.width, im.height]
        print(name, box)
    (OUT / "layout.json").write_text(json.dumps(layout, indent=1))
    for old in [*OUT.glob("pose_*.png"), *OUT.glob("gest_*.png"), OUT / "listen_blink.png", OUT / "wave_alt.png"]:
        old.unlink(missing_ok=True)
    print("crop", crop)
