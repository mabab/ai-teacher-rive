#!/usr/bin/env python3
"""Generates scene.rml for the AI tutor teacher: a Rive avatar that follows a
LiveKit agent's state (`agentState` = the agent's lk.agent.state attribute, plus
the client's own connecting / disconnected / pause) and lip-syncs from
`viseme`, which the page computes from the agent's audio track.

Built on the Charlie avatar rig (~/avatar): the head is a generated render
without eyes, brows or mouth (art/teacher_head.png); the rig draws those.

Run: python3 gen/build_teacher.py && rive . --verify
"""
import math
import os
import re
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "scene.rml"
# Head art: a generated clay render (art/charlie_head.png) with vector eyes,
# brows and mouth on top; set False to fall back to the all-vector head.
RENDER_HEAD = True
# CHARLIE_BARE=1 builds Charlie alone on a transparent artboard (for embedding in other pages):
# the control panel is parked off the artboard and the backdrop only catches the pointer
BARE = True                    # no control panel and a transparent backdrop: the page owns the frame
HEAD_IMAGE = "art/teacher_head.png"
EYE_SCLERA_IMAGE = "art/eye_sclera.png"   # 256 px, oval 148 x 193 px
EYE_ASSETS = {}
# the render is 1024 px: eyes belong at (512 ± 84, 536) px, the mouth at (512, 711),
# the chin at 831; the eyes, brows and glasses are drawn at UPPER_SCALE
HEAD_IMAGE_SCALE = 0.68
FACE_LIFT = -16
UPPER_SCALE = 0.82
HEAD_IMAGE_Y = FACE_LIFT - 6 * UPPER_SCALE - (536 - 512) * HEAD_IMAGE_SCALE
MOUTH_Y = HEAD_IMAGE_Y + (711 - 512) * HEAD_IMAGE_SCALE
MOUTH_SCALE = 1.0
BODY_DROP = 58                 # a human chin sits lower than Charlie's, so the shoulders do too
# The render's own neck is cut along the collar by a clip that stays with the body, so a
# nod or a tilt never slides it out over the sweater; a vector neck behind it fills the
# gap when the head lifts. cut(x) is that line, in Character units.
NECK_CLIP = None
# Pivots, in Character units. The head turns about the base of the neck (so its arcs keep
# the neck seated in the collar); the torso leans and breathes about the waist.
NECK_PIVOT = 180
WAIST_Y = 400
NECK_HALF = 95                 # the render neck is ±81 plus a sideways nod; hair strands start beyond 100


def follow(frames, delay, amp, length, step=8, offset=0.0):
    """Overlapping action: `frames` (a looping channel of a leading part) delayed by
    `delay` frames and scaled by `amp`, resampled so the loop stays seamless — the
    part that follows moves later and less than the part that leads."""
    pts = sorted(frames)
    if pts[0][0] > 0:
        pts.insert(0, (0, pts[-1][1]))
    if pts[-1][0] < length:
        pts.append((length, pts[0][1]))

    def at(t):
        t %= length
        for (t0, v0), (t1, v1) in zip(pts, pts[1:]):
            if t0 <= t <= t1:
                u = 0 if t1 == t0 else (t - t0) / (t1 - t0)
                u = u * u * (3 - 2 * u)          # ease in-out between keys
                return v0 + (v1 - v0) * u
        return pts[-1][1]
    out = [(t, offset + amp * at(t - delay)) for t in range(0, length, step)]
    out.append((length, out[0][1]))
    return out


def neck_cut(x):
    return 176 + 26 * (1 - (x / NECK_HALF) ** 2)
SKIN = "FFF9C7A3"
SKIN_SHADE = "FFEBA97B"
HAIR = "FF3F1D14"
HAIR_LIGHT = "FF6B3A22"

# ---------------------------------------------------------------- palette
FUR = "FFF39A26"
FUR_DARK = "FFE07F16"
EAR_INNER = "FFD9700F"
MUZZLE = "FFFCCB6A"
TUFT = "FFFBE3B0"
BROW = "FFCF6A12"
FRECKLE = "FFFFD585"
EYE_LINE = "FF3A2213"
IRIS = "FF2A1A10"
NOSE = "FF221714"
MOUTH_LINE = "FF7A3112"
MOUTH_IN = "FF4A1610"
TONGUE = "FFE8656B"
TEETH = "FFFFFBF2"
SHIRT = "FFE2382A"
SHIRT_DARK = "FFB92A20"
BG_TOP = "FF8E7BFF"
BG_BOTTOM = "FF4B2FCF"

_next = [100]


def nid():
    _next[0] += 1
    return f"0:{_next[0]}"


def f(v):
    return f"{v:.4f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v)


# ---------------------------------------------------------------- geometry
def smooth_path(points, corners=(), tension=1.0, closed=True, corner_radius=0, vertex_ids=None):
    """Catmull-Rom through points; indices in `corners` become sharp vertices.
    vertex_ids: {index: id} for vertices an animation keys."""
    n = len(points)
    out = []
    vertex_ids = vertex_ids or {}
    for i, (x, y) in enumerate(points):
        vid = f' id="{vertex_ids[i]}"' if i in vertex_ids else ""
        if i in corners:
            r = f' radius="{f(corner_radius)}"' if corner_radius else ""
            out.append(f'<StraightVertex x="{f(x)}" y="{f(y)}"{r}{vid}/>')
            continue
        px, py = points[(i - 1) % n]
        qx, qy = points[(i + 1) % n]
        if not closed and i == 0:
            px, py = x, y
        if not closed and i == n - 1:
            qx, qy = x, y
        tx, ty = qx - px, qy - py
        rot = math.atan2(ty, tx)
        dist = math.hypot(tx, ty) / 6 * tension
        out.append(
            f'<CubicMirroredVertex x="{f(x)}" y="{f(y)}" rotation="{f(rot)}" distance="{f(dist)}"{vid}/>'
        )
    closed_attr = ' isClosed="true"' if closed else ""
    return f'<PointsPath{closed_attr} name="Path">' + "".join(out) + "</PointsPath>"


def mirror_half(right_half):
    """right_half runs from top centre (x=0) clockwise to bottom centre (x=0)."""
    left = [(-x, y) for x, y in reversed(right_half[1:-1])]
    return right_half + left


def fill(color):
    return f'<Fill name="Fill"><SolidColor colorValue="{color}" name="C"/></Fill>'


def stroke(color, w, cap="round"):
    return (
        f'<Stroke thickness="{f(w)}" cap="{cap}" join="round" name="Stroke">'
        f'<SolidColor colorValue="{color}" name="C"/></Stroke>'
    )


_DROP = re.compile(r'<Fill fillRule="clockwise" name="DropShadow">.*?</Fill>')


def shape(name, geom, paints="", x=0, y=0, sid=None, extra=""):
    sid = sid or nid()
    # within a shape the last paint draws on top: drop shadows go first, under the fill
    drops = _DROP.findall(paints)
    if drops and _DROP.sub("", paints):
        paints = "".join(drops) + _DROP.sub("", paints)
    return sid, (
        f'<Shape x="{f(x)}" y="{f(y)}" name="{name}" id="{sid}">{geom}{paints}{extra}</Shape>'
    )


def ellipse(w, h, ox=0.5, oy=0.5):
    return f'<Ellipse width="{f(w)}" height="{f(h)}" originX="{ox}" originY="{oy}" name="Path"/>'


def rect(w, h, ox=0.5, oy=0.5, r=0):
    rr = f' cornerRadiusTL="{f(r)}"' if r else ""
    return f'<Rectangle width="{f(w)}" height="{f(h)}" originX="{ox}" originY="{oy}"{rr} name="Path"/>'


def node(name, children, x=0, y=0, nid_=None, extra=""):
    nid_ = nid_ or nid()
    return nid_, f'<Node x="{f(x)}" y="{f(y)}" name="{name}" id="{nid_}"{extra}>{"".join(children)}</Node>'


def clip(source_id):
    return f'<ClippingShape sourceId="{source_id}" name="Clip"/>'


def _stops(stops):
    return "".join(f'<GradientStop colorValue="{c}" position="{p}"/>' for p, c in stops)


def radial(cx, cy, r, stops, paint="Fill"):
    return (
        f'<{paint} name="Shade"><RadialGradient startX="{f(cx)}" startY="{f(cy)}" endX="{f(cx + r)}" endY="{f(cy)}" name="G">'
        f"{_stops(stops)}</RadialGradient></{paint}>"
    )


def linear(x0, y0, x1, y1, stops):
    return (
        f'<Fill name="Shade"><LinearGradient startX="{f(x0)}" startY="{f(y0)}" endX="{f(x1)}" endY="{f(y1)}" name="G">'
        f"{_stops(stops)}</LinearGradient></Fill>"
    )


def soft(color, strength, ox=0, oy=0, inner=False):
    """Feathered fill: a drop shadow, a glow, or (inner) edge occlusion."""
    inn = ' inner="true"' if inner else ""
    kind = "InnerShade" if inner else "DropShadow"
    return (
        f'<Fill fillRule="clockwise" name="{kind}"><SolidColor colorValue="{color}" name="C"/>'
        f'<Feather strength="{f(strength)}" offsetX="{f(ox)}" offsetY="{f(oy)}"{inn} name="F"/></Fill>'
    )


def para(name, children):
    """A parallax wrapper: only the TurnX/TurnY joystick timelines key these."""
    ids[f"P_{name}"] = nid()
    kids = children if isinstance(children, list) else [children]
    return node(f"P_{name}", kids, nid_=ids[f"P_{name}"])[1]


# ---------------------------------------------------------------- the face
ids = {}

HEAD_RIGHT = [
    (0, -162), (96, -148), (160, -98), (186, -30), (190, 10),
    (216, 34),           # cheek fluff tip
    (184, 56),
    (200, 88),           # lower fluff tip
    (150, 124), (84, 158), (0, 172),
]
HEAD_PTS = mirror_half(HEAD_RIGHT)
N_HEAD = len(HEAD_PTS)
FLUFF_TIPS = {5: 1, 7: 1, N_HEAD - 5: -1, N_HEAD - 7: -1}   # vertex index -> side
head_corners = set(FLUFF_TIPS)
head_vertex_ids = []      # one {index: id} per copy of the head path


def head_geom():
    vids = {i: nid() for i in FLUFF_TIPS}
    head_vertex_ids.append(vids)
    return smooth_path(HEAD_PTS, corners=head_corners, corner_radius=10, vertex_ids=vids)


EAR_TILT = 0.34


def ear(side):
    s = 1 if side == "R" else -1
    # drawn pointing straight up from the pivot at its base, then tilted outward
    outer = [(-74, 34), (-82, -30), (-64, -100), (-28, -152), (6, -166), (38, -144), (64, -82), (74, -12), (56, 40)]
    inner = [(-50, 26), (-58, -26), (-46, -88), (-20, -130), (4, -140), (26, -122), (46, -72), (52, -14), (36, 30)]
    if s < 0:
        outer = [(-x, y) for x, y in outer][::-1]
        inner = [(-x, y) for x, y in inner][::-1]
    outer_paint = (
        linear(0, 40, s * 10, -240, [(0, "FFC2600A"), (0.45, FUR_DARK), (1, "FFFBB24A")])
        + soft("66A84A04", 18, 0, 0, inner=True)
        + soft("44FFE0A0", 10, -s * 8, -6, inner=True)
    )
    inner_paint = (
        linear(0, 30, 0, -200, [(0, "FF9E4806"), (0.6, "FFD06C10"), (1, "FFE88A22")])
        + soft("77803400", 14, 0, 6, inner=True)
    )
    outer_s = shape("EarOuter", smooth_path(outer), outer_paint)[1]
    inner_s = shape("EarInner", smooth_path(inner), inner_paint)[1]
    # three fur clumps fanning out of the inner ear, toward the head
    fluff = []
    for fx, fy, rot, w in ((-s * 22, -44, s * 0.45, 52), (-s * 26, -68, s * 0.25, 48), (-s * 24, -92, s * 0.05, 40)):
        clump = smooth_path([(-s * w / 2, 0), (-s * w * 0.1, -15), (s * w / 2, -3), (-s * w * 0.1, 14)], corners={2}, corner_radius=4)
        fluff.append(
            f'<Shape x="{f(fx)}" y="{f(fy)}" rotation="{f(-rot)}" name="EarFluff">{clump}'
            + radial(-s * w * 0.25, -4, w * 0.7, [(0, "FFFFD080"), (0.6, "FFF8AA40"), (1, "FFE88A22")])
            + soft("44803A00", 6, 0, 4)
            + "</Shape>"
        )
    ids[f"EarTilt{side}"] = nid()
    tilt = node(f"EarTilt{side}", fluff + [inner_s, outer_s], nid_=ids[f"EarTilt{side}"], extra=f' rotation="{f(s * EAR_TILT)}"')[1]
    ids[f"Ear{side}"] = nid()
    return node(f"Ear{side}", [tilt], x=s * 108, y=-100, nid_=ids[f"Ear{side}"])[1]


def tuft():
    # a three-lobed cream curl
    pts = [(-42, -150), (-50, -168), (-38, -186), (-22, -184), (-14, -202), (6, -210), (16, -196),
           (32, -198), (48, -186), (50, -166), (40, -150)]
    paint = (
        radial(-10, -192, 60, [(0, "FFFFF8E6"), (0.6, "FFFBE2AE"), (1, "FFEFC07A")])
        + soft("55C08030", 8, 3, 4, inner=True)
    )
    return shape("Tuft", smooth_path(pts), paint)[1]


def brow(side):
    s = 1 if side == "R" else -1
    # a thick rounded arc
    arc = lambda: smooth_path([(-27 * s, 7), (-6 * s, -5), (27 * s, 3)], closed=False)
    paint = (
        '<Stroke thickness="13" cap="round" join="round" name="Stroke">'
        f'<LinearGradient startX="0" startY="-8" endX="0" endY="8" name="G">'
        f'<GradientStop colorValue="{HAIR_LIGHT}" position="0"/><GradientStop colorValue="{HAIR}" position="1"/>'
        '</LinearGradient></Stroke>'
    )
    body = shape("BrowShape", arc(), paint)[1]
    shadow = shape("BrowShadow", arc(),
                   '<Stroke thickness="10" cap="round" name="S"><SolidColor colorValue="33A05A3A" name="C"/>'
                   '<Feather strength="4" offsetY="4" name="F"/></Stroke>')[1]
    ids[f"Brow{side}"] = nid()
    return node(f"Brow{side}", [body, shadow], x=s * 66, y=-80, nid_=ids[f"Brow{side}"])[1]


def heart_geom(w, h=None):
    h = h or w * 0.92
    pts = [(0, -0.22 * h), (0.27 * w, -0.5 * h), (0.5 * w, -0.16 * h), (0.3 * w, 0.18 * h), (0, 0.5 * h),
           (-0.3 * w, 0.18 * h), (-0.5 * w, -0.16 * h), (-0.27 * w, -0.5 * h)]
    return smooth_path(pts, corners={0, 4}, corner_radius=3)


HEART_PAINT = radial(-12, -14, 50, [(0, "FFFF8A9A"), (0.55, "FFF0384E"), (1, "FFC21A34")])
GOLD_PAINT = radial(-12, -14, 56, [(0, "FFFFF0A0"), (0.55, "FFFFC21A"), (1, "FFF29A00")])


def eye(side):
    s = 1 if side == "R" else -1
    w, h = 76, 80
    clip_id, lash_clip_id = nid(), nid()
    _, clip_s = shape("EyeClip", ellipse(w, h), sid=clip_id)
    _, lash_clip_s = shape("LashClip", ellipse(w + 12, h + 12), sid=lash_clip_id)
    # upper lid: fur-coloured, its lower edge bowed down, a dark lash line on that edge
    lid_pts = [(-60, -110), (60, -110), (60, -4), (0, 5), (-60, -4)]
    lid_geom = lambda: smooth_path(lid_pts, corners={0, 1, 2, 4})
    lid_fill = shape("LidSkin", lid_geom(), linear(0, -60, 0, 0, [(0, "FFFFD6B8"), (1, SKIN_SHADE)]), extra=clip(clip_id))[1]
    lid_shadow = shape("LidShadow", lid_geom(), soft("55A0583A", 7, 0, 7), extra=clip(clip_id))[1]
    lash = shape(
        "Lash", smooth_path([(-s * 46, 0), (-s * 20, 4), (s * 14, 3), (s * 44, -3), (s * 52, -9)], closed=False),
        stroke("FF24120A", 6.5), extra=clip(lash_clip_id),
    )[1]
    ids[f"Lid{side}"] = nid()
    lid = node("Lid", [lash, lid_fill, lid_shadow], y=-46, nid_=ids[f"Lid{side}"])[1]
    if RENDER_HEAD:
        # cartoon iris: smooth dark brown, a warm glow low down, two crisp glints
        iris_paint = radial(0, 16, 42, [(0, "FF7A4422"), (0.55, "FF3A1E0E"), (1, "FF1A0D06")])
        iris = shape("Iris", ellipse(58, 64), iris_paint, extra=clip(clip_id))[1]
        pupil = shape("Pupil", ellipse(30, 34), radial(0, 6, 20, [(0, "FF1A0E08"), (1, "FF080403")]), extra=clip(clip_id))[1]
        glow = shape("IrisGlow", ellipse(40, 18), soft("77D08048", 7), y=19, extra=clip(clip_id))[1]
        big = shape("Glint", ellipse(19, 21), fill("FFFFFFFF"), x=10, y=-12, extra=clip(clip_id))[1]
        small = shape("GlintSmall", ellipse(8, 8), fill("EEFFFFFF"), x=-12, y=13, extra=clip(clip_id))[1]
        gaze_parts = [big, small, glow, pupil, iris]
    else:
        hl1 = shape("Glint", ellipse(13, 13), fill("FFFFFFFF"), x=10, y=-6)[1]
        hl2 = shape("GlintSmall", ellipse(6, 6), fill("CCFFFFFF"), x=-11, y=14)[1]
        iris_paint = radial(0, 18, 38, [(0, "FF8A5228"), (0.5, "FF4A2814"), (1, IRIS)])
        iris = shape("Iris", ellipse(56, 62), iris_paint, extra=clip(clip_id))[1]
        gaze_parts = [hl1, hl2, iris]
    ids[f"Gaze{side}"] = nid()
    gaze = node(f"Gaze{side}", gaze_parts, nid_=ids[f"Gaze{side}"])[1]
    ids[f"Look{side}"] = nid()
    look = node(f"Look{side}", [gaze], x=-s * 3, y=3, nid_=ids[f"Look{side}"])[1]
    white_paint = (
        radial(0, 10, 46, [(0, "FFFFFDF8"), (0.7, "FFFBF4EA"), (1, "FFE6D6C6")])
        + soft("66A0582A", 9, 0, 9, inner=True)
    )
    if RENDER_HEAD:
        EYE_ASSETS.setdefault("sclera", nid())
        white = (f'<Image scaleX="{f(w / 148)}" scaleY="{f(h / 193)}" assetId="{EYE_ASSETS["sclera"]}" name="ScleraRender">{clip(clip_id)}</Image>'
                 + shape("ScleraShade", ellipse(w, h), soft("55A0582A", 9, 0, 9, inner=True))[1])
    else:
        white = shape("White", ellipse(w, h), white_paint)[1]
    ids[f"Blink{side}"] = nid()
    blink = node(f"Blink{side}", [lid, look, white, clip_s, lash_clip_s], nid_=ids[f"Blink{side}"])[1]
    socket = shape("Socket", ellipse(96, 100), soft("33B0603A", 14, 0, 5))[1]
    # emoji eyes for the classroom-style reactions, authored hidden
    ids[f"HeartEye{side}"] = nid()
    heart_eye = shape("HeartEye", heart_geom(88), HEART_PAINT + soft("55801020", 6, 0, 4), y=4,
                      sid=ids[f"HeartEye{side}"]).__getitem__(1).replace("<Shape ", '<Shape scaleX="0" scaleY="0" ', 1)
    ids[f"StarEye{side}"] = nid()
    star_eye = shape("StarEye", star_geom(96, 5, 0.5, 8), GOLD_PAINT + soft("55905000", 6, 0, 4), y=2,
                     sid=ids[f"StarEye{side}"]).__getitem__(1).replace("<Shape ", '<Shape scaleX="0" scaleY="0" ', 1)
    ids[f"Eye{side}"] = nid()
    return node(f"Eye{side}", [heart_eye, star_eye, blink, socket], x=s * 70, y=-6, nid_=ids[f"Eye{side}"])[1]


def nose():
    pts = [(-37, -17), (37, -17), (0, 27)]
    geom = lambda: smooth_path(pts, corners={0, 1, 2}, corner_radius=20)
    nose_paint = radial(-10, -10, 44, [(0, "FF54403B"), (1, "FF0F0A09")])
    body = shape("NoseShape", geom(), nose_paint)[1]
    shine = shape("NoseShine", ellipse(28, 12), soft("CCFFFFFF", 3), x=-9, y=-8)[1]
    dot = shape("NoseDot", ellipse(6, 6), fill("EEFFFFFF"), x=10, y=-10)[1]
    shadow = shape("NoseShadow", geom(), soft("66A0480A", 10, 2, 12))[1]
    return node("Nose", [dot, shine, body, shadow], y=46)[1]


def freckles():
    dots = []
    for s in (-1, 1):
        for x, y in ((112, 38), (128, 50), (108, 58)):
            dots.append(shape("Freckle", ellipse(10, 10), fill(FRECKLE), x=s * x, y=y)[1])
    for s in (-1, 1):
        dots.append(shape("Blush", ellipse(46, 26), soft("55FF6A3A", 12), x=s * 116, y=52)[1])
    return node("Freckles", dots)[1]


def muzzle(head_clip_id):
    right = [(0, 20), (44, 18), (86, 36), (124, 70), (180, 96), (260, 104), (260, 260), (0, 260)]
    pts = mirror_half(right)
    corners = {6, 7, len(pts) - 7, len(pts) - 8}
    geom = lambda: smooth_path(pts, corners=corners)
    paint = radial(0, 84, 170, [(0, "FFFFE6AE"), (0.6, MUZZLE), (1, "FFF2B04C")])
    sheen = shape("MuzzleSheen", ellipse(150, 56), soft("77FFFFFF", 22), y=74, extra=clip(head_clip_id))[1]
    body = shape("Muzzle", geom(), paint, extra=clip(head_clip_id))[1]
    # the muzzle sits proud of the face, so it shades the fur just above it
    lip = shape("MuzzleShadow", geom(), soft("77A84E06", 10, 0, -7), extra=clip(head_clip_id))[1]
    return [sheen, body, lip]


# ---------------------------------------------------------------- visemes
VISEMES = [
    "rest", "mbp", "fv", "dt", "aa", "ee", "oh", "oo", "ch",
]


MOUTH_EDGE = "FFB0484E"
MOUTH_INK = "FFB24A55"


def soft_line(pts, width, corners=(), closed=False):
    """A mouth line in the clay style: a soft shadow under a rounded stroke."""
    shadow = (f'<Stroke thickness="{f(width + 2)}" cap="round" join="round" name="Shadow">'
              f'<SolidColor colorValue="44B0603A" name="C"/><Feather strength="4" offsetY="3" name="F"/></Stroke>')
    line = (f'<Stroke thickness="{f(width)}" cap="round" join="round" name="Line">'
            f'<LinearGradient startX="0" startY="-6" endX="0" endY="6" name="G">'
            f'<GradientStop colorValue="FFD06A70" position="0"/><GradientStop colorValue="{MOUTH_INK}" position="1"/>'
            f'</LinearGradient></Stroke>')
    return shape("Line", smooth_path(pts, corners=set(corners), closed=closed), shadow + line)[1]


def open_mouth(name, w, h, teeth_top=0, teeth_bottom=0, tongue=True, round_=False):
    clip_id = nid()
    if round_:
        geom = lambda: ellipse(w, h)
    else:
        top = h * 0.16
        pts = [(-w / 2, 0), (0, -top), (w / 2, 0), (w * 0.32, h * 0.78), (0, h), (-w * 0.32, h * 0.78)]
        geom = lambda: smooth_path(pts, corners={0, 2}, corner_radius=8)
    mid = 0 if round_ else h * 0.4
    parts = []
    if teeth_top:
        y0 = -h / 2 if round_ else -h * 0.2
        parts.append(shape("TeethTop", rect(w, teeth_top + (h * 0.2 if not round_ else 0), 0.5, 0),
                           fill("FFFFFCF4") + soft("55A08070", 3, 0, 2, inner=True), y=y0, extra=clip(clip_id))[1])
    if teeth_bottom:
        y1 = h / 2 if round_ else h
        parts.append(shape("TeethBottom", rect(w, teeth_bottom, 0.5, 1),
                           fill("FFFFFCF4") + soft("55A08070", 3, 0, -2, inner=True), y=y1, extra=clip(clip_id))[1])
    if tongue:
        ty = h / 2 if round_ else h
        parts.append(shape("Tongue", ellipse(w * 0.72, h * 0.72),
                           radial(0, -h * 0.2, w * 0.45, [(0, "FFFFA0AC"), (1, "FFE0505E")]), y=ty, extra=clip(clip_id))[1])
    inside = (radial(0, mid - h * 0.3, max(w, h) * 0.75, [(0, "FF8A3028"), (0.6, "FF4E1410"), (1, "FF2A0806")])
              + soft("AA200402", 6, 0, 5, inner=True) + stroke(MOUTH_EDGE, 2.5))
    parts.append(shape("Inside", geom(), inside, sid=clip_id)[1])
    # the open mouth sits in the muzzle: a soft shade around its lower rim
    parts.append(shape("MouthShade", geom(), soft("44B0603A", 6, 0, 4))[1])
    return parts


def viseme_parts(v):
    if v == "rest":
        # a closed, friendly smile
        return [soft_line([(-30, -6), (-15, 3), (0, 6), (15, 3), (30, -6)], 6)]
    if v == "mbp":
        return [soft_line([(-28, -1), (0, 4), (28, -1)], 7)]
    if v == "fv":
        return open_mouth(v, 46, 16, teeth_top=8, tongue=False)
    if v == "dt":
        return open_mouth(v, 54, 22, teeth_top=6)
    if v == "aa":
        return open_mouth(v, 62, 46, teeth_top=5)
    if v == "ee":
        return open_mouth(v, 76, 22, teeth_top=7, teeth_bottom=6, tongue=False)
    if v == "oh":
        return open_mouth(v, 40, 44, round_=True)
    if v == "oo":
        return open_mouth(v, 24, 24, round_=True, tongue=False)
    if v == "ch":
        return open_mouth(v, 50, 28, teeth_top=7, teeth_bottom=7, tongue=False)
    raise ValueError(v)


def mouth():
    kids = []
    for i, v in enumerate(VISEMES):
        ids[f"V{i}"] = nid()
        op = "1" if i == 0 else "0"
        kids.append(node(f"Viseme_{v}", viseme_parts(v), nid_=ids[f"V{i}"], extra=f' opacity="{op}"')[1])
    if not RENDER_HEAD:   # the render already has the line under the nose
        kids.append(shape("Philtrum", smooth_path([(0, -22), (0, -4)], closed=False), stroke(MOUTH_LINE, 4))[1])
    return node("Mouth", kids, y=MOUTH_Y, extra=f' scaleX="{MOUTH_SCALE}" scaleY="{MOUTH_SCALE}"')[1]


# ---------------------------------------------------------------- body
def body():
    right = [(0, 108), (60, 106), (140, 140), (180, 210), (196, 320), (200, 480), (0, 480)]   # runs past the frame's bottom
    pts = mirror_half([(x, y + BODY_DROP) for x, y in right])
    w = 72   # narrower than the render's ±81 neck, so a sideways nod never shows its edge
    xs = [w - i * (2 * w / 8) for i in range(9)]
    neck_pts = [(-w, 90), (w, 90)] + [(x, neck_cut(x) + 4) for x in xs]
    v = "".join(f'<StraightVertex x="{f(x)}" y="{f(y)}"/>' for x, y in neck_pts)
    neck = shape("Neck", f'<PointsPath isClosed="true" name="Path">{v}</PointsPath>',
                 linear(-w, 0, w, 0, [(0, "FFE59A66"), (0.5, "FFD38A5C"), (1, "FFE59A66")]))[1]
    return [neck] + [outfit(i, pts) for i in range(len(OUTFITS))]


# ---------------------------------------------------------------- wardrobe
# Each category is a set of variant nodes; a selector layer keys their opacity.
WARDROBE = {"glasses": 4, "hat": 4, "outfit": 4}


def variant(cat, i, children):
    ids[f"{cat}{i}"] = nid()
    op = "1" if i == 0 else "0"
    return node(f"{cat.title()}_{i}", children, nid_=ids[f"{cat}{i}"], extra=f' opacity="{op}"')[1]


def glasses():
    frame = "FF3A2213"
    out = []
    # 1: round reading glasses
    parts = []
    for sx in (-1, 1):
        parts.append(shape("Lens", ellipse(98, 94), fill("22FFFFFF") + stroke(frame, 6), x=sx * 70, y=-6)[1])
        parts.append(shape("Temple", smooth_path([(sx * 119, -16), (sx * 176, -28)], closed=False), stroke(frame, 6))[1])
    parts.insert(0, shape("Bridge", smooth_path([(-22, -14), (0, -22), (22, -14)], closed=False), stroke(frame, 6))[1])
    out.append(variant("glasses", 1, parts))
    # 2: sunglasses
    parts = []
    for sx in (-1, 1):
        lens_paint = (linear(0, -40, 0, 40, [(0, "EE2A2A40"), (1, "EE0E0E18")])
                      + stroke("FF101018", 5))
        glint = shape("Glint", smooth_path([(-30, -18), (-6, -30)], closed=False), stroke("88FFFFFF", 6))[1]
        parts.append(node("Shade", [glint, shape("Lens", rect(108, 82, r=34), lens_paint)[1]], x=sx * 70, y=-4)[1])
        parts.append(shape("Temple", smooth_path([(sx * 124, -16), (sx * 176, -26)], closed=False), stroke("FF101018", 6))[1])
    parts.insert(0, shape("Bridge", smooth_path([(-18, -16), (0, -20), (18, -16)], closed=False), stroke("FF101018", 7))[1])
    out.append(variant("glasses", 2, parts))
    # 3: party star glasses
    parts = []
    for sx in (-1, 1):
        parts.append(shape("StarFrame", star_geom(132, 5, 0.6, 10), fill("33FFFFFF") + stroke("FFF06BFF", 8)
                           + soft("55901060", 6, 0, 4), x=sx * 72, y=-4)[1])
    parts.insert(0, shape("Bridge", smooth_path([(-14, -10), (0, -14), (14, -10)], closed=False), stroke("FFF06BFF", 7))[1])
    out.append(variant("glasses", 3, parts))
    return [variant("glasses", 0, [])] + out


def hats():
    out = [variant("hat", 0, [])]
    # 1: baseball cap
    dome = shape("Dome", smooth_path([(-158, -92), (-140, -150), (-70, -192), (0, -202), (70, -192), (140, -150), (158, -92),
                                      (0, -108)], corners={0, 6}),
                 radial(-50, -170, 220, [(0, "FF6FC0FF"), (0.6, "FF2F86E8"), (1, "FF1A5CB8")]) + soft("55103070", 12, 0, 0, inner=True))[1]
    brim = shape("Brim", smooth_path([(-120, -104), (0, -122), (120, -104), (110, -84), (0, -94), (-110, -84)], corners={0, 2}),
                 linear(0, -120, 0, -84, [(0, "FF1A5CB8"), (1, "FF0F3F88")]) + soft("66102040", 8, 0, 8))[1]
    button_ = shape("Button", ellipse(22, 14), fill("FF0F3F88"), y=-200)[1]
    badge = shape("Badge", star_geom(36, 5, 0.5, 3), fill("FFFFD21A"), y=-150)[1]
    out.append(variant("hat", 1, [brim, button_, badge, dome]))
    # 2: party cone
    cone = shape("Cone", smooth_path([(-58, -146), (0, -300), (58, -146)], corners={0, 1, 2}, corner_radius=6),
                 linear(-58, 0, 58, 0, [(0, "FFB06BFF"), (0.5, "FFF06BFF"), (1, "FF9B6BFF")]))[1]
    stripes = [shape("Stripe", smooth_path([(-58 + 13 * t, -146 - 40 * t), (58 - 13 * t, -146 - 40 * t)], closed=False),
                     stroke("FFFFD21A", 7))[1] for t in (1, 2, 3)]
    pom = shape("Pompom", ellipse(34, 34), radial(-6, -6, 22, [(0, "FFFFFFFF"), (1, "FFFFE27A")]), y=-300)[1]
    out.append(variant("hat", 2, [node("PartyHat", [pom] + stripes + [cone], x=26, y=4, extra=' rotation="0.22"')[1]]))
    # 3: crown
    crown_pts = [(-70, -140), (-74, -206), (-38, -170), (0, -224), (38, -170), (74, -206), (70, -140)]
    crown = shape("Crown", smooth_path(crown_pts, corners=set(range(7)), corner_radius=5),
                  linear(0, -224, 0, -140, [(0, "FFFFF0A0"), (0.5, "FFFFC21A"), (1, "FFE08A00")]) + stroke("FFC07000", 3))[1]
    gems = [shape("Gem", ellipse(16, 16), fill(c), x=x, y=-160)[1] for x, c in ((-40, "FFF0384E"), (0, "FF3AA8FF"), (40, "FF39C86A"))]
    tips = [shape("Tip", ellipse(14, 14), fill("FFFFE680"), x=x, y=y)[1] for x, y in ((-74, -210), (0, -228), (74, -210))]
    out.append(variant("hat", 3, gems + tips + [crown]))
    return out


OUTFITS = [
    # (name, shirt gradient, trim colour); the first is the default
    ("sweater", ("FF6FD8C8", "FF2BA89A", "FF1D7C72"), "FF17665E"),
    ("jacket", ("FFB48CFF", "FF7A4CFF", "FF5230C0"), "FF3E2296"),
    ("tee", ("FFF65440", SHIRT, "FFB8261C"), SHIRT_DARK),
    ("hoodie", ("FF6FC0FF", "FF2F86E8", "FF1A5CB8"), "FF124A96"),
]


FRONT = []


def outfit(i, pts):
    name, (c0, c1, c2), trim = OUTFITS[i]
    paint = linear(-120, 110, 160, 320, [(0, c0), (0.5, c1), (1, c2)]) + soft("55100820", 26, 0, 0, inner=True)
    shirt = shape("Shirt", smooth_path(pts, corners={4, 5, 6}), paint)[1]
    extra = []
    if name == "tee":
        extra.append(shape("Collar", smooth_path([(-52, 112), (0, 140), (52, 112)], closed=False), stroke(trim, 8))[1])
    elif name == "hoodie":
        extra.append(shape("Hood", smooth_path([(-92, 128), (-60, 104), (0, 98), (60, 104), (92, 128)], closed=False), stroke(trim, 22))[1])
        for sx in (-1, 1):
            extra.insert(0, shape("String", smooth_path([(sx * 22, 128), (sx * 26, 170), (sx * 22, 196)], closed=False), stroke("FFFFFFFF", 5))[1])
            extra.insert(0, shape("Tip", ellipse(9, 14), fill("FFFFFFFF"), x=sx * 22, y=200)[1])
    elif name == "sweater":
        for sx in (-1, 1):
            extra.append(shape("ShirtCollar", smooth_path([(sx * 4, 128), (sx * 50, 110), (sx * 40, 150)], corners={0, 1, 2}, corner_radius=4),
                               fill("FFFFFFFF") + stroke("FFDDDDDD", 2))[1])
        extra.append(shape("Rib", smooth_path([(-58, 116), (0, 146), (58, 116)], closed=False), stroke(trim, 12))[1])
    elif name == "jacket":
        bow = []
        for sx in (-1, 1):
            bow.append(shape("Wing", smooth_path([(0, 0), (sx * 30, -16), (sx * 30, 16)], corners={0, 1, 2}, corner_radius=6),
                             fill("FFFFD21A") + stroke("FFC09000", 2))[1])
        knot = shape("Knot", ellipse(14, 16), fill("FFFFC000"))[1]
        extra.append(node("BowTie", [knot] + bow, y=136)[1])
        for sx in (-1, 1):
            extra.append(shape("Lapel", smooth_path([(sx * 30, 124), (sx * 70, 118), (sx * 44, 220)], corners={0, 1, 2}, corner_radius=6),
                               fill(trim))[1])
    # the trims (collars, bow) go in front of the head so they cover where the render's
    # neck ends; drawn for Charlie's narrower neck, they are widened and lowered
    FRONT.append(variant("outfitfront", i, [node("Trim", extra, y=BODY_DROP + 4, extra=' scaleX="1.5"')[1]]))
    return variant("outfit", i, [shirt])


IMAGE_ASSET_ID = None


def ghost(name):
    """An empty node standing in for a vector part the render bakes in, so the
    timelines that key it stay valid."""
    ids[name] = nid()
    return f'<Node name="{name}" id="{ids[name]}"/>'


def neck_clip_shape():
    """Everything except the strip under the collar: the render shows only above the cut."""
    xs = [NECK_HALF - i * (2 * NECK_HALF / 10) for i in range(11)]
    curve = [(x, neck_cut(x)) for x in xs]
    pts = [(-600, -800), (600, -800), (600, 700), (NECK_HALF, 700)] + curve + [(-NECK_HALF, 700), (-600, 700)]
    v = "".join(f'<StraightVertex x="{f(x)}" y="{f(y)}"/>' for x, y in pts)
    return shape("NeckClip", f'<PointsPath isClosed="true" name="Path">{v}</PointsPath>', sid=NECK_CLIP)[1]


def render_head_kids():
    global IMAGE_ASSET_ID, NECK_CLIP
    IMAGE_ASSET_ID = nid()
    NECK_CLIP = NECK_CLIP or nid()
    render = (f'<Image y="{HEAD_IMAGE_Y}" scaleX="{HEAD_IMAGE_SCALE}" scaleY="{HEAD_IMAGE_SCALE}" '
              f'assetId="{IMAGE_ASSET_ID}" name="HeadRender">{clip(NECK_CLIP)}</Image>')
    upper = node("Upper", [
        para("BrowL", brow("L")), para("BrowR", brow("R")), para("Glasses", glasses()),
        para("EyeL", eye("L")), para("EyeR", eye("R")),
    ], y=FACE_LIFT, extra=f' scaleX="{UPPER_SCALE}" scaleY="{UPPER_SCALE}"')[1]
    stand_ins = "".join(ghost(n) for n in ("EarL", "EarR", "EarTiltL", "EarTiltR"))
    ids["Sweat"] = nid()
    drop = smooth_path([(0, -13), (6, -2), (7, 5), (0, 11), (-7, 5), (-6, -2)], corners={0})
    sweat = node("Sweat", [shape("Glint", ellipse(3, 5), fill("CCFFFFFF"), x=-2, y=2)[1],
                           shape("Drop", drop, fill("FF8FD3FF") + stroke("FF3C9AE0", 2))[1]],
                 x=128, y=-96, nid_=ids["Sweat"], extra=' opacity="0"')[1]
    return [sweat, para("Hat", hats()), upper, para("Mouth", mouth()), para("Skull", [render]), stand_ins]


def build_head():
    head_clip = nid()
    _, head_clip_s = shape("HeadClip", head_geom(), sid=head_clip)
    # key light top-left, warm bounce bottom-right, occlusion at the rim
    head_paint = (
        radial(-60, -96, 300, [(0, "FFFFC566"), (0.38, "FFF7A632"), (0.72, FUR), (1, "FFCC680A")])
        + soft("AA9A4204", 30, 0, 0, inner=True)
        + soft("66FFDFA0", 12, -10, -12, inner=True)
    )
    head_base = shape("HeadBase", head_geom(), head_paint)[1]
    sheen = shape("HeadSheen", ellipse(190, 96), soft("77FFF4DC", 34), x=-44, y=-104, extra=clip(head_clip))[1]
    cast = shape("HeadCastShadow", head_geom(), soft("88702A00", 22, 0, 10))[1]
    ids["Head"] = nid()
    if RENDER_HEAD:
        head_vertex_ids.clear()   # no vector outline to reshape on a turn
        kids = render_head_kids()
    else:
        kids = [
            para("Hat", hats()), para("Tuft", tuft()), para("BrowL", brow("L")), para("BrowR", brow("R")),
            para("Glasses", glasses()),
            para("EyeL", eye("L")), para("EyeR", eye("R")), para("Nose", nose()), para("Mouth", mouth()),
            para("Freckles", freckles()), para("Muzzle", muzzle(head_clip)),
            para("Skull", [sheen, head_base, head_clip_s, cast]), para("EarL", ear("L")), para("EarR", ear("R")),
        ]
    head = node("Head", kids, y=-34, nid_=ids["Head"])[1]
    # every rotating node sits at the neck base: idle sway < talk gestures < agent state < pointer turn
    down = node("PivotDown", [head], y=-NECK_PIVOT)[1]
    ids["Sway"], ids["Gesture"], ids["ActHead"], ids["TurnPivot"] = nid(), nid(), nid(), nid()
    sway = node("Sway", [down], nid_=ids["Sway"])[1]
    gesture = node("Gesture", [sway], nid_=ids["Gesture"])[1]
    act = node("ActHead", [gesture], nid_=ids["ActHead"])[1]
    turn = node("TurnPivot", [act], y=NECK_PIVOT, nid_=ids["TurnPivot"])[1]
    return para("Head", [turn])


RENDER_TURN_X = {
    "P_EyeL": 7, "P_EyeR": 7, "P_BrowL": 6, "P_BrowR": 6, "P_Glasses": 7, "P_Mouth": 8, "P_Hat": 3,
    "P_Skull": 0, "P_Head": 10, "P_Body": -6, "P_Front": -6, "GazeL": 7, "GazeR": 7,
}
RENDER_TURN_Y = {
    "P_EyeL": 5, "P_EyeR": 5, "P_BrowL": 4, "P_BrowR": 4, "P_Glasses": 5, "P_Mouth": 6, "P_Hat": -2,
    "P_Skull": 0, "P_Head": 6, "P_Body": 3, "P_Front": 3, "GazeL": 6, "GazeR": 6,
}


# Parallax depth: px offset at full turn. Nearer parts travel further; ears and
# body travel against the turn, which is what sells the head as round.
TURN_X = {
    "P_Nose": 30, "P_Mouth": 24, "P_Muzzle": 18, "P_Freckles": 16,
    "P_EyeL": 15, "P_EyeR": 15, "P_BrowL": 13, "P_BrowR": 13,
    "P_Tuft": 6, "P_Skull": 3, "P_EarL": -14, "P_EarR": -14,
    "P_Head": 10, "P_Body": -6, "GazeL": 7, "GazeR": 7, "P_Glasses": 15, "P_Hat": 5,
}
TURN_Y = {
    "P_Nose": 20, "P_Mouth": 16, "P_Muzzle": 14, "P_Freckles": 12,
    "P_EyeL": 11, "P_EyeR": 11, "P_BrowL": 10, "P_BrowR": 10,
    "P_Tuft": -6, "P_Skull": 2, "P_EarL": -10, "P_EarR": -10,
    "P_Head": 6, "P_Body": 3, "GazeL": 6, "GazeR": 6, "P_Glasses": 11, "P_Hat": -5,
}


# ---------------------------------------------------------------- animation
def cubic(a=0.42, b=0.0, c=0.58, d=1.0):
    return f'<CubicEaseInterpolator x1="{a}" y1="{b}" x2="{c}" y2="{d}"/>'


def keyed(obj_id, prop, frames, interp="cubic"):
    kfs = []
    for fr, val in frames:
        if interp == "cubic":
            kfs.append(f'<KeyFrameDouble frame="{fr}" value="{f(val)}" interpolationType="cubic">{cubic()}</KeyFrameDouble>')
        else:
            kfs.append(f'<KeyFrameDouble frame="{fr}" value="{f(val)}" interpolationType="{interp}"/>')
    return f'<KeyedObject objectId="{obj_id}"><KeyedProperty property="{prop}">{"".join(kfs)}</KeyedProperty></KeyedObject>'


def anim(name, duration, keyed_objects, loop=True, aid=None):
    aid = aid or nid()
    lv = ' loopValue="loop"' if loop else ""
    return aid, f'<LinearAnimation duration="{duration}"{lv} name="{name}" id="{aid}">{"".join(keyed_objects)}</LinearAnimation>'


animations = []


BREATH = 0.012                 # chest scale at the top of a breath


def idle_anim():
    # the chest swells about the waist; the neck base (220 units above it) rises by the
    # same amount, so the head rides the breath instead of floating on its own
    lift = (WAIST_Y - NECK_PIVOT) * BREATH
    sway = [(0, 0), (60, 0.016), (120, 0), (180, -0.016), (240, 0)]
    k = [
        keyed(ids["Head"], "y", [(0, -34), (120, -34 - lift), (240, -34)]),
        keyed(ids["ChestFront"], "scaleY", [(0, 1), (120, 1 + BREATH), (240, 1)]),
        keyed(ids["ChestBack"], "scaleY", [(0, 1), (120, 1 + BREATH), (240, 1)]),
        keyed(ids["Sway"], "rotation", sway),
        keyed(ids["Torso"], "rotation", follow(sway, 18, 0.3, 240), "linear"),
        keyed(ids["EarR"], "rotation", [(0, 0), (150, 0), (155, 0.14), (161, -0.04), (168, 0), (240, 0)]),
        keyed(ids["EarL"], "rotation", [(0, 0), (40, 0), (45, -0.12), (51, 0.03), (58, 0), (240, 0)]),
    ]
    return anim("Idle", 240, k)


def blink_anim():
    frames = [(0, 1), (196, 1), (201, 0.06), (208, 1), (230, 1)]
    k = [keyed(ids["BlinkL"], "scaleY", frames, "linear"), keyed(ids["BlinkR"], "scaleY", frames, "linear")]
    return anim("Blink", 230, k)


def turn_anim(name, axis, table):
    """Joystick timeline: frame 0 is -1 (left/up), 50 is centre, 100 is +1."""
    prop = "x" if axis == "x" else "y"
    if RENDER_HEAD:
        table = RENDER_TURN_X if axis == "x" else RENDER_TURN_Y
    k = [keyed(ids[n], prop, [(0, -v), (50, 0), (100, v)], "linear") for n, v in table.items() if n in ids]
    if axis == "x":
        k.append(keyed(ids["TurnPivot"], "rotation", [(0, -0.035), (50, 0), (100, 0.035)], "linear"))
        # the eye on the far side of the turn foreshortens
        k.append(keyed(ids["BlinkL"], "scaleX", [(0, 0.86), (50, 1), (100, 1.04)], "linear"))
        k.append(keyed(ids["BlinkR"], "scaleX", [(0, 1.04), (50, 1), (100, 0.86)], "linear"))
        for vids in head_vertex_ids:
            for i, vid in vids.items():
                x0 = HEAD_PTS[i][0]
                # the side turning away tucks in, the side coming round fans out
                near = 18 if FLUFF_TIPS[i] < 0 else 10
                k.append(keyed(vid, "x", [(0, x0 + near), (50, x0), (100, x0 - (28 - near))], "linear"))
    return anim(name, 100, k, loop=False)


MOODS = {
    #            browL(y,rot)   browR(y,rot)  lidL lidR  eyeScale look(x,y)
    "neutral":   ((-78, 0.0),   (-78, 0.0),   -48, -48,  1.0,  (0, 0)),
    "happy":     ((-88, -0.06), (-88, 0.06),  -48, -48,  1.05, (0, 0)),
    "thinking":  ((-72, 0.16),  (-94, 0.08),  -30, -38,  1.0,  (7, -7)),
    "surprised": ((-100, 0.0),  (-100, 0.0),  -50, -50,  1.12, (0, 0)),
    "concerned": ((-84, -0.24), (-84, 0.24),  -36, -36,  1.0,  (0, 3)),
    "relaxed":   ((-80, -0.05), (-78, 0.04),  -16, -14,  1.0,  (-2, 4)),
}


def mood_anim(name):
    (bly, blr), (bry, brr), lid_l, lid_r, sc, (lx, ly) = MOODS[name]
    hold = lambda v: [(0, v)]
    k = [
        keyed(ids["BrowL"], "y", hold(bly), "linear"),
        keyed(ids["BrowL"], "rotation", hold(blr), "linear"),
        keyed(ids["BrowR"], "y", hold(bry), "linear"),
        keyed(ids["BrowR"], "rotation", hold(brr), "linear"),
        keyed(ids["LidL"], "y", hold(lid_l), "linear"),
        keyed(ids["LidR"], "y", hold(lid_r), "linear"),
    ]
    for side in "LR":
        k.append(keyed(ids[f"Eye{side}"], "scaleX", hold(sc), "linear"))
        k.append(keyed(ids[f"Eye{side}"], "scaleY", hold(sc), "linear"))
        s = 1 if side == "R" else -1
        k.append(keyed(ids[f"Look{side}"], "x", hold(-s * 3 + lx), "linear"))
        k.append(keyed(ids[f"Look{side}"], "y", hold(3 + ly), "linear"))
    return anim(f"Mood_{name}", 1, k, loop=False)


def viseme_anim(i):
    k = [keyed(ids[f"V{j}"], "opacity", [(0, 1 if j == i else 0)], "linear") for j in range(len(VISEMES))]
    return anim(f"Viseme_{VISEMES[i]}", 1, k, loop=False)


# Demo speech: phrases as (viseme, frames), with an interlude after each one.
PHRASES = [
    # "Hi! I'm Charlie."
    [(4, 7), (5, 9), (0, 6), (4, 7), (1, 8), (0, 5), (8, 8), (4, 8), (3, 5), (5, 10)],
    # "Let's learn some English!"
    [(3, 6), (5, 7), (3, 5), (8, 6), (0, 4), (3, 6), (5, 8), (7, 6), (3, 5), (0, 4), (8, 6), (1, 6), (0, 4),
     (5, 7), (6, 6), (3, 5), (3, 6), (5, 7), (8, 8)],
    # "Are you ready?"
    [(4, 9), (0, 3), (7, 7), (6, 6), (0, 3), (7, 6), (5, 7), (3, 5), (5, 9)],
]
INTERLUDE_LEN = 56

# Interludes: what Charlie does while not speaking. Each maps a property to
# keyframes relative to the interlude start; anything not listed rests.
GESTURE_REST = {
    ("Gesture", "y"): 0, ("Gesture", "rotation"): 0,
    ("BrowL", "y"): -79, ("BrowR", "y"): -79,
    ("LookL", "x"): 3, ("LookR", "x"): -3, ("LookL", "y"): 3, ("LookR", "y"): 3,
    ("BlinkL", "scaleY"): 1, ("BlinkR", "scaleY"): 1,
}
INTERLUDES = {
    "nod": {   # a warm nod
        ("Gesture", "y"): [(6, 0), (16, 7), (26, 0), (34, 4), (44, 0)],
        ("Gesture", "rotation"): [(6, 0), (20, 0.03), (44, 0)],
        ("BrowL", "y"): [(6, -79), (14, -86), (40, -86), (50, -79)],
        ("BrowR", "y"): [(6, -79), (14, -86), (40, -86), (50, -79)],
    },
    "aside": {   # brows up, a glance to the side, back to the listener
        ("Gesture", "rotation"): [(4, 0), (16, -0.05), (40, -0.05), (52, 0)],
        ("BrowL", "y"): [(4, -79), (12, -94), (38, -94), (48, -79)],
        ("BrowR", "y"): [(4, -79), (12, -88), (38, -88), (48, -79)],
        ("LookL", "x"): [(8, 3), (14, -7), (36, -7), (44, 3)],
        ("LookR", "x"): [(8, -3), (14, -13), (36, -13), (44, -3)],
        ("LookL", "y"): [(8, 3), (14, -2), (36, -2), (44, 3)],
        ("LookR", "y"): [(8, 3), (14, -2), (36, -2), (44, 3)],
    },
    "tilt": {   # head tilt with a double blink
        ("Gesture", "rotation"): [(2, 0), (16, 0.07), (42, 0.07), (54, 0)],
        ("Gesture", "y"): [(2, 0), (16, -3), (42, -3), (54, 0)],
        ("BlinkL", "scaleY"): [(10, 1), (13, 0.06), (17, 1), (21, 0.06), (25, 1)],
        ("BlinkR", "scaleY"): [(10, 1), (13, 0.06), (17, 1), (21, 0.06), (25, 1)],
    },
}
INTERLUDE_ORDER = ["nod", "aside", "tilt"]


def speech_bob(t0, length):
    """Small head movement that only runs while a phrase is being said."""
    y, r = [], []
    for i, t in enumerate(range(0, length, 14)):
        y.append((t0 + t, (-3, 0, -2, 1)[i % 4]))
        r.append((t0 + t, (0.015, 0, -0.012, 0.006)[i % 4]))
    y.append((t0 + length, 0))
    r.append((t0 + length, 0))
    return y, r


EXTRA_ASSETS, EXTRA_EVENTS = [], []


_SOUND_EVENTS = {}


def sound_event(sound, volume=1.0):
    """One AudioAsset + AudioEvent per file (sounds/<sound>.mp3), reused."""
    if sound not in _SOUND_EVENTS:
        aid, eid = nid(), nid()
        label = sound.replace("/", "_")
        vol = f' volume="{volume}"' if volume != 1.0 else ""
        EXTRA_ASSETS.append(f'<AudioAsset file="sounds/{sound}.mp3"{vol} name="{label}" id="{aid}"/>')
        EXTRA_EVENTS.append(f'<AudioEvent assetId="{aid}" name="sfx_{label}" id="{eid}"/>')
        _SOUND_EVENTS[sound] = eid
    return _SOUND_EVENTS[sound]


def trigger_key(event_id, frame):
    return (f'<KeyedObject objectId="{event_id}"><KeyedProperty property="trigger">'
            f'<KeyFrameCallback frame="{frame}"/></KeyedProperty></KeyedObject>')


def demo_anim():
    ramp = 2
    babble = []     # gibberish voice, one clip per phrase
    tracks = {key: [] for key in GESTURE_REST}
    vis = []
    t = 0
    for i, (phrase, gesture) in enumerate(zip(PHRASES, INTERLUDE_ORDER)):
        length = sum(d for _, d in phrase)
        babble.append((sound_event(f"babble_{i + 1}"), t))
        y, r = speech_bob(t, length)
        tracks[("Gesture", "y")] += y
        tracks[("Gesture", "rotation")] += r
        for v, d in phrase:
            vis.append((v, d))
            t += d
        vis.append((0, INTERLUDE_LEN))
        for key, frames in INTERLUDES[gesture].items():
            tracks[key] += [(t + fr, val) for fr, val in frames]
        t += INTERLUDE_LEN
    total = t
    k = []
    for (obj, prop), frames in tracks.items():
        rest = GESTURE_REST[(obj, prop)]
        frames = sorted(set(frames)) or [(0, rest)]
        if frames[0][0] > 0:
            frames.insert(0, (0, rest))
        if frames[-1][0] < total:
            frames.append((total, rest))
        k.append(keys(ids[obj], {prop: frames}))
    for j in range(len(VISEMES)):
        frames, tt, prev = [], 0, None
        for v, d in vis:
            val = 1 if v == j else 0
            if prev is None:
                frames.append((0, val))
            elif val != prev:
                frames.append((tt, prev))
                frames.append((tt + ramp, val))
            prev, tt = val, tt + d
        if prev != frames[0][1]:
            # hold to the end, then hand over to the loop's first viseme
            frames.append((total - ramp, prev))
        frames.append((total, frames[0][1]))
        k.append(keyed(ids[f"V{j}"], "opacity", frames, "linear"))
    for eid, frame in babble:
        k.append(f'<KeyedObject objectId="{eid}"><KeyedProperty property="trigger">'
                 f'<KeyFrameCallback frame="{frame}"/></KeyedProperty></KeyedObject>')
    return anim("Talk_demo", total, k)


def interlude_anims():
    out = []
    for name in INTERLUDE_ORDER:
        k = []
        for (obj, prop), rest in GESTURE_REST.items():
            frames = INTERLUDES[name].get((obj, prop))
            if frames is None:
                continue
            frames = list(frames)
            if frames[0][0] > 0:
                frames.insert(0, (0, rest))
            frames.append((INTERLUDE_LEN, rest))
            k.append(keys(ids[obj], {prop: frames}))
            if obj == "Gesture":
                # follow-through: the torso echoes the gesture, later and smaller
                lag = [(min(INTERLUDE_LEN, t + 6), v * 0.3) for t, v in frames]
                k.append(keys(ids["Follow"], {prop: [(0, 0)] + lag}))
        out.append(anim(f"Interlude_{name}", INTERLUDE_LEN, k, loop=False))
    return out


def talk_gesture_layer(interludes):
    """Real lip sync: while `mode` is talking and the host drives `viseme`, the head
    bobs during speech; after ~0.4 s with the mouth at rest Charlie does one
    random interlude, then waits for the next phrase."""
    bob_y, bob_r = speech_bob(0, 56)
    bob_id, bob = anim("Speaking_bob", 56, [keys(ids["Gesture"], {"y": bob_y, "rotation": bob_r}),
                                             keyed(ids["Follow"], "y", follow(bob_y, 6, 0.35, 56, step=4), "linear"),
                                             keyed(ids["Follow"], "rotation", follow(bob_r, 6, 0.3, 56, step=4), "linear")])
    rest = {"y": [(0, 0)], "rotation": [(0, 0)]}
    still_id, still = anim("Gesture_still", 60, [keys(ids["Gesture"], rest), keys(ids["Follow"], rest)], loop=False)
    off_id, off = anim("Gesture_off", 1, [keys(ids["Gesture"], rest), keys(ids["Follow"], rest)], loop=False)
    s_off, s_speak, s_wait, s_rest = nid(), nid(), nid(), nid()
    s_inter = [nid() for _ in interludes]
    talking = f'{cond_state("speaking")}{cond_bool("demo", "false")}'
    speaking = f'<TransitionViewModelCondition opValue="notEqual"><TransitionPropertyViewModelComparator><BindablePropertyNumber><DataBindContext sourcePathIds="{VM["vm"]}-{VM["viseme"]}" propertyKey="636"/></BindablePropertyNumber></TransitionPropertyViewModelComparator><TransitionValueNumberComparator value="0"/></TransitionViewModelCondition>'
    silent = cond_number("viseme", 0)
    leave = (f'<StateTransition stateToId="{s_off}" duration="250">{cond_state("speaking", "notEqual")}</StateTransition>'
             f'<StateTransition stateToId="{s_off}" duration="250">{cond_bool("demo", "true")}</StateTransition>')
    to_speak = f'<StateTransition stateToId="{s_speak}" duration="150">{speaking}</StateTransition>'
    states = (
        f'<AnimationState x="160" y="0" animationId="{off_id}" id="{s_off}">'
        f'<StateTransition stateToId="{s_wait}" duration="200">{talking}</StateTransition></AnimationState>'
        f'<AnimationState x="360" y="-120" animationId="{bob_id}" id="{s_speak}">'
        f'<StateTransition stateToId="{s_wait}" duration="200">{silent}</StateTransition>{leave}</AnimationState>'
        f'<AnimationState x="360" y="120" animationId="{still_id}" random="true" reset="true" id="{s_wait}">{to_speak}{leave}'
        + "".join(f'<StateTransition stateToId="{sid}" duration="150" enableExitTime="true" exitTimeIsPercetange="true" exitTime="100"/>'
                  for sid in s_inter)
        + "</AnimationState>"
        + "".join(f'<AnimationState x="{600 + 180 * i}" y="240" animationId="{aid}" reset="true" id="{sid}">{to_speak}{leave}'
                  f'<StateTransition stateToId="{s_rest}" duration="150" enableExitTime="true" exitTimeIsPercetange="true" exitTime="100"/>'
                  f'</AnimationState>' for i, (sid, (aid, _)) in enumerate(zip(s_inter, interludes)))
        + f'<AnimationState x="880" y="0" animationId="{still_id}" id="{s_rest}">{to_speak}{leave}</AnimationState>'
    )
    layer = (
        f'<StateMachineLayer name="Talk gestures" id="{nid()}">'
        f'<AnyState x="1200" y="-120"/><ExitState x="1360" y="-120"/>'
        f'<EntryState x="0" y="0"><StateTransition stateToId="{s_off}"/></EntryState>{states}</StateMachineLayer>'
    )
    return layer, bob + still + off + "".join(a for _, a in interludes)


# ---------------------------------------------------------------- view model
VM = {"vm": nid(), "inst": nid(), "viseme": nid(), "mood": nid(), "demo": nid(), "agentState": nid(),
      "celebrate": nid(), "fxRainbow": nid(), "fxSplash": nid(), "fxConfetti": nid()}
FX_TRIGGERS = ["fxRainbow", "fxSplash", "fxConfetti", "celebrate",
               "fxStar", "fxSuperStar", "fxHeartEyes", "fxStarStruck", "fxPopper", "fxGreatJob"]
LESSON_TRIGGERS = ["lessonStart", "lessonStop", "lessonStar", "lessonSuperStar", "fxStarPlain"]
for _t in FX_TRIGGERS + LESSON_TRIGGERS:
    VM.setdefault(_t, nid())
NUMBERS = ["glasses", "hat", "outfit", "stars"]
for _n in NUMBERS:
    VM.setdefault(_n, nid())


DEFAULTS = {"glasses": 1}      # the teacher wears her reading glasses unless told otherwise
# lk.agent.state (initializing, idle, listening, thinking, speaking) plus the client's own
# disconnected / connecting / pause, as the classroom's voice-assistant resource reports them
AGENT_STATES = ["disconnected", "connecting", "initializing", "idle", "listening", "thinking", "speaking", "pause"]


def cond_state(value, op="equal"):
    return (
        f'<TransitionViewModelCondition opValue="{op}"><TransitionPropertyViewModelComparator>'
        f'<BindablePropertyString><DataBindContext sourcePathIds="{VM["vm"]}-{VM["agentState"]}" propertyKey="635"/></BindablePropertyString>'
        f'</TransitionPropertyViewModelComparator><TransitionValueStringComparator value="{value}"/></TransitionViewModelCondition>'
    )


def view_model():
    return (
        f'<ViewModel defaultInstanceId="{VM["inst"]}" name="Teacher" id="{VM["vm"]}">'
        f'<ViewModelPropertyNumber name="viseme" id="{VM["viseme"]}"/>'
        f'<ViewModelPropertyNumber name="mood" id="{VM["mood"]}"/>'
        f'<ViewModelPropertyBoolean name="demo" id="{VM["demo"]}"/>'
        f'<ViewModelPropertyString name="agentState" id="{VM["agentState"]}"/>'
        + "".join(f'<ViewModelPropertyNumber name="{n}" id="{VM[n]}"/>' for n in NUMBERS)
        + "".join(f'<ViewModelPropertyTrigger name="{t}" id="{VM[t]}"/>' for t in FX_TRIGGERS + LESSON_TRIGGERS)
        +
        f'<ViewModelInstance exports="true" name="Default" id="{VM["inst"]}">'
        f'<ViewModelInstanceNumber propertyValue="0" viewModelPropertyId="{VM["viseme"]}"/>'
        f'<ViewModelInstanceNumber propertyValue="1" viewModelPropertyId="{VM["mood"]}"/>'
        f'<ViewModelInstanceBoolean propertyValue="false" viewModelPropertyId="{VM["demo"]}"/>'
        f'<ViewModelInstanceString propertyValue="connecting" viewModelPropertyId="{VM["agentState"]}"/>'
        + "".join(f'<ViewModelInstanceNumber propertyValue="{DEFAULTS.get(n, 0)}" viewModelPropertyId="{VM[n]}"/>' for n in NUMBERS)
        + "".join(f'<ViewModelInstanceTrigger viewModelPropertyId="{VM[t]}"/>' for t in FX_TRIGGERS + LESSON_TRIGGERS)
        +
        f'</ViewModelInstance></ViewModel>'
    )


def cond_trigger(prop):
    return (
        f'<TransitionViewModelCondition opValue="equal"><TransitionPropertyViewModelComparator>'
        f'<BindablePropertyTrigger><DataBindContext sourcePathIds="{VM["vm"]}-{VM[prop]}" propertyKey="686"/></BindablePropertyTrigger>'
        f'</TransitionPropertyViewModelComparator><TransitionValueTriggerComparator/></TransitionViewModelCondition>'
    )


CONVERTERS = []


def formula(name, tokens):
    """tokens: 'in', '(', ')', ('op', n), ('val', v), ('fn', n), ','"""
    xml = []
    for t in tokens:
        if t == "in":
            xml.append("<FormulaTokenInput/>")
        elif t == "(":
            xml.append("<FormulaTokenParenthesisOpen/>")
        elif t == ")":
            xml.append("<FormulaTokenParenthesisClose/>")
        elif t == ",":
            xml.append("<FormulaTokenArgumentSeparator/>")
        elif t[0] == "op":
            xml.append(f'<FormulaTokenOperation operationType="{t[1]}"/>')
        elif t[0] == "fn":
            xml.append(f'<FormulaTokenFunction functionType="{t[1]}"/>')
        else:
            xml.append(f'<FormulaTokenValue operationValue="{t[1]}"/>')
    cid = nid()
    CONVERTERS.append(f'<DataConverterFormula name="{name}" id="{cid}">{"".join(xml)}</DataConverterFormula>')
    return cid


def cond_number_conv(prop, value, conv, op="equal"):
    return (
        f'<TransitionViewModelCondition opValue="{op}"><TransitionPropertyViewModelComparator>'
        f'<BindablePropertyNumber><DataBindContext sourcePathIds="{VM["vm"]}-{VM[prop]}" propertyKey="636" converterId="{conv}"/></BindablePropertyNumber>'
        f'</TransitionPropertyViewModelComparator><TransitionValueNumberComparator value="{value}"/></TransitionViewModelCondition>'
    )


def cond_number(prop, value):
    return (
        f'<TransitionViewModelCondition opValue="equal"><TransitionPropertyViewModelComparator>'
        f'<BindablePropertyNumber><DataBindContext sourcePathIds="{VM["vm"]}-{VM[prop]}" propertyKey="636"/></BindablePropertyNumber>'
        f'</TransitionPropertyViewModelComparator><TransitionValueNumberComparator value="{value}"/></TransitionViewModelCondition>'
    )


def cond_bool(prop, value):
    return (
        f'<TransitionViewModelCondition opValue="equal"><TransitionPropertyViewModelComparator>'
        f'<BindablePropertyBoolean><DataBindContext sourcePathIds="{VM["vm"]}-{VM[prop]}" propertyKey="634"/></BindablePropertyBoolean>'
        f'</TransitionPropertyViewModelComparator><TransitionValueBooleanComparator value="{value}"/></TransitionViewModelCondition>'
    )


def selector_layer(name, prop, anim_ids, duration_ms, y_row, extra_state=None):
    """One state per value of a number property, every state reaching every other."""
    state_ids = [nid() for _ in anim_ids]
    states = []
    for i, (sid, aid) in enumerate(zip(state_ids, anim_ids)):
        trans = [
            f'<StateTransition stateToId="{state_ids[j]}" duration="{duration_ms}">{cond_number(prop, j)}</StateTransition>'
            for j in range(len(anim_ids)) if j != i
        ]
        if extra_state:
            trans.append(
                f'<StateTransition stateToId="{extra_state["id"]}" duration="{duration_ms}">{extra_state["enter"]}</StateTransition>'
            )
        x = 160 + (i % 5) * 180
        y = y_row + (i // 5) * 140
        states.append(f'<AnimationState x="{x}" y="{y}" animationId="{aid}" id="{sid}">{"".join(trans)}</AnimationState>')
    if extra_state:
        states.append(
            f'<AnimationState x="160" y="{y_row + 300}" animationId="{extra_state["anim"]}" id="{extra_state["id"]}">'
            f'<StateTransition stateToId="{state_ids[0]}" duration="{duration_ms}">{extra_state["leave"]}</StateTransition>'
            f'</AnimationState>'
        )
    return (
        f'<StateMachineLayer name="{name}" id="{nid()}">'
        f'<AnyState x="1100" y="-120"/><ExitState x="1250" y="-120"/>'
        f'<EntryState x="0" y="0"><StateTransition stateToId="{state_ids[0]}"/></EntryState>'
        + "".join(states)
        + "</StateMachineLayer>"
    )


def loop_layer(name, aid):
    sid = nid()
    return (
        f'<StateMachineLayer name="{name}" id="{nid()}">'
        f'<AnyState x="400" y="-120"/><ExitState x="560" y="-120"/>'
        f'<EntryState x="0" y="0"><StateTransition stateToId="{sid}"/></EntryState>'
        f'<AnimationState x="200" y="0" animationId="{aid}" id="{sid}"/>'
        f'</StateMachineLayer>'
    )


# ---------------------------------------------------------------- celebration fx
# One oneShot timeline in three beats, after the reference board:
#   0-40   a star rides up a rainbow trail
#   52-90  it pops: streaks splash out
#   58-200 star confetti fills the screen, drifts and fades
import random

FX_CENTER = (300, 486)
RAINBOW = ["FFFF5B4C", "FFFFC21A", "FF39C86A", "FF3AA8FF", "FF9B6BFF"]
CONFETTI = ["FFFFD21A", "FFFFB300", "FFF06BFF", "FFFF6A4A", "FF3AA8FF", "FFFFD21A"]
SPLASH = ["FFFFD21A", "FF3AA8FF", "FFF06BFF", "FFFFD21A", "FF3AA8FF"]
FX_LEN = 200

EASE_OUT = (0.2, 0.8, 0.3, 1.0)
EASE_IN_OUT = (0.42, 0.0, 0.58, 1.0)
BACK_OUT = (0.34, 1.56, 0.64, 1.0)


HOLD = "hold"                  # keep this key's value until the next one (a cut, not a blend)


def kf(frames, ease=EASE_IN_OUT):
    """frames: (frame, value) or (frame, value, ease) — ease shapes the segment leaving that key."""
    out = []
    for fr in frames:
        e = fr[2] if len(fr) > 2 else ease
        if e == HOLD:
            out.append(f'<KeyFrameDouble frame="{fr[0]}" value="{f(fr[1])}" interpolationType="hold"/>')
        elif e is None:
            out.append(f'<KeyFrameDouble frame="{fr[0]}" value="{f(fr[1])}" interpolationType="linear"/>')
        else:
            out.append(
                f'<KeyFrameDouble frame="{fr[0]}" value="{f(fr[1])}" interpolationType="cubic">{cubic(*e)}</KeyFrameDouble>'
            )
    return "".join(out)


def keys(obj_id, props):
    """props: {property: frames}"""
    body = "".join(f'<KeyedProperty property="{p}">{kf(fr)}</KeyedProperty>' for p, fr in props.items())
    return f'<KeyedObject objectId="{obj_id}">{body}</KeyedObject>'


def bezier(p, t):
    u = 1 - t
    return (
        u**3 * p[0][0] + 3 * u * u * t * p[1][0] + 3 * u * t * t * p[2][0] + t**3 * p[3][0],
        u**3 * p[0][1] + 3 * u * u * t * p[1][1] + 3 * u * t * t * p[2][1] + t**3 * p[3][1],
    )


def arc_samples(p, n):
    """n+1 points evenly spaced by arc length, with unit normals."""
    dense = [bezier(p, i / 400) for i in range(401)]
    acc = [0.0]
    for a, b in zip(dense, dense[1:]):
        acc.append(acc[-1] + math.dist(a, b))
    out = []
    for k in range(n + 1):
        target = acc[-1] * k / n
        i = min(range(len(acc)), key=lambda j: abs(acc[j] - target))
        a, b = dense[max(i - 1, 0)], dense[min(i + 1, 400)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        ln = math.hypot(dx, dy) or 1
        out.append((dense[i], (-dy / ln, dx / ln)))
    return out


def star_geom(w, points=5, inner=0.5, radius=0):
    r = f' cornerRadius="{f(radius)}"' if radius else ""
    return f'<Star width="{f(w)}" height="{f(w * 0.95)}" points="{points}" innerRadius="{inner}"{r} name="Path"/>'


def build_fx():
    """Effect art, authored hidden; returns the art plus one timeline per effect."""
    rng = random.Random(7)
    cx, cy = FX_CENTER

    # --- rainbow trail
    curve = [(10, 740), (40, 560), (290, 660), (cx, cy + 30)]
    samples = arc_samples(curve, 36)
    bands, trims = [], []
    for b, color in enumerate(RAINBOW):
        o = (b - 2) * 21
        pts = "".join(
            f'<StraightVertex x="{f(px + nx * o)}" y="{f(py + ny * o)}"/>' for (px, py), (nx, ny) in samples
        )
        trim = nid()
        trims.append(trim)
        bands.append(
            f'<Shape name="Band" id="{nid()}"><PointsPath name="Path">{pts}</PointsPath>'
            f'<Stroke thickness="22" cap="butt" join="round" name="Stroke"><SolidColor colorValue="{color}" name="C"/>'
            f'<TrimPath start="0" end="0" name="Trim" id="{trim}"/></Stroke></Shape>'
        )
    sparkles = []
    for i, frac in enumerate((0.18, 0.36, 0.55, 0.72, 0.88)):
        (px, py), _ = samples[int(frac * 36)]
        sid = nid()
        sparkles.append((sid, int(40 * (1 - math.sqrt(1 - frac)))))
        bands.insert(0, shape("Sparkle", star_geom(22, 4, 0.32, 2), fill("FFFFFFFF"), x=px + (8 if i % 2 else -6), y=py, sid=sid)[1]
                     .replace('<Shape ', '<Shape scaleX="0" scaleY="0" ', 1))
    rainbow = node("Rainbow", bands)[1]

    # --- hero star
    star_id = nid()
    star = shape(
        "BigStar", star_geom(128, 5, 0.52, 14),
        radial(-18, -22, 80, [(0, "FFFFE680"), (0.6, "FFFFC21A"), (1, "FFFFA000")]) + soft("55B06000", 10, 0, 8),
        x=cx, y=cy, sid=star_id,
    )[1].replace('<Shape ', '<Shape scaleX="0" scaleY="0" ', 1)
    ride_x, ride_y = [], []
    for fr in range(0, 41, 4):
        s = 1 - (1 - fr / 40) ** 2
        (px, py), _ = samples[round(s * 36)]
        ride_x.append((fr, px))
        ride_y.append((fr, py))

    # --- splash drops
    drops = []
    for i in range(16):
        ang = i / 16 * 2 * math.pi + rng.uniform(-0.12, 0.12)
        r0, r1 = rng.uniform(60, 80), rng.uniform(190, 300)
        w = rng.choice((16, 20, 26, 32))
        ln = w * rng.uniform(3.2, 4.5)
        pts = [(-ln, 0), (-ln * 0.35, -w * 0.42), (0, -w / 2), (w / 2, 0), (0, w / 2), (-ln * 0.35, w * 0.42)]
        did = nid()
        sh = shape("Drop", smooth_path(pts, corners={0}), fill(SPLASH[i % len(SPLASH)]), x=r0, sid=did)[1]
        sh = sh.replace('<Shape ', '<Shape scaleX="0" scaleY="0" ', 1)
        drops.append((did, r0, r1, rng.randint(0, 5)))
        drops_xml = node("Splash", [sh], x=cx, y=cy, extra=f' rotation="{f(ang)}"')[1]
        drops[-1] = drops[-1] + (drops_xml,)
    splash = node("Splash", [d[4] for d in drops])[1]

    # --- confetti
    bits = []
    for i in range(48):
        kind = rng.choices(("star", "dot", "spark"), weights=(5, 3, 2))[0]
        color = rng.choice(CONFETTI)
        if kind == "star":
            w = rng.choice((26, 34, 44, 56, 70))
            geom = star_geom(w, 5, 0.5, w * 0.1)
        elif kind == "dot":
            w = rng.choice((10, 14, 18))
            geom = ellipse(w, w)
        else:
            w = rng.choice((16, 22))
            geom = star_geom(w, 4, 0.35, 1)
            color = rng.choice(("FFFFFFFF", "FFFFD21A"))
        bid = nid()
        xml = shape("Confetti", geom, fill(color), x=cx, y=cy, sid=bid)[1].replace('<Shape ', '<Shape scaleX="0" scaleY="0" ', 1)
        bits.append(dict(
            id=bid, xml=xml, tx=rng.uniform(-30, 630), ty=rng.uniform(-40, 600), delay=rng.randint(0, 10),
            fly=rng.randint(22, 34), fall=rng.uniform(30, 90), jitter=rng.randint(-10, 10),
            sc=rng.uniform(0.8, 1.15), spin=rng.uniform(-1.5, 1.5), drift=rng.uniform(-20, 20),
        ))
    confetti = node("Confetti", [b["xml"] for b in bits])[1]

    fx = node("FX", [star, confetti, splash, rainbow])[1]

    def timeline(name, length, rainbow_at=None, splash_at=None, confetti_at=None, outro=None, cheer=None):
        k = []
        # star: rides the rainbow, or pops in at the centre
        if rainbow_at is not None:
            t = rainbow_at
            xs = [(t + fr, x, None) for fr, x in ride_x] + [(t + 48, cx, None)]
            ys = [(t + fr, y, None) for fr, y in ride_y] + [(t + 48, cy, None)]
            sc = [(0, 0, None), (t, 0.55), (t + 40, 1.0, BACK_OUT)]
            rot = [(0, -0.5), (t + 48, 0, EASE_OUT)]
        else:
            xs, ys = [(0, cx, None)], [(0, cy, None)]
            sc = [(0, 0, BACK_OUT), (12, 1.0)]
            rot = [(0, -0.6, EASE_OUT), (14, 0)]
        pop = splash_at if splash_at is not None else (rainbow_at + 52 if rainbow_at is not None else 8)
        if rainbow_at is None:
            pop = max(pop, 16)
        sc += [(pop, 1.0, EASE_OUT), (pop + 6, 1.32, EASE_IN_OUT), (pop + 16, 1.0), (outro, 1.0, EASE_IN_OUT), (outro + 16, 0)]
        rot += [(outro, 0, EASE_IN_OUT), (outro + 16, 0.9)]
        k.append(keys(star_id, {"x": xs, "y": ys, "scaleX": sc, "scaleY": sc, "rotation": rot}))

        if rainbow_at is not None:
            t = rainbow_at
            for trim in trims:
                k.append(keys(trim, {"end": [(0, 0), (t, 0, EASE_OUT), (t + 40, 1), (t + 80, 1, None), (t + 81, 0)],
                                     "start": [(0, 0), (t + 52, 0, EASE_IN_OUT), (t + 80, 1), (t + 81, 0, None)]}))
            for sid, t0 in sparkles:
                pulse = [(0, 0), (t + t0, 0, BACK_OUT), (t + t0 + 8, 1), (t + 60, 1), (t + 72, 0)]
                k.append(keys(sid, {"scaleX": pulse, "scaleY": pulse, "rotation": [(0, 0, None), (t + 72, 1.2)]}))

        if splash_at is not None:
            t = splash_at
            for did, r0, r1, d, _ in drops:
                k.append(keys(did, {
                    "x": [(0, r0), (t + d, r0, EASE_OUT), (t + 22 + d, r1, EASE_IN_OUT), (t + 42 + d, r1 + 25)],
                    "scaleX": [(0, 0), (t + d, 0, EASE_OUT), (t + 8 + d, 1.25, EASE_IN_OUT), (t + 28 + d, 1.0, EASE_IN_OUT), (t + 42 + d, 0)],
                    "scaleY": [(0, 0), (t + d, 0, BACK_OUT), (t + 8 + d, 1.0, EASE_IN_OUT), (t + 32 + d, 1.0, EASE_IN_OUT), (t + 42 + d, 0)],
                }))

        if confetti_at is not None:
            for b in bits:
                t0 = confetti_at + b["delay"]
                t1 = t0 + b["fly"]
                end = min(length - 2, outro + 10 + b["jitter"])
                sc_b = [(0, 0), (t0, 0, BACK_OUT), (t0 + 14, b["sc"]), (end - 14, b["sc"], EASE_IN_OUT), (end, 0)]
                k.append(keys(b["id"], {
                    "x": [(0, cx), (t0, cx, EASE_OUT), (t1, b["tx"], None), (end, b["tx"] + b["drift"])],
                    "y": [(0, cy), (t0, cy, EASE_OUT), (t1, b["ty"], None), (end, b["ty"] + b["fall"])],
                    "scaleX": sc_b, "scaleY": sc_b,
                    "rotation": [(0, 0), (t0, 0, None), (end, b["spin"])],
                }))

        # Charlie cheers: brows up, eyes wide, a grin
        a, z = cheer
        for side in "LR":
            sd = 1 if side == "R" else -1
            k.append(keys(ids[f"Brow{side}"], {
                "y": [(0, -78), (a, -78, BACK_OUT), (a + 10, -94), (z, -94), (z + 14, -78)],
                "rotation": [(0, 0), (a, 0), (a + 10, sd * 0.08), (z, sd * 0.08), (z + 14, 0)],
            }))
            k.append(keys(ids[f"Eye{side}"], {
                "scaleX": [(0, 1), (a, 1, BACK_OUT), (a + 10, 1.1), (z, 1.1), (z + 14, 1)],
                "scaleY": [(0, 1), (a, 1, BACK_OUT), (a + 10, 1.1), (z, 1.1), (z + 14, 1)],
            }))
        for j in range(len(VISEMES)):
            if j == 0:
                fr = [(0, 1, None), (a + 2, 1, None), (a + 5, 0, None), (z, 0, None), (z + 4, 1, None), (length, 1, None)]
            elif j == 5:
                fr = [(0, 0, None), (a + 2, 0, None), (a + 5, 1, None), (z, 1, None), (z + 4, 0, None), (length, 0, None)]
            else:
                fr = [(0, 0, None), (length, 0, None)]
            k.append(keys(ids[f"V{j}"], {"opacity": fr}))
        return anim(name, length, k, loop=False)

    timelines = {
        "fxRainbow": timeline("FX_Rainbow", 92, rainbow_at=0, outro=72, cheer=(40, 72)),
        "fxSplash": timeline("FX_Splash", 76, splash_at=8, outro=58, cheer=(4, 58)),
        "fxConfetti": timeline("FX_Confetti", 140, confetti_at=8, outro=118, cheer=(4, 118)),
        "celebrate": timeline("FX_Celebrate", FX_LEN, rainbow_at=0, splash_at=52, confetti_at=56, outro=170, cheer=(50, 160)),
    }
    return fx, timelines


def fx_layer(timelines):
    s_off = nid()
    states = {t: nid() for t in FX_TRIGGERS}
    outs = []
    for t in FX_TRIGGERS:
        if t == "fxStar":
            outs.append(f'<StateTransition stateToId="{states["fxStar"]}">{cond_trigger(t)}'
                        f'{cond_number_conv("stars", 0, MOD5, "notEqual")}</StateTransition>')
            outs.append(f'<StateTransition stateToId="{states["fxSuperStar"]}">{cond_trigger(t)}'
                        f'{cond_number_conv("stars", 0, MOD5)}</StateTransition>')
        else:
            outs.append(f'<StateTransition stateToId="{states[t]}">{cond_trigger(t)}</StateTransition>')
    # the lesson asks for a plain star explicitly, so its timing never changes
    outs.append(f'<StateTransition stateToId="{states["fxStar"]}">{cond_trigger("fxStarPlain")}</StateTransition>')
    off_out = "".join(outs)
    on = "".join(
        f'<AnimationState x="{160 + 200 * i}" y="160" animationId="{timelines[t][0]}" reset="true" id="{states[t]}">'
        f'<StateTransition stateToId="{s_off}" enableExitTime="true" exitTimeIsPercetange="true" exitTime="100"/>'
        f'</AnimationState>'
        for i, t in enumerate(FX_TRIGGERS)
    )
    empty_id, empty = anim("FX_off", 1, [], loop=False)
    layer = (
        f'<StateMachineLayer name="Effects" id="{nid()}">'
        f'<AnyState x="900" y="-120"/><ExitState x="1060" y="-120"/>'
        f'<EntryState x="0" y="0"><StateTransition stateToId="{s_off}"/></EntryState>'
        f'<AnimationState x="160" y="0" animationId="{empty_id}" id="{s_off}">{off_out}</AnimationState>'
        + on + "</StateMachineLayer>"
    )
    return layer, empty


# ---------------------------------------------------------------- classroom-style reactions
# Counterparts of the classroom stickers and star award: star / super-star,
# heart-eyes, star-struck, party-popper and a "Great job!" banner.
def hidden(xml):
    """Author the root element at scale 0; its timeline pops it in."""
    for tag in ("<Shape ", "<Node "):
        if xml.startswith(tag):
            return tag + 'scaleX="0" scaleY="0" ' + xml[len(tag):]
    raise ValueError(xml[:40])


def pop_scale(a, peak, z, size=1.0, out=12):
    return [(0, 0), (a, 0, BACK_OUT), (a + peak, size), (z, size, EASE_IN_OUT), (z + out, 0)]


def cheer_keys(a, z, length, mouth=5):
    k = []
    for side in "LR":
        sd = 1 if side == "R" else -1
        k.append(keys(ids[f"Brow{side}"], {
            "y": [(0, -78), (a, -78, BACK_OUT), (a + 10, -94), (z, -94), (z + 14, -78)],
            "rotation": [(0, 0), (a, 0), (a + 10, sd * 0.08), (z, sd * 0.08), (z + 14, 0)],
        }))
    for j in range(len(VISEMES)):
        if j == 0:
            fr = [(0, 1, None), (a + 2, 1, None), (a + 5, 0, None), (z, 0, None), (z + 4, 1, None), (length, 1, None)]
        elif j == mouth:
            fr = [(0, 0, None), (a + 2, 0, None), (a + 5, 1, None), (z, 1, None), (z + 4, 0, None), (length, 0, None)]
        else:
            fr = [(0, 0, None), (length, 0, None)]
        k.append(keys(ids[f"V{j}"], {"opacity": fr}))
    return k


def banner(name, text, x, y, colors, font_size=40, width=330):
    bid = nid()
    run_style = nid()
    ribbon = shape(
        "Ribbon", rect(width, font_size * 1.9, r=font_size * 0.95),
        linear(-width / 2, 0, width / 2, 0, [(0, colors[0]), (1, colors[1])])
        + soft("55FFFFFF", 6, 0, -6, inner=True) + stroke("FFFFFFFF", 4) + soft("55200A60", 14, 0, 8),
    )[1]
    txt = (
        f'<Text y="-2" sizingValue="autoWidth" originX="0.5" originY="0.5" name="Text">'
        f'<TextStylePaint fontSize="{font_size}" fontAssetId="{FONT_ID}" familyName="Inter" styleName="Bold" name="Style" id="{run_style}">'
        f'<Fill name="Fill"><SolidColor colorValue="FFFFFFFF" name="C"/></Fill></TextStylePaint>'
        f'<TextValueRun styleId="{run_style}" text="{text}" name="Run"/></Text>'
    )
    xml = f'<Node x="{x}" y="{y}" scaleX="0" scaleY="0" name="{name}" id="{bid}">{txt}{ribbon}</Node>'
    return bid, xml


def build_kk_fx():
    rng = random.Random(11)
    art, tl = [], {}

    # --- star award: a sunburst behind a big star that then flies up to the counter
    burst_id = nid()
    rays = []
    for i in range(12):
        a = i / 12 * 2 * math.pi
        w = 0.13
        pts = [(0, 0), (240 * math.cos(a - w), 240 * math.sin(a - w)), (240 * math.cos(a + w), 240 * math.sin(a + w))]
        rays.append(shape("Ray", smooth_path(pts, corners={0, 1, 2}), fill("33FFE27A"))[1])
    glow = shape("Glow", ellipse(240, 240), soft("44FFE680", 50))[1]
    burst = hidden(node("Sunburst", [glow] + rays, x=300, y=330, nid_=burst_id)[1])
    award_id = nid()
    award = hidden(shape(
        "AwardStar", star_geom(210, 5, 0.52, 22),
        radial(-30, -40, 150, [(0, "FFFFF4B0"), (0.5, "FFFFC21A"), (1, "FFF08C00")])
        + soft("66FFFFFF", 10, -8, -10, inner=True) + soft("77905000", 16, 0, 12),
        x=300, y=330, sid=award_id,
    )[1])
    twinkles = []
    for i in range(8):
        a = i / 8 * 2 * math.pi + 0.3
        r = rng.uniform(130, 175)
        tid = nid()
        twinkles.append((tid, hidden(shape("Twinkle", star_geom(rng.choice((22, 30, 38)), 4, 0.32, 1.5), fill("FFFFFFFF"),
                                           x=300 + r * math.cos(a), y=330 + r * math.sin(a), sid=tid)[1]), rng.randint(6, 20)))
    orbit_id = nid()
    orbit_stars = []
    for i in range(8):
        a = i / 8 * 2 * math.pi
        c = CONFETTI[i % len(CONFETTI)]
        orbit_stars.append(shape("OrbitStar", star_geom(34, 5, 0.5, 3), fill(c), x=170 * math.cos(a), y=170 * math.sin(a))[1])
    orbit = hidden(node("Orbit", orbit_stars, x=300, y=330, nid_=orbit_id)[1])
    super_id, super_banner = banner("SuperBanner", "SUPER STAR!", 300, 130, ("FFFF8A00", "FFFF3D7F"), 36, 300)
    art += [super_banner, award, orbit] + [t[1] for t in twinkles] + [burst]

    def star_award(name, length, big):
        k = []
        size = 1.25 if big else 1.0
        k.append(keys(award_id, {
            "scaleX": [(0, 0), (2, 0, BACK_OUT), (18, size), (62, size, EASE_IN_OUT), (90, 0.22 * size), (96, 0)],
            "scaleY": [(0, 0), (2, 0, BACK_OUT), (18, size), (62, size, EASE_IN_OUT), (90, 0.22 * size), (96, 0)],
            "rotation": [(0, -0.8, EASE_OUT), (18, 0), (62, 0, EASE_IN_OUT), (90, 1.2)],
            "x": [(0, 300), (62, 300, EASE_IN_OUT), (90, 300)],
            "y": [(0, 330), (62, 330, EASE_IN_OUT), (90, 30)],
        }))
        bs = [(0, 0), (4, 0, EASE_OUT), (20, 1.1 * size), (58, 1.1 * size, EASE_IN_OUT), (72, 0)]
        k.append(keys(burst_id, {"scaleX": bs, "scaleY": bs, "rotation": [(0, 0, None), (72, 0.9)]}))
        for tid, _, d in twinkles:
            tw = [(0, 0), (d, 0, BACK_OUT), (d + 8, 1), (d + 18, 0.4, EASE_IN_OUT), (d + 26, 1), (60, 0)]
            k.append(keys(tid, {"scaleX": tw, "scaleY": tw, "rotation": [(0, 0, None), (60, 1.5)]}))
        if big:
            os_ = [(0, 0), (14, 0, BACK_OUT), (28, 1), (60, 1, EASE_IN_OUT), (80, 1.6), (84, 0)]
            k.append(keys(orbit_id, {"scaleX": os_, "scaleY": os_, "rotation": [(0, 0, None), (84, 2.2)]}))
            k.append(keys(super_id, {"scaleX": pop_scale(10, 12, 74), "scaleY": pop_scale(10, 12, 74),
                                     "rotation": [(0, -0.2, BACK_OUT), (22, 0.03), (74, -0.03)]}))
        k += cheer_keys(6, 70, length)
        return anim(name, length, k, loop=False)

    tl["fxStar"] = star_award("FX_Star", 100, False)
    tl["fxSuperStar"] = star_award("FX_SuperStar", 100, True)

    # --- heart-eyes: eyes turn into beating hearts, little hearts float up
    hearts = []
    for i in range(10):
        hid = nid()
        x0, y0 = rng.uniform(170, 430), rng.uniform(300, 420)
        w = rng.choice((26, 34, 42))
        hearts.append(dict(id=hid, x0=x0, y0=y0, rise=rng.uniform(170, 260), sway=rng.uniform(-30, 30),
                           d=rng.randint(4, 40), sc=rng.uniform(0.8, 1.2),
                           xml=hidden(shape("FloatHeart", heart_geom(w), HEART_PAINT, x=x0, y=y0, sid=hid)[1])))
    art += [h["xml"] for h in hearts]

    def heart_eyes():
        length = 130
        k = []
        for side in "LR":
            beat = [(0, 0), (4, 0, BACK_OUT), (16, 1.1)]
            for t in range(16, 104, 20):
                beat += [(t + 6, 1.25, EASE_IN_OUT), (t + 12, 1.05)]
            beat += [(110, 1.1, EASE_IN_OUT), (122, 0)]
            k.append(keys(ids[f"HeartEye{side}"], {"scaleX": beat, "scaleY": beat}))
            k.append(keys(ids[f"Blink{side}"], {"opacity": [(0, 1, None), (8, 0, None), (116, 0, None), (118, 1, None)]}))
        for h in hearts:
            d = h["d"]
            k.append(keys(h["id"], {
                "x": [(0, h["x0"]), (d, h["x0"]), (d + 30, h["x0"] + h["sway"]), (d + 60, h["x0"] - h["sway"] / 2), (d + 80, h["x0"])],
                "y": [(0, h["y0"]), (d, h["y0"], None), (d + 80, h["y0"] - h["rise"])],
                "scaleX": pop_scale(d, 10, d + 66, h["sc"]), "scaleY": pop_scale(d, 10, d + 66, h["sc"]),
            }))
        k += cheer_keys(6, 110, length, mouth=5)
        return anim("FX_HeartEyes", length, k, loop=False)

    tl["fxHeartEyes"] = heart_eyes()

    # --- star-struck: spinning star eyes, an "oh!" mouth, sparkles around the head
    sparks = []
    for i in range(10):
        a = rng.uniform(0, 2 * math.pi)
        r = rng.uniform(170, 230)
        sid = nid()
        sparks.append((sid, rng.randint(6, 60), hidden(shape(
            "WowSpark", star_geom(rng.choice((18, 26, 34)), 4, 0.32, 1.5), fill(rng.choice(("FFFFFFFF", "FFFFD21A"))),
            x=300 + r * math.cos(a), y=290 + r * math.sin(a) * 0.8, sid=sid)[1])))
    art += [s_[2] for s_ in sparks]

    def star_struck():
        length = 120
        k = []
        for side in "LR":
            sd = 1 if side == "R" else -1
            sc = [(0, 0), (4, 0, BACK_OUT), (16, 1.0), (104, 1.0, EASE_IN_OUT), (114, 0)]
            k.append(keys(ids[f"StarEye{side}"], {"scaleX": sc, "scaleY": sc, "rotation": [(0, 0, None), (114, sd * 6.283)]}))
            k.append(keys(ids[f"Blink{side}"], {"opacity": [(0, 1, None), (8, 0, None), (108, 0, None), (110, 1, None)]}))
        for sid, d, _ in sparks:
            tw = [(0, 0), (d, 0, BACK_OUT), (d + 8, 1), (d + 20, 0.3, EASE_IN_OUT), (d + 30, 1), (min(d + 50, 116), 0)]
            k.append(keys(sid, {"scaleX": tw, "scaleY": tw}))
        k += cheer_keys(6, 104, length, mouth=6)
        return anim("FX_StarStruck", length, k, loop=False)

    tl["fxStarStruck"] = star_struck()

    # --- party poppers: two cones in the bottom corners shoot streamers and confetti
    popper_parts, popper_keys = [], []
    g = 0.11
    for side, (px, py, rot) in (("L", (88, 560, 0.55)), ("R", (512, 560, -0.55))):
        cone_id = nid()
        cone = shape(
            "Cone", smooth_path([(0, 46), (-30, -34), (30, -34)], corners={0, 1, 2}, corner_radius=4),
            linear(-30, 0, 30, 0, [(0, "FF7A4CFF"), (0.5, "FFB06BFF"), (1, "FF7A4CFF")]) + stroke("FFFFD21A", 3),
        )[1]
        rim = shape("Rim", ellipse(64, 16), fill("FFFFD21A"), y=-34)[1]
        cone_node = f'<Node x="{px}" y="{py}" rotation="{rot}" scaleX="0" scaleY="0" name="Popper{side}" id="{cone_id}">{rim}{cone}</Node>'
        popper_parts.append(cone_node)
        mx, my = px + 40 * math.sin(rot), py - 40 * math.cos(rot)
        popper_keys.append(keys(cone_id, {
            "scaleX": [(0, 0), (0, 0, BACK_OUT), (10, 1), (16, 1.15, EASE_IN_OUT), (22, 1), (96, 1, EASE_IN_OUT), (110, 0)],
            "scaleY": [(0, 0), (0, 0, BACK_OUT), (10, 1), (16, 0.85, EASE_IN_OUT), (22, 1), (96, 1, EASE_IN_OUT), (110, 0)],
        }))
        base_ang = -math.pi / 2 + rot
        for i in range(16):
            ang = base_ang + rng.uniform(-0.45, 0.45)
            v = rng.uniform(9, 14)
            vx, vy = v * math.cos(ang), v * math.sin(ang)
            pid = nid()
            if i % 4 == 0:   # curly streamer riding the trajectory
                pts = []
                for t in range(0, 41, 2):
                    x, y = mx + vx * t, my + vy * t + 0.5 * g * t * t
                    wob = 10 * math.sin(t * 0.6)
                    pts.append((x + wob * math.cos(ang + math.pi / 2), y + wob * math.sin(ang + math.pi / 2)))
                trim = nid()
                verts = "".join(f'<StraightVertex x="{f(x)}" y="{f(y)}"/>' for x, y in pts)
                color = rng.choice(CONFETTI[:5])
                popper_parts.append(
                    f'<Shape name="Streamer" id="{pid}"><PointsPath name="Path">{verts}</PointsPath>'
                    f'<Stroke thickness="6" cap="round" join="round" name="S"><SolidColor colorValue="{color}" name="C"/>'
                    f'<TrimPath start="0" end="0" name="Trim" id="{trim}"/></Stroke></Shape>'
                )
                popper_keys.append(keys(trim, {"end": [(0, 0), (14, 0, EASE_OUT), (44, 1)],
                                               "start": [(0, 0), (30, 0, EASE_IN_OUT), (70, 1)]}))
                continue
            kind = rng.choice(("rect", "star", "dot"))
            c = rng.choice(CONFETTI)
            geom = {"rect": rect(10, 18, r=2), "star": star_geom(22, 5, 0.5, 2), "dot": ellipse(11, 11)}[kind]
            popper_parts.append(hidden(shape("Bit", geom, fill(c), x=mx, y=my, sid=pid)[1]))
            xs, ys = [(0, mx, None), (14, mx, None)], [(0, my, None), (14, my, None)]
            for t in range(6, 91, 12):
                xs.append((14 + t, mx + vx * t * 0.9, None))
                ys.append((14 + t, my + vy * t + 0.5 * g * t * t * 0.55, None))
            sc = pop_scale(14, 6, 92, 1.0, 10)
            popper_keys.append(keys(pid, {"x": xs, "y": ys, "scaleX": sc, "scaleY": sc,
                                          "rotation": [(0, 0, None), (104, rng.uniform(-8, 8))]}))
    art += popper_parts
    tl["fxPopper"] = anim("FX_Popper", 112, popper_keys + cheer_keys(14, 96, 112), loop=False)

    # --- "Great job!" banner with sparkles
    gj_id, gj = banner("GreatJob", "Great job!", 300, 120, ("FF3AA8FF", "FF9B6BFF"), 46, 340)
    art.append(gj)
    gj_sparks = []
    for i, (dx, dy) in enumerate(((-190, -30), (185, -40), (-160, 50), (170, 45), (0, -70))):
        sid = nid()
        gj_sparks.append((sid, 8 + i * 5))
        art.append(hidden(shape("GJSpark", star_geom(30, 4, 0.32, 1.5), fill("FFFFD21A"), x=300 + dx, y=120 + dy, sid=sid)[1]))
    k = [keys(gj_id, {"scaleX": pop_scale(0, 14, 96, 1.0, 12), "scaleY": pop_scale(0, 14, 96, 1.0, 12),
                      "rotation": [(0, -0.25, BACK_OUT), (14, 0.04), (40, -0.03, EASE_IN_OUT), (70, 0.03, EASE_IN_OUT), (96, 0)]})]
    for sid, d in gj_sparks:
        tw = [(0, 0), (d, 0, BACK_OUT), (d + 8, 1), (d + 20, 0.3, EASE_IN_OUT), (d + 32, 1), (100, 0)]
        k.append(keys(sid, {"scaleX": tw, "scaleY": tw, "rotation": [(0, 0, None), (100, 2)]}))
    tl["fxGreatJob"] = anim("FX_GreatJob", 112, k + cheer_keys(4, 96, 112), loop=False)

    return node("ClassroomFX", art)[1], tl


# ---------------------------------------------------------------- sound
# ElevenLabs sound effects (sounds/*.mp3): each effect timeline fires its
# AudioEvent on the frame the action lands.
FX_VOLUME = 0.35   # effects sit under the voice, never over it
SFX_FOR = {
    "fxRainbow": ("rainbow", 0), "fxSplash": ("splash", 6), "fxConfetti": ("confetti", 8),
    "celebrate": ("celebrate", 0), "fxStar": ("star", 2), "fxSuperStar": ("super_star", 2),
    "fxHeartEyes": ("heart_eyes", 4), "fxStarStruck": ("star_struck", 4), "fxPopper": ("popper", 12),
    "fxGreatJob": ("great_job", 0),
}


def add_sounds(timelines):
    """Returns (assets, events) and splices a trigger key into each timeline."""
    assets, events, made = [], [], {}
    for trig, (sound, frame) in SFX_FOR.items():
        if sound not in made:
            aid, eid = nid(), nid()
            assets.append(f'<AudioAsset file="sounds/{sound}.mp3" volume="{FX_VOLUME}" name="{sound}" id="{aid}"/>')
            events.append(f'<AudioEvent assetId="{aid}" name="sfx_{sound}" id="{eid}"/>')
            made[sound] = eid
        tid, xml = timelines[trig]
        key = (f'<KeyedObject objectId="{made[sound]}"><KeyedProperty property="trigger">'
               f'<KeyFrameCallback frame="{frame}"/></KeyedProperty></KeyedObject>')
        timelines[trig] = (tid, xml.replace("</LinearAnimation>", key + "</LinearAnimation>"))
    return "".join(assets), "".join(events)


# ---------------------------------------------------------------- mini lesson
# A scripted demo of a speaking lesson: Charlie shows a word card and asks for
# it (his ElevenLabs voice, lip-synced from the character timings), "listens"
# while a kid voice answers (emulated input), "checks" it (emulated latency),
# then praises with a star or asks again. Started by `lessonStart`, aborted by
# `lessonStop`; `lessonStar` adds a star to the balance.
import json as _json
import re

LESSON_DIR = Path(__file__).resolve().parent.parent / "sounds" / "lesson"
INK = "FF2A1A4A"
LIP_LEAD = 1  # frames: the mouth shape leads the sound a touch


def char_viseme(ch, nxt):
    c = ch.lower()
    if c in "cs" and nxt.lower() == "h":
        return 8
    return {"a": 4, "e": 5, "i": 5, "y": 5, "o": 6, "u": 7, "w": 7, "q": 7, "m": 1, "b": 1, "p": 1,
            "f": 2, "v": 2, "j": 8}.get(c, 3 if c.isalpha() else 0)


def lip_sync(name):
    """[(viseme, start_frame, end_frame)] from an ElevenLabs alignment file."""
    a = _json.loads((LESSON_DIR / f"{name}.json").read_text())["alignment"]
    chars, st, en = a["characters"], a["character_start_times_seconds"], a["character_end_times_seconds"]
    segs = []
    for i, ch in enumerate(chars):
        v = char_viseme(ch, chars[i + 1] if i + 1 < len(chars) else "")
        s0, s1 = max(0, round(st[i] * 60) - LIP_LEAD), max(0, round(en[i] * 60) - LIP_LEAD)
        if v == 0 and ch == " " and en[i] - st[i] < 0.08:
            continue                      # a short word gap does not close the mouth
        if segs and segs[-1][0] == v:
            segs[-1][2] = s1
        else:
            segs.append([v, s0, s1])
    out = []
    for v, s0, s1 in segs:               # fold slivers into the previous shape
        if out and s1 - s0 < 3:
            out[-1][2] = s1
        else:
            out.append([v, s0, s1])
    return [tuple(x) for x in out]


def audio_frames(name):
    a = _json.loads((LESSON_DIR / f"{name}.json").read_text())["alignment"]
    return round(a["character_end_times_seconds"][-1] * 60)


def viseme_track(segs, length, start=0):
    """Opacity keys for every viseme over a [0, length] timeline."""
    timeline = [(0, start)]
    for v, s0, s1 in segs:
        timeline.append((start + s0, v))
        timeline.append((start + s1, 0))
    timeline.sort()
    k = []
    for j in range(len(VISEMES)):
        fr, prev = [(0, 1 if j == 0 else 0, None)], 1 if j == 0 else 0
        for t, v in timeline:
            val = 1 if v == j else 0
            if val != prev:
                fr.append((max(t - 2, fr[-1][0] + 1), prev, None))
                fr.append((t, val, None))
                prev = val
        if fr[-1][0] < length:
            fr.append((length, prev, None))
        k.append(keys(ids[f"V{j}"], {"opacity": fr}))
    return k


def text_node(text, size, color, x=0, y=0, name="Text", hidden=True):
    tid, sid = nid(), nid()
    op = ' opacity="0"' if hidden else ""
    return tid, (
        f'<Text x="{f(x)}" y="{f(y)}" sizingValue="autoWidth" originX="0.5" originY="0.5"{op} name="{name}" id="{tid}">'
        f'<TextStylePaint fontSize="{size}" fontAssetId="{FONT_ID}" familyName="Inter" styleName="Bold" name="Style" id="{sid}">'
        f'<Fill name="Fill"><SolidColor colorValue="{color}" name="C"/></Fill></TextStylePaint>'
        f'<TextValueRun styleId="{sid}" text="{text}" name="Run"/></Text>'
    )


import subprocess as _sp
_MP3_FRAMES = {}


def mp3_frames(rel):
    """Length of sounds/<rel>.mp3 in frames at 60 fps (afinfo, macOS)."""
    if rel not in _MP3_FRAMES:
        info = _sp.run(["afinfo", str(Path(__file__).resolve().parent.parent / "sounds" / f"{rel}.mp3")],
                       capture_output=True, text=True).stdout
        sec = float(re.search(r"estimated duration: ([0-9.]+)", info).group(1))
        _MP3_FRAMES[rel] = math.ceil(sec * 60)
    return _MP3_FRAMES[rel]


# ---- word scenes: each word's picture is a tiny scene with an entrance.
# Returns (xml parts inside the picture window, entrance keys, entrance length,
# entrance sound). Everything is authored at its final pose; the entrance keys
# start it off-stage, so the later lesson states can leave it alone.
WORD_ART = Path(__file__).resolve().parent.parent / "art" / "words"
WORD_SIZES = _json.loads((WORD_ART / "sizes.json").read_text())
WORD_ASSETS = {}


def art(name, width=None, height=None, x=0, y=0, win=None, iid=None, op=None):
    """An Image of art/words/<name>.png scaled to `width` (or `height`) units."""
    WORD_ASSETS.setdefault(name, nid())
    pw, ph = WORD_SIZES[name]
    sc = width / pw if width else height / ph
    iid = iid or nid()
    opacity = f' opacity="{op}"' if op is not None else ""
    return iid, (f'<Image x="{f(x)}" y="{f(y)}" scaleX="{f(sc)}" scaleY="{f(sc)}"{opacity} assetId="{WORD_ASSETS[name]}" '
                 f'name="{name}" id="{iid}">{clip(win) if win else ""}</Image>')


def word_assets_xml():
    return "".join(f'<ImageAsset file="art/words/{n}.png" name="word_{n}" id="{aid}"/>' for n, aid in WORD_ASSETS.items())


def scene_apple(win):
    ground = shape("Grass", rect(96, 14, r=6), fill("FF6ACB5C"), y=36, extra=clip(win))[1]
    tree_id, tree_art = art("tree", height=66, y=-31, win=win)
    sway_id, rock_id = nid(), nid()
    tree = f'<Node x="-16" y="29" name="TreeSway" id="{sway_id}">{tree_art}</Node>'   # pivots at the foot of the trunk
    apple_id = nid()
    _, apple = art("apple", width=22, win=win)
    apple_node = f'<Node x="20" y="25" name="FallingApple" id="{apple_id}"><Node name="Rock" id="{rock_id}">{apple}</Node></Node>'
    keys_ = [
        keys(tree_id, {"rotation": [(0, 0), (6, 0.06), (11, -0.05), (16, 0.03), (21, 0)]}),
        keys(apple_id, {
            "x": [(0, 0), (20, 0, EASE_IN_OUT), (34, 20)],
            "y": [(0, -18), (20, -18, (0.5, 0, 1, 1)), (34, 25, EASE_OUT), (40, 17, EASE_IN_OUT), (46, 25, EASE_OUT), (50, 23), (54, 25)],
            "scaleY": [(0, 1), (33, 1), (35, 0.8, EASE_OUT), (40, 1.05), (46, 0.92), (50, 1)],
            "scaleX": [(0, 1), (33, 1), (35, 1.18, EASE_OUT), (40, 0.96), (46, 1.06), (50, 1)],
        }),
    ]
    idle = [keys(sway_id, {"rotation": [(0, 0), (60, 0.035), (120, 0), (180, -0.03), (240, 0)]}),
            keys(rock_id, {"rotation": [(0, 0), (40, 0.07), (80, -0.05), (120, 0), (240, 0)],
                           "scaleY": [(0, 1), (150, 1), (156, 0.92), (162, 1.04), (168, 1), (240, 1)]})]
    return [apple_node, tree, ground], keys_, 56, "apple_fall", idle


def scene_car(win):
    car_id, w1, w2, honk = nid(), nid(), nid(), nid()
    road = shape("Road", rect(96, 8, r=4), fill("FF8E86A8"), y=34, extra=clip(win))[1]
    _, body = art("car", width=66, win=win)
    wheels = []
    for wid, wx in ((w1, -18.2), (w2, 17.4)):
        _, wheel = art("wheel", width=15, win=win)
        wheels.append(f'<Node x="{wx}" y="17" name="Wheel" id="{wid}">{wheel}</Node>')
    horn = "".join(shape("Beep", smooth_path([(36, -10 + d), (44, -14 + d * 2)], closed=False), stroke("FFFFC21A", 2.5), extra=clip(win))[1]
                   for d in (0, 6))
    shiver_id = nid()
    puffs, puff_ids = [], []
    for i in range(3):
        pid = nid()
        puff_ids.append(pid)
        puffs.append(shape("Puff", ellipse(9, 8), fill("CCC8C4D8"), x=-36, y=10, sid=pid, extra=clip(win))[1]
                     .replace("<Shape ", '<Shape opacity="0" ', 1))
    car = (f'<Node y="0" name="Car" id="{car_id}">{"".join(puffs)}'
           f'<Node name="Shiver" id="{shiver_id}">{wheels[0]}{wheels[1]}{body}</Node></Node>')
    horn_node = f'<Node opacity="0" name="Honk" id="{honk}">{horn}</Node>'
    spin = [(0, 0, None), (40, -14)]
    keys_ = [
        keys(car_id, {"x": [(0, -95), (36, 4, EASE_OUT), (42, -1), (46, 0)],
                      "y": [(0, 0), (8, -2), (16, 0), (24, -2), (32, 0), (40, 2), (44, -1), (48, 0)],
                      "rotation": [(0, 0), (36, 0), (39, 0.06), (44, -0.02), (48, 0)]}),
        keys(w1, {"rotation": spin}), keys(w2, {"rotation": spin}),
        keys(honk, {"opacity": [(0, 0, None), (48, 0, None), (50, 1, None), (56, 0, None), (60, 1, None), (68, 0)]}),
    ]
    idle = [keys(shiver_id, {"y": [(t, (0, -0.8)[i % 2]) for i, t in enumerate(range(0, 241, 5))]})]
    for i, pid in enumerate(puff_ids):
        t0 = i * 80
        idle.append(keys(pid, {
            "opacity": [(0, 0, None), (t0, 0, None), (t0 + 2, 0.9), (t0 + 60, 0), (240, 0)],
            "x": [(0, -36), (t0, -36), (t0 + 60, -50), (240, -36)],
            "y": [(0, 10), (t0, 10), (t0 + 60, -6), (240, 10)],
            "scaleX": [(0, 0.5), (t0, 0.5), (t0 + 60, 1.6), (240, 0.5)],
            "scaleY": [(0, 0.5), (t0, 0.5), (t0 + 60, 1.6), (240, 0.5)],
        }))
    return [horn_node, car, road], keys_, 70, "car_drive", idle


def scene_cat(win):
    cat_id, body_id, purr_id = nid(), nid(), nid()
    floor = shape("Floor", rect(96, 10, r=5), fill("FFE8DCC8"), y=36, extra=clip(win))[1]
    open_id, cat_open = art("cat", height=70, win=win)
    shut_id, cat_shut = art("cat_closed", height=70, win=win, op=0)
    purr = "".join(shape("Purr", smooth_path([(20 + i * 7, -18 - i * 5), (24 + i * 7, -21 - i * 5), (28 + i * 7, -18 - i * 5)], closed=False),
                         stroke("FFFFFFFF", 2.2), extra=clip(win))[1] for i in range(2))
    breath_id, lid_open, lid_shut = nid(), nid(), nid()
    # the blink gets its own closed-eyes copy: the purr's swap (entrance) and the
    # blink (idle loop) then never fight over one image
    _, blink_shut = art("cat_closed", height=70, win=win)
    cat = (f'<Node x="2" y="0" name="Cat" id="{cat_id}"><Node y="35" name="Seat" id="{body_id}">'
           f'<Node name="Breath" id="{breath_id}"><Node y="-35" name="Art">'
           f'<Node name="BlinkShut" id="{lid_shut}" opacity="0">{blink_shut}</Node>'
           f'{cat_shut}<Node name="BlinkOpen" id="{lid_open}">{cat_open}</Node></Node></Node></Node></Node>')
    purr_node = f'<Node opacity="0" name="PurrMarks" id="{purr_id}">{purr}</Node>'
    walk_y = [(t, (0, -3)[i % 2]) for i, t in enumerate(range(0, 41, 6))] + [(44, 0)]
    vib = [(0, 1), (44, 1)] + [(t, (1.03, 1)[i % 2]) for i, t in enumerate(range(48, 104, 4))] + [(108, 1)]
    keys_ = [
        keys(cat_id, {"x": [(0, -90), (40, 2, EASE_OUT)], "y": walk_y}),
        keys(body_id, {"scaleY": vib}),   # purring: a gentle breathing shiver from the seat up
        keys(open_id, {"opacity": [(0, 1, None), (48, 1, None), (49, 0, None), (100, 0, None), (101, 1, None)]}),
        keys(shut_id, {"opacity": [(0, 0, None), (48, 0, None), (49, 1, None), (100, 1, None), (101, 0, None)]}),
        keys(purr_id, {"opacity": [(0, 0, None), (48, 0), (54, 1), (96, 1), (104, 0)],
                       "y": [(0, 0), (48, 0), (104, -6)]}),
    ]
    # blinks live on wrappers, so they layer with the purr's eye swap instead of fighting it
    blink = lambda on, off: [(0, on, None), (90, on, None), (91, off, None), (97, off, None), (98, on, None),
                             (190, on, None), (191, off, None), (196, off, None), (197, on, None)]
    idle = [keys(breath_id, {"scaleY": [(0, 1), (60, 1.025), (120, 1), (180, 1.025), (240, 1)],
                             "scaleX": [(0, 1), (60, 0.99), (120, 1), (180, 0.99), (240, 1)]}),
            keys(lid_open, {"opacity": blink(1, 0)}), keys(lid_shut, {"opacity": blink(0, 1)})]
    return [purr_node, cat, floor], keys_, 108, "cat_purr", idle


def scene_bunny(win):
    bunny_id, rim_clip = nid(), nid()
    grass = shape("Grass", rect(96, 16, r=6), fill("FF6ACB5C"), y=36, extra=clip(win))[1]
    _, hole = art("hole", width=62, y=26, win=win)
    opening = shape("Opening", ellipse(30, 10), fill("FF2A160C"), y=24, extra=clip(win))[1]
    above = shape("AboveRim", rect(96, 80, 0.5, 1.0), y=25, sid=rim_clip)[1]   # bunny shows only above the opening
    _, bunny_art = art("bunny", height=52, win=rim_clip)
    bob_id = nid()
    bunny = f'<Node y="0" name="Bunny" id="{bunny_id}"><Node name="Bob" id="{bob_id}">{bunny_art}</Node></Node>'
    keys_ = [
        keys(bunny_id, {"y": [(0, 62), (10, 62, BACK_OUT), (24, -4), (30, 2), (34, 0)],
                        "scaleY": [(0, 1), (22, 1.1, EASE_IN_OUT), (28, 0.95), (32, 1)],
                        "rotation": [(0, 0), (30, 0), (34, -0.06), (38, 0.05), (42, -0.03), (46, 0)]}),
    ]
    idle = [keys(bob_id, {"rotation": [(0, 0), (50, 0.05), (100, -0.04), (140, 0), (240, 0)],
                          "y": [(0, 0), (150, 0), (158, -7, EASE_OUT), (166, 0), (172, -3), (178, 0), (240, 0)],
                          "scaleY": [(0, 1), (148, 1), (152, 0.9), (158, 1.06), (166, 0.95), (172, 1), (240, 1)]})]
    return [bunny, opening, hole, grass, above], keys_, 50, "bunny_pop", idle


def scene_sun(win):
    sun_id = nid()
    hill = shape("Hill", ellipse(130, 50), radial(0, -10, 70, [(0, "FF8CE69A"), (1, "FF3DBA5E")]), y=46, extra=clip(win))[1]
    _, sun_art = art("sun", width=50, win=win)
    glow_id = nid()
    sun = f'<Node y="-6" name="Sun" id="{sun_id}"><Node name="Glow" id="{glow_id}">{sun_art}</Node></Node>'
    # animate the wrapper: the image's own scale is what sizes it
    keys_ = [keys(sun_id, {"y": [(0, 50), (40, -6, EASE_OUT)],
                           "rotation": [(0, -0.3), (40, 0, EASE_OUT), (50, 0.06), (60, 0)],
                           "scaleX": [(0, 0.7), (40, 1, BACK_OUT)], "scaleY": [(0, 0.7), (40, 1, BACK_OUT)]})]
    idle = [keys(glow_id, {"rotation": [(0, 0), (60, 0.08), (120, 0), (180, -0.08), (240, 0)],
                           "scaleX": [(0, 1), (60, 1.06), (120, 1), (180, 1.06), (240, 1)],
                           "scaleY": [(0, 1), (60, 1.06), (120, 1), (180, 1.06), (240, 1)]})]
    return [hill, sun], keys_, 60, None, idle


SCENES = {"apple": scene_apple, "car": scene_car, "cat": scene_cat, "bunny": scene_bunny, "sun": scene_sun}
WORDS = ["apple", "car", "cat", "bunny", "sun"]
# Emulated LLM latency (frames at 60 fps) after each answer; deliberately uneven,
# the way a real model's replies are.
LLM_WAIT = {"prep": 70, ("apple", 0): 140, ("car", 0): 104, ("cat", 0): 96, ("cat", 1): 192,
            ("bunny", 0): 168, ("sun", 0): 118}
LONG_THINK = 150
WORD_IDLE = 240   # frames in the word scenes' idle loop
STAR_LEN = 100   # FX_Star / FX_SuperStar timeline length
GAP = 12   # frames of quiet between an effect finishing and Charlie speaking
SFX_AT = 2  # entrance sounds start here
STAR_SFX_AT = 6  # the star chime: frame 2 of FX_Star, plus a few frames for the trigger to arrive
PRAISE = {"apple": ("great", "c_great"), "car": ("welldone", "c_welldone"), "cat": ("super", "c_super"),
          "bunny": ("excellent", "c_excellent"), "sun": ("awesome", "c_awesome")}
BUBBLE_TEXTS = {
    "intro": "Let's learn new words!", **{f"say_{w}": f"Say: {w}!" for w in WORDS},
    "great": "Great job!", "welldone": "Well done!", "super": "Super!", "excellent": "Excellent!",
    "awesome": "Awesome!", "again": "Almost! Try again.", "outro": "You learned 5 words!",
}
HEARD = {w: (f"You said: {w}", "FF1E9E50") for w in WORDS}
HEARD["cap"] = ("You said: cap", "FFE0573C")


def build_lesson():
    L = {}
    # speech bubble under the star balance
    L["bubble"] = nid()
    btexts = {}
    parts = []
    for key, text in BUBBLE_TEXTS.items():
        tid, xml = text_node(text, 20, INK, y=-1)
        btexts[key] = tid
        parts.append(xml)
    tail = shape("Tail", smooth_path([(-10, 22), (10, 22), (0, 36)], corners={0, 1, 2}, corner_radius=2), fill("F7FFFFFF"))[1]
    box = shape("Box", rect(300, 46, r=23), fill("F7FFFFFF") + soft("44200A60", 10, 0, 5))[1]
    bubble = f'<Node x="300" y="92" scaleX="0" scaleY="0" name="Bubble" id="{L["bubble"]}">{"".join(parts)}{tail}{box}</Node>'

    # word card
    L["card"] = nid()
    pics, words, heard = {}, {}, {}
    cparts = []
    entrances, idle_keys = {}, []
    for w in WORDS:
        pid, win = nid(), nid()
        pics[w] = pid
        parts_, ekeys, elen, esound, idle = SCENES[w](win)
        entrances[w] = (ekeys, elen, esound)
        idle_keys += idle
        window_ = shape("Window", rect(96, 80, r=14), sid=win)[1]
        cparts.append(f'<Node x="-80" y="0" opacity="0" name="Scene_{w}" id="{pid}">{"".join(parts_)}{window_}</Node>')
        tid, xml = text_node(w, 34, INK, x=46, y=-14, name=f"Word_{w}")
        words[w] = tid
        cparts.append(xml)
    for h, (text, color) in HEARD.items():
        tid, xml = text_node(text, 15, color, x=46, y=22, name=f"Heard_{h}")
        heard[h] = tid
        cparts.append(xml)
    cbox = shape("CardBox", rect(290, 96, r=22), fill("F7FFFFFF") + soft("44200A60", 12, 0, 6))[1]
    card = f'<Node x="300" y="548" scaleX="0" scaleY="0" name="WordCard" id="{L["card"]}">{"".join(cparts)}{cbox}</Node>'

    # status pill: listening (mic + bars) / checking (spinner)
    L["status"], L["listen"], L["check"] = nid(), nid(), nid()
    bars = []
    for i in range(5):
        bid = nid()
        bars.append(bid)
    bar_xml = "".join(shape("Bar", rect(5, 18, r=2.5), fill("FFFFFFFF"), x=40 + i * 9, sid=bid)[1] for i, bid in enumerate(bars))
    mic = (shape("Mic", rect(10, 16, r=5), fill("FFFF5B7A"), x=-74, y=-3)[1]
           + shape("Stand", smooth_path([(-81, -2), (-81, 4), (-74, 10), (-67, 4), (-67, -2)], closed=False), stroke("FFFF5B7A", 2.5))[1])
    lt_id, lt = text_node("Listening", 14, "FFFFFFFF", x=-18, hidden=False)
    listen = f'<Node opacity="0" name="Listening" id="{L["listen"]}">{bar_xml}{mic}{lt}</Node>'
    dots = []
    for i in range(3):
        did = nid()
        dots.append(did)
    dot_xml = "".join(shape("Dot", ellipse(8, 8), fill("FFFFD21A"), x=-70 + i * 12, sid=did)[1] for i, did in enumerate(dots))
    ct_id, ct = text_node("Thinking", 14, "FFFFFFFF", x=14, hidden=False)
    ct2_id, ct2 = text_node("Still thinking", 14, "FFFFFFFF", x=22)
    L["think_text"], L["think_text_long"] = ct_id, ct2_id
    check = f'<Node opacity="0" name="Thinking" id="{L["check"]}">{dot_xml}{ct}{ct2}</Node>'
    pill = shape("StatusPill", rect(196, 38, r=19), fill("CC2A1A4A") + stroke("55FFFFFF", 1.5))[1]
    status = f'<Node x="300" y="476" scaleX="0" scaleY="0" name="Status" id="{L["status"]}">{listen}{check}{pill}</Node>'
    # bars sit to the right of the label
    status = status.replace('name="Bar"', 'name="Bar"')

    L["root"] = nid()
    root = f'<Node opacity="0" name="Lesson" id="{L["root"]}">{bubble}{status}{card}</Node>'
    L.update(btexts=btexts, pics=pics, words=words, heard=heard, bars=bars, dots=dots, entrances=entrances,
             idle_keys=idle_keys)
    return root, L


def lesson_states(L):
    """[(name, anim_xml, anim_id, length, fire_trigger_or_None)] in play order."""
    def pop(obj, show, length, popin=True):
        if not show:
            return [keys(obj, {"scaleX": [(0, 0, None)], "scaleY": [(0, 0, None)]})]
        sc = [(0, 0.6 if popin else 1, BACK_OUT), (12, 1), (length, 1)]
        return [keys(obj, {"scaleX": sc, "scaleY": sc})]

    def ui(length, bubble=None, word=None, heard=None, heard_at=0, status=None, pop_card=False, bubble_at=0):
        k = [keys(L["root"], {"opacity": [(0, 1, None)]})]
        if bubble is not None and bubble_at:
            sc = [(0, 0, None), (bubble_at, 0.6, BACK_OUT), (bubble_at + 12, 1), (length, 1)]
            k.append(keys(L["bubble"], {"scaleX": sc, "scaleY": sc}))
        else:
            k += pop(L["bubble"], bubble is not None, length)
        for key, tid in L["btexts"].items():
            k.append(keys(tid, {"opacity": [(0, 1 if key == bubble else 0, None)]}))
        k += pop(L["card"], word is not None, length, popin=pop_card)
        for w in WORDS:
            on = 1 if w == word else 0
            k.append(keys(L["pics"][w], {"opacity": [(0, on, None)]}))
            k.append(keys(L["words"][w], {"opacity": [(0, on, None)]}))
        for h, tid in L["heard"].items():
            if h == heard:
                k.append(keys(tid, {"opacity": [(0, 0, None), (heard_at, 0), (heard_at + 8, 1)],
                                    "y": [(0, 30), (heard_at, 30, BACK_OUT), (heard_at + 10, 22)]}))
            else:
                k.append(keys(tid, {"opacity": [(0, 0, None)]}))
        k += pop(L["status"], status is not None, length)
        k.append(keys(L["listen"], {"opacity": [(0, 1 if status == "listen" else 0, None)]}))
        k.append(keys(L["check"], {"opacity": [(0, 1 if status == "check" else 0, None)]}))
        return k

    def talk(line, length, delay=0):
        segs = lip_sync(line)
        k = viseme_track(segs, length, start=delay)
        y, r = speech_bob(delay, max(14, audio_frames(line)))
        k.append(keys(ids["Gesture"], {"y": [(0, 0)] + y + [(length, 0)], "rotation": [(0, 0)] + r + [(length, 0)]}))
        k.append(trigger_key(sound_event(f"lesson/{line}"), delay + 1))
        return k

    def listening_pose(length):
        k = [keys(ids["ActHead"], {"rotation": [(0, 0.07)], "y": [(0, 0), (40, 4), (80, 0)]})]
        for side in "LR":
            sd = 1 if side == "R" else -1
            k += [keys(ids[f"Lid{side}"], {"y": [(0, -44)]}),
                  keys(ids[f"Brow{side}"], {"y": [(0, -86)], "rotation": [(0, sd * 0.05)]}),
                  keys(ids[f"Look{side}"], {"x": [(0, -sd * 3)], "y": [(0, 3)]})]
        return k

    def thinking_pose(length):
        """Looks up and aside; past ~1.7 s glances to the other side, as if still working on it."""
        long_wait = length > LONG_THINK
        sw = 100   # frame of the second glance
        def two(a, b):
            return [(0, a), (sw, a, EASE_IN_OUT), (sw + 16, b)] if long_wait else [(0, a)]
        k = [keys(ids["ActHead"], {"rotation": two(-0.06, 0.05), "y": [(0, -2)]}),
             keys(ids["LidL"], {"y": two(-26, -32)}), keys(ids["LidR"], {"y": two(-32, -26)}),
             keys(ids["BrowL"], {"y": two(-76, -96), "rotation": two(0.1, -0.12)}),
             keys(ids["BrowR"], {"y": two(-96, -76), "rotation": two(0.12, -0.1)}),
             keys(ids["LookL"], {"x": two(11, -5), "y": [(0, -7)]}), keys(ids["LookR"], {"x": two(5, -11), "y": [(0, -7)]})]
        if long_wait:
            k.append(keys(L["think_text"], {"opacity": [(0, 1, None), (sw, 1), (sw + 8, 0)]}))
            k.append(keys(L["think_text_long"], {"opacity": [(0, 0, None), (sw, 0), (sw + 8, 1)]}))
        else:
            k.append(keys(L["think_text"], {"opacity": [(0, 1, None)]}))
            k.append(keys(L["think_text_long"], {"opacity": [(0, 0, None)]}))
        return k

    def mic_bars(start, dur, length):
        rng = random.Random(start)
        k = []
        for i, bid in enumerate(L["bars"]):
            fr = [(0, 0.3), (start, 0.3)]
            t = start
            while t < start + dur:
                t += rng.randint(4, 7)
                fr.append((min(t, start + dur), rng.uniform(0.5, 1.6)))
            fr += [(start + dur + 6, 0.3), (length, 0.3)]
            k.append(keys(bid, {"scaleY": fr}))
        return k

    def spinner(length):
        k = []
        for i, did in enumerate(L["dots"]):
            fr = []
            for b in range(0, length, 36):
                fr += [(b + i * 8, 0), (b + i * 8 + 9, -8), (b + i * 8 + 18, 0)]
            fr = sorted(x for x in fr if x[0] <= length)
            k.append(keys(did, {"y": [(0, 0)] + fr + [(length, 0)]}))
        return k

    states = []

    def add(name, length, k, fire=None):
        aid, xml = anim(f"Lesson_{name}", length, k, loop=False)
        states.append((name, xml, aid, length, fire))

    n = LLM_WAIT["prep"]
    add("prep", n, ui(n, status="check") + thinking_pose(n) + spinner(n))
    n = audio_frames("c_intro") + 24
    add("intro", n, ui(n, bubble="intro") + talk("c_intro", n))
    for idx, w in enumerate(WORDS):
        # the word's scene plays out (with its sound) before Charlie speaks
        ekeys, elen, esound = L["entrances"][w]
        lead = max(elen, SFX_AT + mp3_frames(esound) if esound else 0) + GAP
        n = lead + audio_frames(f"c_{w}") + 24
        k = ui(n, bubble=f"say_{w}", word=w, pop_card=True, bubble_at=lead) + ekeys + talk(f"c_{w}", n, delay=lead)
        if esound:
            k.append(trigger_key(sound_event(esound, FX_VOLUME), SFX_AT))
        add(f"say_{w}", n, k)
        attempts = ["cap", "cat"] if w == "cat" else [w]
        for a_i, answer in enumerate(attempts):
            kid = f"k_{answer}"
            start, dur = 20, audio_frames(kid)
            n = start + dur + 34
            add(f"listen_{w}_{a_i}", n, ui(n, word=w, heard=answer, heard_at=start + dur + 6, status="listen")
                + listening_pose(n) + mic_bars(start, dur, n)
                + [trigger_key(sound_event(f"lesson/{kid}"), start)])
            n = LLM_WAIT[(w, a_i)]
            add(f"think_{w}_{a_i}", n, ui(n, word=w, heard=answer, heard_at=0, status="check")
                + thinking_pose(n) + spinner(n))
            if answer != w:
                n = audio_frames("c_again") + 24
                k = ui(n, bubble="again", word=w, heard=answer, heard_at=0) + talk("c_again", n)
                k += [keys(ids["BrowL"], {"y": [(0, -84)], "rotation": [(0, -0.24)]}),
                      keys(ids["BrowR"], {"y": [(0, -84)], "rotation": [(0, 0.24)]})]
                add(f"again_{w}", n, k)
        # the star (its animation and its chime) goes first; the praise follows
        bubble, line = PRAISE[w]
        last = idx == len(WORDS) - 1
        star_tl, star_snd = ("fxSuperStar", "super_star") if last else ("fxStar", "star")
        lead = max(STAR_LEN, STAR_SFX_AT + mp3_frames(star_snd)) + GAP
        n = lead + audio_frames(line) + 24
        add(f"praise_{w}", n, ui(n, bubble=bubble, word=w, heard=w, heard_at=0, bubble_at=lead)
            + talk(line, n, delay=lead), fire="lessonSuperStar" if last else "lessonStar")
    n = audio_frames("c_outro") + 24
    add("outro", n, ui(n, bubble="outro") + talk("c_outro", n))
    add("party", FX_LEN + 10, ui(FX_LEN + 10, bubble="outro"), fire="celebrate")
    return states


def lesson_layer(L):
    states = lesson_states(L)
    off_id, off = anim("Lesson_off", 1, [keys(L["root"], {"opacity": [(0, 0, None)]})], loop=False)
    s_off = nid()
    sids = [nid() for _ in states]
    stop = f'<StateTransition stateToId="{s_off}" duration="200">{cond_trigger("lessonStop")}</StateTransition>'
    xml = [f'<AnimationState x="0" y="160" animationId="{off_id}" id="{s_off}">'
           f'<StateTransition stateToId="{sids[0]}" duration="200">{cond_trigger("lessonStart")}</StateTransition></AnimationState>']
    for i, ((name, _, aid, _, fires), sid) in enumerate(zip(states, sids)):
        nxt = sids[i + 1] if i + 1 < len(sids) else s_off
        fire_xml = (f'<StateMachineFireTrigger viewModelPathIds="{VM["vm"]}-{VM[fires]}" occursValue="atStart"/>'
                    if fires else "")
        xml.append(
            f'<AnimationState x="{160 + 180 * (i % 6)}" y="{(i // 6) * 140}" animationId="{aid}" reset="true" id="{sid}">'
            f'{fire_xml}<StateTransition stateToId="{nxt}" duration="200" enableExitTime="true" exitTimeIsPercetange="true" exitTime="100"/>'
            f'{stop}</AnimationState>'
        )
    layer = (f'<StateMachineLayer name="Lesson" id="{nid()}">'
             f'<AnyState x="1300" y="-120"/><ExitState x="1460" y="-120"/>'
             f'<EntryState x="-160" y="160"><StateTransition stateToId="{s_off}"/></EntryState>{"".join(xml)}</StateMachineLayer>')
    # a star earned in the lesson goes through the same path as the Star button
    star_listener = (
        f'<StateMachineListener targetId="0:2" name="Lesson star" id="{nid()}">'
        f'<ListenerInputTypeViewModel viewModelPathIds="{VM["vm"]}-{VM["lessonStar"]}" listenerTypeValue="viewModel"/>'
        f'{step_number("stars", PLUS1)}{fire("fxStarPlain")}</StateMachineListener>'
        f'<StateMachineListener targetId="0:2" name="Lesson super star" id="{nid()}">'
        f'<ListenerInputTypeViewModel viewModelPathIds="{VM["vm"]}-{VM["lessonSuperStar"]}" listenerTypeValue="viewModel"/>'
        f'{step_number("stars", PLUS1)}{fire("fxSuperStar")}</StateMachineListener>'
    )
    # word scenes keep living after their entrance: one looping layer, under the lesson
    idle_id, idle = anim("Word_idle", WORD_IDLE, L["idle_keys"])
    layer = loop_layer("Word idle", idle_id) + layer
    return layer, star_listener, off + idle + "".join(x for _, x, _, _, _ in states)


# ---------------------------------------------------------------- activity modes
MODES = ["idle", "listening", "thinking", "talking"]
BADGE = {}
PURPLE = "FF6A50EC"
BADGE_POS = (488, 118)          # beside her head, on the artboard


def bubble(w, h):
    """A white pill with a soft shadow, the badges' common backing."""
    return [shape("Pill", rect(w, h, r=h / 2), fill("FFFFFFFF") + stroke("FFE4DEFF", 2))[1],
            shape("PillShadow", rect(w, h, r=h / 2), soft("446A50EC", 10, 0, 6))[1]]


def build_badges():
    """One small sign per agent state, all at BADGE_POS, all authored hidden."""
    hidden = ' opacity="0"'
    # disconnected: an alarm clock — she is running late for the lesson
    BADGE["minute"], BADGE["hour"], BADGE["ring"] = nid(), nid(), nid()
    hands = [node("Minute", [shape("M", rect(3.5, 15, 0.5, 1, r=1.75), fill("FF1F1640"))[1]], nid_=BADGE["minute"])[1],
             node("Hour", [shape("H", rect(4, 10, 0.5, 1, r=2), fill(PURPLE))[1]], nid_=BADGE["hour"], extra=' rotation="2.2"')[1],
             shape("Hub", ellipse(6, 6), fill("FF1F1640"))[1]]
    bells = [shape("Bell", ellipse(16, 12), fill("FFFFC21A") + stroke("FFC08A00", 2), x=sx * 15, y=-20,
                   extra="")[1] for sx in (-1, 1)]
    legs = [shape("Leg", smooth_path([(sx * 10, 18), (sx * 15, 25)], closed=False), stroke("FF1F1640", 3.5))[1] for sx in (-1, 1)]
    face = [shape("Face", ellipse(40, 40), fill("FFFFFFFF") + stroke(PURPLE, 4))[1]]
    clock = node("Ring", hands + face + bells + legs, nid_=BADGE["ring"])[1]
    BADGE["clock"] = nid()
    sleep = node("Clock", [clock] + bubble(70, 70)[1:], y=-4, nid_=BADGE["clock"], extra=hidden + ' scaleX="1.35" scaleY="1.35"')[1]
    # connecting: three dots in a pill
    dots = []
    for i in range(3):
        BADGE[f"dot{i}"] = nid()
        dots.append(node(f"Dot{i}", [shape("D", ellipse(14, 14), fill(PURPLE))[1]], x=-24 + i * 24, nid_=BADGE[f"dot{i}"])[1])
    BADGE["connect"] = nid()
    connect = node("Connecting", dots + bubble(110, 52), nid_=BADGE["connect"], extra=hidden)[1]
    # initializing: a spinning arc and a twinkle
    BADGE["spin"] = nid()
    arc = [(14 * math.cos(math.radians(a)), 14 * math.sin(math.radians(a))) for a in range(-90, 181, 45)]
    spinner = node("Spin", [shape("Arc", smooth_path(arc, closed=False), stroke(PURPLE, 5))[1],
                            shape("Track", ellipse(28, 28), stroke("33" + PURPLE[2:], 5))[1]], x=-18, nid_=BADGE["spin"])[1]
    BADGE["twinkle"] = nid()
    twinkle = node("Twinkle", [shape("Star", star_geom(22, 4, 0.35, 2), fill("FFFFC21A"))[1]], x=20, nid_=BADGE["twinkle"])[1]
    BADGE["init"] = nid()
    init = node("Initializing", [spinner, twinkle] + bubble(96, 52), nid_=BADGE["init"], extra=hidden)[1]
    # listening: an equaliser
    bars = []
    for i in range(4):
        BADGE[f"bar{i}"] = nid()
        bars.append(node(f"Bar{i}", [shape("B", rect(8, 26, r=4), fill(PURPLE))[1]], x=-21 + i * 14,
                         nid_=BADGE[f"bar{i}"], extra=' scaleY="0.4"')[1])
    BADGE["listen"] = nid()
    listen = node("Listening", bars + bubble(96, 52), nid_=BADGE["listen"], extra=hidden)[1]
    # thinking: a thought cloud with bouncing dots, two puffs leading back to her head
    tdots = []
    for i in range(3):
        BADGE[f"tdot{i}"] = nid()
        tdots.append(node(f"TDot{i}", [shape("D", ellipse(12, 12), fill(PURPLE))[1]], x=-20 + i * 20, nid_=BADGE[f"tdot{i}"])[1])
    cloud = []
    for x, y, w, h in ((0, 0, 104, 56), (-30, -16, 46, 42), (6, -22, 52, 46), (34, -10, 40, 36)):
        cloud.append(shape("Puff", ellipse(w, h), fill("FFFFFFFF"), x=x, y=y)[1])
    cloud_shadow = [shape("PuffShadow", ellipse(w, h), soft("446A50EC", 10, 0, 6), x=x, y=y)[1]
                    for x, y, w, h in ((0, 0, 104, 56), (-30, -16, 46, 42), (6, -22, 52, 46), (34, -10, 40, 36))]
    trail = [shape("Trail", ellipse(d, d), fill("FFFFFFFF") + soft("336A50EC", 6, 0, 3), x=x, y=y)[1]
             for x, y, d in ((-58, 36, 18), (-80, 56, 11))]
    BADGE["think"] = nid()
    think = node("Thinking", tdots + cloud + cloud_shadow + trail, nid_=BADGE["think"], extra=hidden)[1]
    # pause: two bars
    pbars = [shape("P", rect(9, 24, r=3), fill(PURPLE), x=x)[1] for x in (-8, 8)]
    BADGE["pause"] = nid()
    pause = node("Pause", pbars + bubble(72, 52), nid_=BADGE["pause"], extra=hidden)[1]
    BADGE["root"] = nid()
    return node("Badges", [sleep, connect, init, listen, think, pause], x=BADGE_POS[0], y=BADGE_POS[1], nid_=BADGE["root"])[1]


RUNNER = {}
RUN_IMAGES = {}              # name -> (asset id, file)
def run_image(name, file, x, y, scale=1.0):
    RUN_IMAGES.setdefault(name, (nid(), file))
    return (f'<Image x="{f(x)}" y="{f(y)}" scaleX="{f(scale)}" scaleY="{f(scale)}" '
            f'assetId="{RUN_IMAGES[name][0]}" name="{name}"/>')


RUN_FRAME_H = 610            # her height on the artboard while running


def build_runner():
    """Her run for `connecting`: an 8-frame sprite cycle. Each frame was redrawn by the image
    model from the rig's own anatomically correct pose (gen/gen_run_frames.py), then aligned
    on the head (gen/prep_run_frames.py). The rig adds the bob and the shadow."""
    import json as _json
    meta = _json.loads((OUT.parent / "art" / "run" / "frames.json").read_text())
    sc = RUN_FRAME_H / meta["h"]
    for k_ in ("root", "bob", "shadow", "fx"):
        RUNNER[k_] = nid()
    frames = []
    for i in range(meta["n"]):
        RUNNER[f"f{i}"] = nid()
        img = run_image(f"run_f{i}", f"art/run/f_{i}.png", 0, meta["h"] * sc / 2, sc)   # an Image is placed by its centre
        frames.append(node(f"Frame{i}", [img], nid_=RUNNER[f"f{i}"], extra=' opacity="0"' if i else "")[1])
    bob = node("Bob", frames, nid_=RUNNER["bob"])[1]
    shadow = node("Shadow", [shape("S", ellipse(150, 22), soft("44241A60", 10))[1]], y=RUN_FRAME_H - 8, nid_=RUNNER["shadow"])[1]
    fx_node = node("RunFx", [], nid_=RUNNER["fx"])[1]
    return node("Runner", [bob, shadow, fx_node], x=300, y=700 - RUN_FRAME_H, nid_=RUNNER["root"], extra=' opacity="0"')[1]


def run_cycle_anim():
    """The stride loop at 12 fps (5 animation frames per drawing), plus a small bob in step:
    lowest just after each contact (drawings 1 and 5), highest in flight (3 and 7)."""
    n, per = 8, 5
    L = n * per
    k = [keys(RUNNER[f"f{i}"], {"opacity": [(0, 1 if i == 0 else 0, HOLD)] + [(j * per, 1 if j == i else 0, HOLD) for j in range(1, n)] + [(L, 1 if i == 0 else 0, HOLD)]})
         for i in range(n)]
    bob = [0, 6, 2, -8, 0, 6, 2, -8, 0]
    k.append(keys(RUNNER["bob"], {"y": [(j * per, v) for j, v in enumerate(bob)]}))
    k.append(keys(RUNNER["shadow"], {"scaleX": [(j * per, 1 + v / 60) for j, v in enumerate(bob)]}))
    return anim("RunCycle", L, k)


TEAL_LIGHT, TEAL_MID = "FF4F9A84", "FF307568"   # the sleeve, sampled from the render
TEA = {}
TEA_FORE = 300


def build_tea_arm():
    """The `disconnected` routine: a forearm from below the frame holding a mug of tea.
    In Character units, inside the chest (in front of her face when she sips)."""
    for k_ in ("root", "elbow", "fore", "mug", "steam"):
        TEA[k_] = nid()
    steam = []
    for i, x in enumerate((-22, 0, 22)):
        TEA[f"steam{i}"] = nid()
        wisp = smooth_path([(0, 0), (8, -18), (-6, -36), (6, -54)], closed=False)
        steam.append(node(f"Steam{i}", [shape("Wisp", wisp, stroke("99FFFFFF", 7))[1]], x=x, y=-70, nid_=TEA[f"steam{i}"], extra=' opacity="0"')[1])
    mug = node("Mug", [node("SteamGroup", steam, nid_=TEA["steam"])[1],
                       shape("Tea", ellipse(74, 14), fill("FF8A5A3C"), y=-48)[1],
                       shape("Rim", ellipse(94, 22), fill("FFF4EFE6") + stroke("FFD9D1C2", 2), y=-48)[1],
                       shape("Band", rect(94, 20, 0.5, 0.5), fill("FF6A50EC"), y=-8)[1],
                       shape("Body", rect(94, 100, 0.5, 0.5, r=20), linear(-47, 0, 47, 0, [(0, "FFFFFFFF"), (1, "FFE4DDD0")]), y=0)[1],
                       shape("Handle", ellipse(42, 54), stroke("FFEDE7DB", 13), x=50, y=-4)[1]],
               x=-62, y=-6, nid_=TEA["mug"])[1]
    fingers = [shape("Finger", rect(30, 22, 0.5, 0.5, r=11), fill(SKIN) + soft("33A0583A", 4, 0, 2), x=-10, y=y)[1] for y in (-22, 0, 22)]
    hand = node("Hand", fingers + [mug, shape("Palm", ellipse(70, 84), radial(-10, -14, 56, [(0, "FFFFE0C8"), (1, SKIN)]))[1]], y=-TEA_FORE)[1]
    sleeve = shape("Sleeve", rect(96, TEA_FORE - 20, 0.5, 1, r=40), linear(-48, 0, 48, 0, [(0, TEAL_LIGHT), (1, TEAL_MID)]))[1]
    cuff = shape("Cuff", rect(98, 28, 0.5, 0.5, r=12), fill("FFF4F1EA"), y=-TEA_FORE + 34)[1]
    fore = node("Fore", [hand, cuff, sleeve], nid_=TEA["fore"], extra=' rotation="-0.4"')[1]
    elbow = node("Elbow", [fore], x=230, y=560, nid_=TEA["elbow"])[1]
    return node("TeaArm", [elbow], nid_=TEA["root"], extra=' opacity="0"')[1]


def badge_keys(active, tea=False):
    # the mug only exists in the disconnected routine; no sweat outside the run
    hide_sweat = [keys(ids["Sweat"], {"opacity": [(0, 0, None)]})]
    if not tea:
        hide_sweat.append(keys(TEA["root"], {"opacity": [(0, 0, HOLD)]}))
    return hide_sweat + [keys(BADGE[b], {"opacity": [(0, 1 if b == active else 0, None)]})
            for b in ("clock", "connect", "init", "listen", "think", "pause")]


def lean(rotation, y, scale_y=1.0):
    """The torso's posture for a state. Every state keys all three channels, so a state
    change always blends to a defined pose instead of keeping the last one."""
    as_frames = lambda v: v if isinstance(v, list) else [(0, v)]
    return [keyed(ids["Lean"], "rotation", as_frames(rotation), "linear"),
            keyed(ids["Lean"], "y", as_frames(y), "linear"),
            keyed(ids["Lean"], "scaleY", as_frames(scale_y), "linear")]


def agent_anims():
    """One looping timeline per agent state; the Agent layer picks by `agentState`.

    Posture follows the head (overlapping action): the head leads, the torso leans the
    same way about a third as far and a beat later; where the eyes move, they lead the head."""
    still_head = [keys(ids["ActHead"], {"rotation": [(0, 0)], "y": [(0, 0)]})]
    open_eyes = [keys(ids[f"Blink{sd}"], {"scaleY": [(0, 1)]}) for sd in "LR"]
    out = {}

    # disconnected: her routine while there is no lesson — tea and notes, 8 s on a loop.
    # The mug travels on arcs: the elbow swings out and up while the forearm turns, and
    # the mug counter-rotates to stay level, then tips ~30° to drink (after a small tip
    # back: anticipation). Held, it sways with her breath, so it is never a dead prop.
    #   0-50    holds it              50-75   brings it up under her chin
    #   75-115  blows on it (head bows to it, the steam is pushed aside)
    #   115-150 lifts it to her mouth  150-215 drinks, eyes shut, head back, two gulps
    #   215-265 lowers it              265-300 a contented "ahh" and a nod
    #   300-480 reads her notes: eyes scan down-left line by line, small nods
    L = 480
    W_ = (0.42, 0.0, 0.58, 1.0)
    #      frame: (elbow x, elbow y, forearm rotation, mug rotation relative to the hand)
    poses = [(0, (230, 560, -0.40, 0.40)), (25, (230, 556, -0.40, 0.43)), (50, (230, 560, -0.40, 0.40)),
             (75, (262, 420, -0.60, 0.60)), (115, (262, 424, -0.60, 0.60)),
             (142, (297, 244, -0.95, 0.95)), (150, (297, 240, -0.95, 1.02)), (160, (297, 240, -0.95, 0.45)),
             (180, (297, 236, -0.95, 0.40)), (190, (297, 240, -0.95, 0.45)), (205, (297, 235, -0.95, 0.40)),
             (215, (297, 240, -0.95, 0.95)), (265, (230, 560, -0.40, 0.40)),
             (330, (230, 556, -0.40, 0.43)), (390, (230, 561, -0.40, 0.38)), (450, (230, 556, -0.40, 0.42)), (L, (230, 560, -0.40, 0.40))]
    k = [keys(TEA["root"], {"opacity": [(0, 1, HOLD)]}),
         keys(TEA["elbow"], {"x": [(t, v[0], W_) for t, v in poses], "y": [(t, v[1], W_) for t, v in poses]}),
         keys(TEA["fore"], {"rotation": [(t, v[2], W_) for t, v in poses]}),
         keys(TEA["mug"], {"rotation": [(t, v[3], W_) for t, v in poses]}),
         # blowing pushes the steam aside; while the mug is up there is none to see
         keys(TEA["steam"], {"x": [(0, 0), (75, 0), (85, 26), (112, 26), (122, 0), (L, 0)],
                             "rotation": [(0, 0), (75, 0), (85, 0.35), (112, 0.35), (122, 0), (L, 0)],
                             "opacity": [(0, 1), (115, 1), (122, 0, HOLD), (265, 0), (285, 1), (L, 1)]})]
    for i in range(3):
        d = i * 16
        cyc = []
        for t0 in range(d, L, 48):
            cyc += [(t0, -70, HOLD), (t0 + 1, -70), (t0 + 46, -112, HOLD)]
        ops = []
        for t0 in range(d, L, 48):
            ops += [(t0, 0), (t0 + 14, 0.85), (t0 + 46, 0, HOLD)]
        k.append(keys(TEA[f"steam{i}"], {"y": [(0, -70, HOLD)] + cyc + [(L, -70)], "opacity": [(0, 0, HOLD)] + ops + [(L, 0)]}))
    head_rot = [(0, 0.02), (50, 0.02), (75, 0.05), (115, 0.05), (142, -0.03), (215, -0.04), (265, 0.0), (282, 0.04), (300, 0.0), (330, 0.04), (L, 0.02)]
    head_y = [(0, 2), (50, 2), (75, 7), (115, 7), (142, -6), (160, -9), (180, -7), (190, -9), (205, -7), (215, -9), (265, 0), (282, 5), (300, 0),
              (330, 3), (360, 5), (390, 3), (420, 5), (450, 3), (L, 2)]
    k.append(keys(ids["ActHead"], {"rotation": head_rot, "y": head_y}))
    k += lean(follow(head_rot, 10, 0.3, L), 0, 1.0)
    blink = [(0, 1), (146, 1), (152, 0.08), (214, 0.08), (222, 1), (L, 1)]
    k += [keys(ids["BlinkL"], {"scaleY": blink}), keys(ids["BlinkR"], {"scaleY": blink})]
    k += [keys(ids["BrowL"], {"y": [(0, -86), (215, -86), (235, -96), (300, -96), (330, -82), (L, -86)], "rotation": [(0, 0)]}),
          keys(ids["BrowR"], {"y": [(0, -86), (215, -86), (235, -96), (300, -96), (330, -82), (L, -86)], "rotation": [(0, 0)]})]
    # eyes: on the mug (they lead it up), shut while she drinks, then reading line by line
    read_x = [(330, -10), (360, 2), (366, -10), (396, 2), (402, -10), (432, 2), (438, -10), (468, 2)]
    for sd in "LR":
        s_ = 1 if sd == "R" else -1
        base = -s_ * 3
        k.append(keys(ids[f"Look{sd}"], {"x": [(0, base + 8), (70, base + 6), (110, base + 4), (130, base + 2), (300, base), (330, base - 10)]
                                               + [(t_, base + v) for t_, v in read_x] + [(L, base + 8)],
                                          "y": [(0, 9), (70, 12), (110, 12), (130, 2), (300, 3), (330, 10), (L, 9)]}))
    out["disconnected"] = anim("Agent_disconnected", L, k + badge_keys(None, tea=True))

    # connecting: the lesson is starting — a surprised double take toward the door (eyes
    # first), then the Arrival layer dashes her out of frame and she runs.
    k = open_eyes + [keys(ids["ActHead"], {"rotation": [(0, 0), (8, -0.02), (16, 0.05)], "y": [(0, 0), (8, -6)]})]
    k += lean([(0, 0), (12, -0.02), (20, 0.03)], 0)
    k += [keys(ids["BrowL"], {"y": [(0, -104)], "rotation": [(0, 0)]}), keys(ids["BrowR"], {"y": [(0, -104)], "rotation": [(0, 0)]})]
    for sd in "LR":
        s_ = 1 if sd == "R" else -1
        k.append(keys(ids[f"Look{sd}"], {"x": [(0, -s_ * 3), (6, -s_ * 3 + 12)], "y": [(0, 3)]}))
    k += [keys(TEA["root"], {"opacity": [(0, 1, HOLD), (12, 0, HOLD)]}),
          keys(TEA["elbow"], {"y": [(0, 560, (0.55, 0, 0.85, 0.45)), (12, 900)]})]
    out["connecting"] = anim("Agent_connecting", 30, k + badge_keys(None, tea=True), loop=False)

    # initializing: she perks up and gets ready
    k = open_eyes + [keys(ids["ActHead"], {"rotation": [(0, -0.02), (60, 0.02), (120, -0.02)], "y": [(0, -4), (60, -2), (120, -4)]}),
                     keys(ids["BrowL"], {"y": [(0, -94)]}), keys(ids["BrowR"], {"y": [(0, -94)]}),
                     keys(BADGE["spin"], {"rotation": [(0, 0, None), (120, math.tau * 2, None)]}),
                     keys(BADGE["twinkle"], {"scaleX": [(0, 0.6), (30, 1.2), (60, 0.6), (90, 1.2), (120, 0.6)],
                                             "scaleY": [(0, 0.6), (30, 1.2), (60, 0.6), (90, 1.2), (120, 0.6)]})]
    k += lean(follow([(0, -0.02), (60, 0.02), (120, -0.02)], 12, 0.3, 120), -3, 1.01)   # sits up, ready
    out["initializing"] = anim("Agent_initializing", 120, k + badge_keys("init"))

    # listening: Charlie's attentive nod, plus the equaliser
    nod = [(0, 0), (10, 8), (26, 0), (36, 6), (52, 0), (180, 0), (190, 8), (206, 0), (360, 0)]
    nod_r = [(0, 0.13), (10, 0.18), (26, 0.13), (36, 0.17), (52, 0.13), (180, 0.13), (190, 0.18), (206, 0.13), (360, 0.13)]
    k = open_eyes + [keys(ids["ActHead"], {"rotation": nod_r, "y": nod})]
    for side in "LR":
        sd = 1 if side == "R" else -1
        k += [keys(ids[f"Lid{side}"], {"y": [(0, -44)]}),
              keys(ids[f"Brow{side}"], {"y": [(0, -92)], "rotation": [(0, sd * 0.05)]}),
              keys(ids[f"Look{side}"], {"x": [(0, -sd * 3)], "y": [(0, 3)]})]
    heights = [(0.4, 1.0, 0.5, 0.8), (0.9, 0.3, 1.0, 0.4), (0.5, 0.8, 0.3, 1.0), (1.0, 0.5, 0.7, 0.3)]
    for i in range(4):
        h = heights[i]
        k.append(keys(BADGE[f"bar{i}"], {"scaleY": [(j * 30, h[j % 4]) for j in range(12)] + [(360, h[0])]}))
    k += lean(0.03, follow(nod, 8, 0.3, 360, offset=2), 0.99)   # leans in; each nod reaches the shoulders a beat later
    out["listening"] = anim("Agent_listening", 360, k + badge_keys("listen"))

    # thinking: eyes up and aside, a thought cloud with bouncing dots
    k = open_eyes + [
        keys(ids["ActHead"], {"rotation": [(0, -0.06)], "y": [(0, -2)]}),
        keys(ids["LidL"], {"y": [(0, -26)]}), keys(ids["LidR"], {"y": [(0, -32)]}),
        keys(ids["BrowL"], {"y": [(0, -76)], "rotation": [(0, 0.1)]}),
        keys(ids["BrowR"], {"y": [(0, -96)], "rotation": [(0, 0.12)]}),
        keys(ids["LookL"], {"x": [(0, 11)], "y": [(0, -7)]}),
        keys(ids["LookR"], {"x": [(0, 5)], "y": [(0, -7)]}),
    ]
    for i in range(3):
        d = i * 8
        k.append(keys(BADGE[f"tdot{i}"], {"y": [(0, 0), (d, 0), (d + 10, -8), (d + 20, 0), (54, 0)]}))
    k += lean(-0.014, -1, 1.006)
    out["thinking"] = anim("Agent_thinking", 54, k + badge_keys("think"))

    # idle: in the call but nobody's turn: a calm, friendly wait with a slow sway
    drift = [(0, 0), (120, 0.02), (240, 0)]
    k = open_eyes + [keys(ids["ActHead"], {"rotation": drift, "y": [(0, 0)]})] + lean(follow(drift, 16, 0.3, 240), 0)
    out["idle"] = anim("Agent_idle", 240, k + badge_keys(None))

    # speaking: the mouth (viseme) and the talk gestures do the work
    out["speaking"] = anim("Agent_speaking", 1, still_head + open_eyes + lean(0, 0) + badge_keys(None), loop=False)

    # pause: she waits calmly, eyes lowered
    settle = [(0, 8), (180, 11), (360, 8)]
    k = open_eyes + [keys(ids["ActHead"], {"rotation": [(0, 0.05)], "y": settle})] + lean(0.012, follow(settle, 10, 0.4, 360), 0.985)
    for side in "LR":
        sd = 1 if side == "R" else -1
        k += [keys(ids[f"Lid{side}"], {"y": [(0, -12)]}), keys(ids[f"Look{side}"], {"x": [(0, -sd * 3)], "y": [(0, 11)]}),
              keys(ids[f"Brow{side}"], {"y": [(0, -80)], "rotation": [(0, 0)]})]
    out["pause"] = anim("Agent_pause", 360, k + badge_keys("pause"))
    return out


def routine_mouth_layer():
    """The tea routine's mouth, in step with Agent_disconnected: blow ("oo"), a sip (lips
    closed on the mug), a contented "ahh". After the Mouth layer, so it wins only there;
    in every other state its empty timeline leaves the viseme alone."""
    seq = [(0, 0), (76, 7), (114, 0), (152, 1), (214, 0), (268, 6), (298, 0), (480, 0)]
    frames = {j: [] for j in range(len(VISEMES))}
    for t, v in seq:
        for j in range(len(VISEMES)):
            frames[j].append((t, 1 if j == v else 0))
    k = [keyed(ids[f"V{j}"], "opacity", frames[j], "hold") for j in range(len(VISEMES))]
    tea_id, tea = anim("Mouth_tea", 480, k)
    off_id, off = anim("Mouth_tea_off", 1, [], loop=False)
    press_id, press = anim("Mouth_think", 1, [keyed(ids[f"V{j}"], "opacity", [(0, 1 if j == 1 else 0)], "hold")
                                              for j in range(len(VISEMES))], loop=False)
    tea += press
    s_off, s_on, s_think = nid(), nid(), nid()
    xml = (f'<StateMachineLayer name="Routine mouth" id="{nid()}"><AnyState x="600" y="-120"/><ExitState x="760" y="-120"/>'
           f'<EntryState x="0" y="0"><StateTransition stateToId="{s_off}"/></EntryState>'
           f'<AnimationState x="200" y="0" animationId="{off_id}" id="{s_off}">'
           f'<StateTransition stateToId="{s_on}">{cond_state("disconnected")}</StateTransition>'
           f'<StateTransition stateToId="{s_think}">{cond_state("thinking")}</StateTransition></AnimationState>'
           f'<AnimationState x="400" y="0" animationId="{tea_id}" id="{s_on}">'
           f'<StateTransition stateToId="{s_off}">{cond_state("disconnected", "notEqual")}</StateTransition></AnimationState>'
           f'<AnimationState x="400" y="140" animationId="{press_id}" id="{s_think}">'
           f'<StateTransition stateToId="{s_off}">{cond_state("thinking", "notEqual")}</StateTransition></AnimationState>'
           f'</StateMachineLayer>')
    return xml, tea + off


def arrival_layer():
    """Who is on screen: the teacher (home) or the runner. On `connecting` she dashes out
    (anticipation: a step back, then off fast) and the runner runs in; when the agent is
    there (any state but connecting / disconnected) the runner runs out ahead and the
    teacher comes in after her, brakes, squashes and settles. Lost connection mid-run
    blends straight back home."""
    ch, rn, ln = ids["Character"], RUNNER["root"], ids["Lean"]
    fast_out = (0.55, 0.0, 0.85, 0.45)
    home = anim("Arrive_home", 1, [keys(ch, {"x": [(0, 300)], "opacity": [(0, 1, HOLD)], "scaleX": [(0, 0.84)], "scaleY": [(0, 0.84)]}),
                                   keys(BADGE["root"], {"opacity": [(0, 1)]}),
                                   keys(rn, {"x": [(0, 300)], "opacity": [(0, 0, HOLD)]})], loop=False)
    dash = anim("Arrive_dash", 64, [
        keys(ch, {"x": [(0, 300), (16, 270, EASE_IN_OUT), (24, 270, fast_out), (40, 1000)], "opacity": [(0, 1, HOLD), (40, 0, HOLD)],
                  "scaleX": [(0, 0.84), (24, 0.84), (34, 1.09), (40, 1.09)], "scaleY": [(0, 0.84), (24, 0.84), (34, 0.76), (40, 0.76)]}),
        keys(ln, {"rotation": [(0, 0), (16, -0.06), (24, -0.06), (32, 0.12), (40, 0.12)]}),
        keys(rn, {"x": [(0, -260, HOLD), (40, -260, EASE_OUT), (64, 300)], "opacity": [(0, 0, HOLD), (40, 1, HOLD)]})], loop=False)
    run = anim("Arrive_run", 1, [keys(ch, {"x": [(0, 1000)], "opacity": [(0, 0, HOLD)]}), keys(BADGE["root"], {"opacity": [(0, 0)]}),
                                 keys(rn, {"x": [(0, 300)], "opacity": [(0, 1, HOLD)]})], loop=False)
    arrive = anim("Arrive_in", 60, [
        keys(rn, {"x": [(0, 300, fast_out), (18, 1000)], "opacity": [(0, 1, HOLD), (18, 0, HOLD)]}),
        keys(ch, {"x": [(0, -400, HOLD), (16, -400, EASE_OUT), (40, 316, EASE_IN_OUT), (50, 300)], "opacity": [(0, 0, HOLD), (16, 1, HOLD)],
                  "scaleX": [(0, 1.09), (16, 1.09), (26, 0.84)], "scaleY": [(0, 0.76), (16, 0.76), (26, 0.84)]}),
        keys(ln, {"rotation": [(0, 0.1), (30, 0.1), (40, -0.08), (50, 0.02), (60, 0)],
                  "scaleY": [(0, 1), (38, 1), (42, 0.86), (44, 0.86), (52, 1.04), (60, 1)], "y": [(0, 0), (38, 0), (42, 12), (44, 12), (52, -4), (60, 0)]}),
        keys(BADGE["root"], {"opacity": [(0, 0, HOLD), (46, 0), (58, 1)]})], loop=False)
    s_ = {n: nid() for n in ("home", "dash", "run", "arrive")}
    here = cond_state("connecting", "notEqual") + cond_state("disconnected", "notEqual")
    done = '<StateTransition stateToId="{to}" enableExitTime="true" exitTimeIsPercetange="true" exitTime="100"/>'
    states = [
        ("home", home[0], f'<StateTransition stateToId="{s_["dash"]}">{cond_state("connecting")}</StateTransition>'),
        ("dash", dash[0], f'<StateTransition stateToId="{s_["arrive"]}" enableExitTime="true" exitTimeIsPercetange="true" exitTime="100">{here}</StateTransition>'
                          f'<StateTransition stateToId="{s_["home"]}" duration="300">{cond_state("disconnected")}</StateTransition>'
                          + done.format(to=s_["run"])),
        ("run", run[0], f'<StateTransition stateToId="{s_["arrive"]}">{here}</StateTransition>'
                        f'<StateTransition stateToId="{s_["home"]}" duration="300">{cond_state("disconnected")}</StateTransition>'),
        ("arrive", arrive[0], f'<StateTransition stateToId="{s_["dash"]}">{cond_state("connecting")}</StateTransition>' + done.format(to=s_["home"])),
    ]
    body = "".join(f'<AnimationState x="{200 + 200 * i}" y="{(i % 2) * 120}" animationId="{aid}" id="{s_[n]}">{tr}</AnimationState>'
                   for i, (n, aid, tr) in enumerate(states))
    xml = (f'<StateMachineLayer name="Arrival" id="{nid()}"><AnyState x="1100" y="-120"/><ExitState x="1250" y="-120"/>'
           f'<EntryState x="0" y="0"><StateTransition stateToId="{s_["home"]}"/></EntryState>{body}</StateMachineLayer>')
    return xml, home[1] + dash[1] + run[1] + arrive[1]


def agent_layer(anims_):
    """Every state reaches every other, on `agentState` alone."""
    sid = {st: nid() for st in AGENT_STATES}
    states = []
    for i, st in enumerate(AGENT_STATES):
        trans = "".join(f'<StateTransition stateToId="{sid[o]}" duration="300">{cond_state(o)}</StateTransition>'
                        for o in AGENT_STATES if o != st)
        states.append(f'<AnimationState x="{160 + (i % 4) * 200}" y="{(i // 4) * 160}" animationId="{anims_[st][0]}" id="{sid[st]}">{trans}</AnimationState>')
    return (f'<StateMachineLayer name="Agent" id="{nid()}"><AnyState x="1100" y="-120"/><ExitState x="1250" y="-120"/>'
            f'<EntryState x="0" y="0"><StateTransition stateToId="{sid["connecting"]}"/></EntryState>{"".join(states)}</StateMachineLayer>')


# ---------------------------------------------------------------- buttons
FONT_ID = None


def label(text, y):
    return (
        f'<Text y="{f(y)}" sizingValue="autoWidth" originX="0.5" originY="0.5" name="Label">'
        f'<TextStylePaint fontSize="12" fontAssetId="{FONT_ID}" familyName="Inter" styleName="Bold" name="LabelStyle" id="{{sid}}">'
        f'<Fill name="Fill"><SolidColor colorValue="FFFFFFFF" name="C"/></Fill></TextStylePaint>'
        f'<TextValueRun styleId="{{sid}}" text="{text}" name="Run"/></Text>'
    ).replace("{sid}", nid())


def icon(kind):
    W = "FFFFFFFF"
    if kind == "idle":
        face = shape("Smile", smooth_path([(-9, 2), (0, 8), (9, 2)], closed=False), stroke(W, 3.5))[1]
        eyes = [shape("Eye", ellipse(5, 5), fill(W), x=dx, y=-6)[1] for dx in (-7, 7)]
        return [face] + eyes
    if kind == "listening":
        dot = shape("Dot", ellipse(7, 7), fill(W), x=-8)[1]
        arcs = []
        for r in (9, 17):
            pts = [(-8 + r * math.cos(math.radians(a)), r * math.sin(math.radians(a))) for a in (-50, -25, 0, 25, 50)]
            arcs.append(shape("Arc", smooth_path(pts, closed=False), stroke(W, 3.2))[1])
        return [dot] + arcs
    if kind == "thinking":
        cloud = shape("Cloud", ellipse(30, 20), fill(W), y=-3)[1]
        puff = shape("Puff", ellipse(7, 6), fill(W), x=-12, y=11)[1]
        dots = [shape("D", ellipse(4.5, 4.5), fill("FF6A50EC"), x=dx, y=-3)[1] for dx in (-7, 0, 7)]
        return dots + [cloud, puff]
    if kind == "talking":
        bubble = shape("Bubble", rect(30, 21, r=7), fill(W), y=-3)[1]
        tail = shape("Tail", smooth_path([(-8, 6), (-2, 6), (-11, 14)], corners={0, 1, 2}), fill(W))[1]
        lines = [shape("L", rect(w, 3, r=1.5), fill("FF6A50EC"), y=y)[1] for w, y in ((18, -7), (12, 0))]
        return lines + [bubble, tail]
    if kind == "fxRainbow":
        out = []
        for r, c in ((16, "FFFF5B4C"), (12, "FFFFC21A"), (8, "FF3AA8FF")):
            pts = [(r * math.cos(math.radians(a)), 6 + r * math.sin(math.radians(a))) for a in range(180, 361, 30)]
            out.append(shape("Band", smooth_path(pts, closed=False), stroke(c, 3.6, cap="butt"))[1])
        return out
    if kind == "fxSplash":
        out = [shape("Core", ellipse(7, 7), fill("FFFFD21A"))[1]]
        for i in range(6):
            a = i * math.pi / 3 + 0.3
            pts = [(7 * math.cos(a), 7 * math.sin(a)), (15 * math.cos(a), 15 * math.sin(a))]
            out.append(shape("Ray", smooth_path(pts, closed=False), stroke(SPLASH[i % 3], 3.6))[1])
        return out
    if kind == "fxConfetti":
        return [shape("S", star_geom(w, 5, 0.5, 1.5), fill(c), x=x, y=y)[1]
                for w, c, x, y in ((15, "FFFFD21A", -7, -5), (12, "FFF06BFF", 8, -6), (11, "FF3AA8FF", 1, 8))]
    if kind == "celebrate":
        big = shape("Star", star_geom(24, 5, 0.52, 3), fill("FFFFC21A"), y=1)[1]
        sp = [shape("Sp", star_geom(9, 4, 0.35, 0.5), fill(W), x=x, y=y)[1] for x, y in ((13, -11), (-14, -9))]
        return sp + [big]
    if kind == "glasses":
        lenses = [shape("L", ellipse(14, 14), stroke(W, 3), x=dx)[1] for dx in (-9, 9)]
        return lenses + [shape("B", smooth_path([(-2, -1), (2, -1)], closed=False), stroke(W, 3))[1]]
    if kind == "hat":
        crown = smooth_path([(-13, 8), (-14, -8), (-6, -1), (0, -11), (6, -1), (14, -8), (13, 8)], corners=set(range(7)), corner_radius=1.5)
        return [shape("Crown", crown, fill("FFFFD21A"))[1]]
    if kind == "outfit":
        tee = smooth_path([(-6, -11), (0, -7), (6, -11), (15, -5), (11, 1), (8, -1), (8, 12), (-8, 12), (-8, -1), (-11, 1), (-15, -5)],
                          corners=set(range(11)), corner_radius=1.5)
        return [shape("Tee", tee, fill(W))[1]]
    if kind == "reset":
        pts = [(11 * math.cos(math.radians(a)), 11 * math.sin(math.radians(a))) for a in range(-60, 241, 30)]
        arrow = shape("Head", smooth_path([(4, -16), (12, -9), (2, -5)], corners={0, 1, 2}), fill(W), x=1)[1]
        return [arrow, shape("Arc", smooth_path(pts, closed=False), stroke(W, 3))[1]]
    if kind == "lessonStart":
        return [shape("Play", smooth_path([(-7, -11), (12, 0), (-7, 11)], corners={0, 1, 2}, corner_radius=3), fill("FF39C86A"))[1]]
    if kind == "lessonStop":
        return [shape("Stop", rect(18, 18, r=4), fill("FFFF5B4C"))[1]]
    if kind == "fxStar":
        return [shape("Star", star_geom(30, 5, 0.52, 3), GOLD_PAINT)[1]]
    if kind == "fxSuperStar":
        sp = [shape("Sp", star_geom(9, 4, 0.35, 0.5), fill(W), x=x, y=y)[1] for x, y in ((14, -12), (-15, -10), (14, 12))]
        ring = shape("Ring", ellipse(36, 36), stroke("FFFFD21A", 2.5))[1]
        return sp + [shape("Star", star_geom(24, 5, 0.52, 3), GOLD_PAINT)[1], ring]
    if kind == "fxHeartEyes":
        return [shape("Heart", heart_geom(28), HEART_PAINT, y=1)[1]]
    if kind == "fxStarStruck":
        eyes = [shape("E", star_geom(10, 5, 0.5, 1), fill("FFF29A00"), x=dx, y=-4)[1] for dx in (-6, 6)]
        mouth = shape("M", ellipse(7, 8), fill("FF7A3112"), y=8)[1]
        return eyes + [mouth, shape("Face", ellipse(32, 32), fill("FFFFD54A"))[1]]
    if kind == "fxPopper":
        dots = [shape("D", ellipse(5, 5), fill(c), x=x, y=y)[1] for c, x, y in (("FFF06BFF", 6, -14), ("FF3AA8FF", 14, -6), ("FFFFD21A", 12, -16))]
        cone = shape("Cone", smooth_path([(-12, 14), (-6, -8), (8, 4)], corners={0, 1, 2}, corner_radius=2), fill("FFB06BFF"))[1]
        return dots + [cone]
    if kind == "fxGreatJob":
        star = shape("S", star_geom(12, 5, 0.5, 1), fill(W))[1]
        return [star, shape("Badge", rect(32, 22, r=11), linear(-16, 0, 16, 0, [(0, "FF3AA8FF"), (1, "FF9B6BFF")]))[1]]
    raise ValueError(kind)


def button(kind, text, x, y, with_ring=False, scale=1.0):
    hit_id = nid()
    hit = shape("Hit", ellipse(58, 58), fill("40FFFFFF") + stroke("80FFFFFF", 2) + soft("33200A60", 10, 0, 4), sid=hit_id)[1]
    parts = icon(kind)
    ring_id = None
    if with_ring:
        ring_id = nid()
        parts.append(shape("Active", ellipse(66, 66), stroke("FFFFD21A", 4), sid=ring_id)[1]
                     .replace('<Shape ', '<Shape opacity="0" ', 1))
    parts.append(hit)
    parts.append(label(text, 44))
    sc = f' scaleX="{scale}" scaleY="{scale}"' if scale != 1 else ""
    return hit_id, ring_id, node(f"Button_{kind}", parts, x=x, y=y, extra=sc)[1]


def set_number(prop, value):
    return (
        f'<ListenerViewModelChange><BindablePropertyNumber propertyValue="{value}">'
        f'<DataBindContext sourcePathIds="{VM["vm"]}-{VM[prop]}" propertyKey="636" direction="true"/>'
        f'</BindablePropertyNumber></ListenerViewModelChange>'
    )


def set_bool(prop, value):
    return (
        f'<ListenerViewModelChange><BindablePropertyBoolean propertyValue="{value}">'
        f'<DataBindContext sourcePathIds="{VM["vm"]}-{VM[prop]}" propertyKey="634" direction="true"/>'
        f'</BindablePropertyBoolean></ListenerViewModelChange>'
    )


def fire(prop):
    return (
        f'<ListenerViewModelChange><BindablePropertyTrigger propertyValue="1">'
        f'<DataBindContext sourcePathIds="{VM["vm"]}-{VM[prop]}" propertyKey="686" direction="true"/>'
        f'</BindablePropertyTrigger></ListenerViewModelChange>'
    )


def step_number(prop, conv):
    read = nid()
    return (
        f'<ListenerViewModelChange fromViewModelProperty="true" fromDataBindId="{read}"><BindablePropertyNumber>'
        f'<DataBindContext sourcePathIds="{VM["vm"]}-{VM[prop]}" propertyKey="636" converterId="{conv}" id="{read}"/>'
        f'<DataBindContext sourcePathIds="{VM["vm"]}-{VM[prop]}" propertyKey="636" direction="true"/>'
        f'</BindablePropertyNumber></ListenerViewModelChange>'
    )


def click(target, actions, name):
    return (
        f'<StateMachineListenerSingle targetId="{target}" listenerTypeValue="click" name="{name}" id="{nid()}">'
        f'{actions}</StateMachineListenerSingle>'
    )


MODE_BUTTONS = [("idle", "Спокій"), ("listening", "Слухаю"), ("thinking", "Думаю"), ("talking", "Говорю")]
FX_BUTTONS = [("fxRainbow", "Веселка"), ("fxSplash", "Бризки"), ("fxConfetti", "Зірки"), ("celebrate", "Свято")]
BUTTON_YS = (150, 250, 350, 450)
KK_BUTTONS = [("fxStar", "Зірка"), ("fxSuperStar", "Суперзірка"), ("fxHeartEyes", "Закоханий"),
              ("fxStarStruck", "Вау!"), ("fxPopper", "Хлопавка"), ("fxGreatJob", "Great job!")]
ART_H = 720


def star_balance():
    """Top-centre balance: five slots fill as `stars` grows, the total beside them."""
    parts = []
    for k in range(5):
        mapper, interp, group = nid(), nid(), nid()
        CONVERTERS.append(
            f'<DataConverterRangeMapper minInput="{k}" maxInput="{k + 1}" minOutput="0" maxOutput="1" '
            f'clampLower="true" clampUpper="true" name="Slot {k + 1}" id="{mapper}"/>'
            f'<DataConverterInterpolator duration="1.3" name="Ease slot {k + 1}" id="{interp}"/>'
            f'<DataConverterGroup name="Slot {k + 1} fill" id="{group}">'
            f'<DataConverterGroupItem converterId="{mapper}"/><DataConverterGroupItem converterId="{interp}"/></DataConverterGroup>'
        )
        x = -92 + 32 * k
        filled = (f'<Shape x="{x}" y="0" opacity="0" name="Filled">{star_geom(28, 5, 0.52, 3)}{GOLD_PAINT}'
                  f'<DataBindContext sourcePathIds="{VM["vm"]}-{VM["stars"]}" propertyKey="18" converterId="{group}"/></Shape>')
        empty = shape("Empty", star_geom(28, 5, 0.52, 3), fill("30FFFFFF") + stroke("70FFFFFF", 1.5), x=x)[1]
        parts += [filled, empty]
    to_text, run_style = nid(), nid()
    CONVERTERS.append(f'<DataConverterToString decimals="0" round="true" name="Stars as text" id="{to_text}"/>')
    parts.insert(0,
        f'<Text x="78" y="0" sizingValue="autoWidth" originX="0.5" originY="0.5" name="Count">'
        f'<TextStylePaint fontSize="22" fontAssetId="{FONT_ID}" familyName="Inter" styleName="Bold" name="CountStyle" id="{run_style}">'
        f'<Fill name="Fill"><SolidColor colorValue="FFFFFFFF" name="C"/></Fill></TextStylePaint>'
        f'<TextValueRun styleId="{run_style}" text="0" name="Run">'
        f'<DataBindContext sourcePathIds="{VM["vm"]}-{VM["stars"]}" propertyKey="268" converterId="{to_text}"/></TextValueRun></Text>'
    )
    pill = shape("Pill", rect(236, 48, r=24), fill("33200A60") + stroke("55FFFFFF", 1.5) + soft("33200A60", 10, 0, 4))[1]
    return node("StarBalance", parts + [pill], x=300, y=30)[1]


def build_buttons():
    xml, listeners, rings = [], [], []
    for i, ((kind, text), y) in enumerate(zip(MODE_BUTTONS, BUTTON_YS)):
        hit, ring, b = button(kind, text, 52, y, with_ring=True)
        xml.append(b)
        rings.append(ring)
        talking = "true" if kind == "talking" else "false"
        listeners.append(click(hit, set_number("mode", i) + set_bool("demo", talking), f"Mode {kind}"))
    for (kind, text), y in zip(FX_BUTTONS, BUTTON_YS):
        hit, _, b = button(kind, text, 548, y)
        xml.append(b)
        listeners.append(click(hit, fire(kind), f"Effect {kind}"))
    bar = shape("Tray", rect(580, 104, r=26), fill("26FFFFFF") + stroke("40FFFFFF", 1.5), x=300, y=660)[1]
    for i, (kind, text) in enumerate(KK_BUTTONS):
        hit, _, b = button(kind, text, 75 + 90 * i, 646)
        xml.append(b)
        action = step_number("stars", PLUS1) + fire(kind) if kind == "fxStar" else fire(kind)
        listeners.append(click(hit, action, f"Effect {kind}"))
    for kind, text, x in (("glasses", "Окуляри", 40), ("hat", "Шапка", 104), ("outfit", "Одяг", 496), ("reset", "Скинути", 560)):
        hit, _, b = button(kind, text, x, 34, scale=0.76)
        xml.append(b)
        if kind == "reset":
            action = "".join(set_number(n, 0) for n in NUMBERS)
        else:
            action = step_number(kind, CYCLE4)
        listeners.append(click(hit, action, f"Wardrobe {kind}"))
    xml.append(star_balance())
    for kind, text, x in (("lessonStart", "Урок", 52), ("lessonStop", "Стоп", 548)):
        hit, _, b = button(kind, text, x, 550)
        xml.append(b)
        listeners.append(click(hit, fire(kind), f"Lesson {kind}"))
    xml.append(bar)
    return node("Buttons", xml)[1], "".join(listeners), rings


# ---------------------------------------------------------------- assemble
def main():
    global FONT_ID, PLUS1, CYCLE4, MOD5
    FONT_ID = nid()
    PLUS1 = formula("Plus one", ["in", ("op", 0), ("val", 1)])
    CYCLE4 = formula("Next of four", ["(", "in", ("op", 0), ("val", 1), ")", ("op", 4), ("val", 4)])
    MOD5 = formula("Every fifth", ["in", ("op", 4), ("val", 5)])
    for n in ("Torso", "Lean", "Follow", "ChestFront", "ChestBack"):
        ids[n] = nid()
    head = build_head()
    ids["Character"] = nid()
    body_xml = para("Body", body())
    W_ = WAIST_Y
    front = node("ChestFront", [node("FrontDown", [build_tea_arm(), para("Front", FRONT + [neck_clip_shape()])], y=-W_)[1]], nid_=ids["ChestFront"])[1]
    back = node("ChestBack", [node("BodyDown", [body_xml], y=-W_)[1]], nid_=ids["ChestBack"])[1]
    head_mount = node("HeadDown", [head], y=-W_)[1]
    torso = node("Torso", [node("Lean", [node("Follow", [front, head_mount, back], nid_=ids["Follow"])[1]], nid_=ids["Lean"])[1]],
                 y=W_, nid_=ids["Torso"])[1]
    character = node("Character", [torso], x=300, y=346, nid_=ids["Character"], extra=' scaleX="0.84" scaleY="0.84"')[1]
    badges = build_badges()
    runner = build_runner()

    idle_id, idle = idle_anim()
    blink_id, blink = blink_anim()
    mood_anims = [mood_anim(m) for m in MOODS]
    vis_anims = [viseme_anim(i) for i in range(len(VISEMES))]
    demo_id, demo = demo_anim()
    turn_x_id, turn_x = turn_anim("TurnX", "x", TURN_X)
    turn_y_id, turn_y = turn_anim("TurnY", "y", TURN_Y)
    agent = agent_anims()
    fx, timelines = build_fx()
    kk_art, kk_timelines = build_kk_fx()
    timelines.update(kk_timelines)
    sound_assets, sound_events = add_sounds(timelines)
    effects_layer, fx_off = fx_layer(timelines)
    gestures_layer, gesture_anims = talk_gesture_layer(interlude_anims())
    hurry_xml, hurry_anims = routine_mouth_layer()
    arrival_xml, arrival_anims = arrival_layer()
    run_id, run_xml = run_cycle_anim()
    gesture_anims += hurry_anims + arrival_anims + run_xml
    wardrobe_layers, wardrobe_anims = "", []
    for cat, n in WARDROBE.items():
        parts = [cat, "outfitfront"] if cat == "outfit" else [cat]
        anims_ = [anim(f"{cat.title()}_{i}", 1, [keys(ids[f"{c}{j}"], {"opacity": [(0, 1 if i == j else 0, None)]})
                                                 for c in parts for j in range(n)], loop=False)
                  for i in range(n)]
        wardrobe_anims += anims_
        wardrobe_layers += selector_layer(cat.title(), cat, [a for a, _ in anims_], 150, 0)

    # the pointer drags an invisible handle; the joystick turns its position
    # inside the artboard into -1..1 and scrubs TurnX/TurnY with it
    backdrop_id, handle_id = nid(), nid()
    backdrop_paint = radial(0, -40, 420, [(0, BG_TOP), (0.55, "FF6A50EC"), (1, BG_BOTTOM)])
    if BARE:
        backdrop_paint = fill("00000000")
    backdrop = shape("Backdrop", rect(600, ART_H), backdrop_paint, x=300, y=ART_H / 2, sid=backdrop_id)[1]
    handle = f'<Node x="300" y="320" name="LookHandle" id="{handle_id}"/>'
    joystick = (
        f'<Joystick posX="300" posY="320" width="600" height="640" xId="{turn_x_id}" yId="{turn_y_id}" '
        f'handleSourceId="{handle_id}" name="Look" id="{nid()}"/>'
    )
    follow = (
        f'<StateMachineListenerSingle targetId="{backdrop_id}" listenerTypeValue="move" name="Follow pointer" id="{nid()}">'
        f'<ListenerAlignTarget targetId="{handle_id}"/></StateMachineListenerSingle>'
    )

    sm_id = nid()
    demo_state = {
        "id": nid(),
        "anim": demo_id,
        "enter": cond_bool("demo", "true"),
        "leave": cond_bool("demo", "false"),
    }
    machine = (
        f'<StateMachine name="Teacher" id="{sm_id}">'
        + loop_layer("Idle", idle_id)
        + loop_layer("Blink", blink_id)
        + selector_layer("Mood", "mood", [a for a, _ in mood_anims], 250, 0)
        + agent_layer(agent)
        + gestures_layer
        + selector_layer("Mouth", "viseme", [a for a, _ in vis_anims], 30, 0, extra_state=demo_state)
        + hurry_xml
        + arrival_xml
        + loop_layer("Run cycle", run_id)
        + effects_layer
        + wardrobe_layers
        + "</StateMachine>"
    )

    style_id = nid()
    artboard = (
        f'<Artboard defaultStateMachineId="{sm_id}" viewModelId="{VM["vm"]}" viewModelInstanceId="{VM["inst"]}" '
        f'styleId="{style_id}" width="600" height="{ART_H}" name="Teacher" id="0:2">'
        f'<LayoutComponentStyle name="Artboard Style" id="{style_id}"/>'
        + handle
        + badges
        + kk_art
        + fx
        + runner
        + character
        + backdrop
        + sound_events + "".join(EXTRA_EVENTS)
        + machine
        + idle + blink + "".join(a for _, a in mood_anims) + "".join(a for _, a in agent.values())
        + "".join(a for _, a in vis_anims) + demo
        + turn_x + turn_y + fx_off + "".join(t[1] for t in timelines.values()) + "".join(a for _, a in wardrobe_anims) + gesture_anims
        + "</Artboard>"
    )
    font = f'<FontAsset file="fonts/inter-bold.ttf" name="Inter" id="{FONT_ID}"/>'
    font += sound_assets + "".join(EXTRA_ASSETS)
    if RENDER_HEAD:
        font += f'<ImageAsset file="{EYE_SCLERA_IMAGE}" name="eye_sclera" id="{EYE_ASSETS["sclera"]}"/>'
        font += f'<ImageAsset file="{HEAD_IMAGE}" name="teacher_head" id="{IMAGE_ASSET_ID}"/>'
    font += "".join(f'<ImageAsset file="{file}" name="{name}" id="{aid}"/>' for name, (aid, file) in RUN_IMAGES.items())
    doc = f'<Rive version="1" kind="fragment">{artboard}{view_model()}{font}{"".join(CONVERTERS)}</Rive>\n'
    OUT.write_text(doc)
    print(f"wrote {OUT} ({len(doc)} bytes)")


if __name__ == "__main__":
    main()
