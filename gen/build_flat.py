#!/usr/bin/env python3
"""The flat 2D teacher in Rive: a cut-out rig from generated art (gen/prep_flat.py).

Same contract as the vector teacher (artboard, state machine and view model "Teacher";
`agentState` string, `viseme` number 0-8), so web/index.html drives either file.
- one head and one body for every state; each drawing of an arm (keys, in-betweens) and the book is a layer
  of its own, pivoted at its bottom; scripts/life.luau shows one at a time (y 0, or 3000 to hide it), so an
  arm move is drawn frame by frame: book (disconnected), wave (connecting, initializing), hand to the ear
  (listening), gestures (speaking);
- mouth patches for visemes 1-8, blink, half lids (pause, reading) and gaze patches;
- breathing, a slow sway, and a talking bob.
Run: python3 gen/build_flat.py && (cd flat && rive . --verify)
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJ = ROOT / "flat"
L = json.loads((PROJ / "art" / "layout.json").read_text())
CW, CH = L["size"]
W, H = 600, 720
S = 700 / CH                       # figure height on the artboard
DROP = 60 * S                      # the figure sits this much below the bottom edge, so the frame cuts the torso
                                   # (the bust's own rounded lower edge, 30 px deep, stays out of view)
_n = [1000]


def nid():
    _n[0] += 1
    return f"0:{_n[0]}"


def f(v):
    return f"{v:.4f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v)


def node(name, kids, x=0, y=0, nid_=None, extra="", bind=None):
    """bind: {property key: view model number} — the life script drives these (13 x, 14 y, 15 rotation)"""
    nid_ = nid_ or nid()
    b = "".join(f'<DataBindContext sourcePathIds="{VM["vm"]}-{VM[p]}" propertyKey="{k}"/>' for k, p in (bind or {}).items())
    return nid_, f'<Node x="{f(x)}" y="{f(y)}"{extra} name="{name}" id="{nid_}">{b}{"".join(kids)}</Node>'


ASSETS = {}


def image(file, cx, cy, op=None, origin=(0, 0)):
    """An Image is placed by its centre; (cx, cy) are crop pixels, origin at the crop's bottom centre,
    shifted by `origin` (crop pixels) for images inside a node placed there."""
    ASSETS.setdefault(file, nid())
    o = f' opacity="{op}"' if op is not None else ""
    iid = nid()
    ox, oy = origin
    return iid, f'<Image x="{f(cx - CW / 2 - ox)}" y="{f(cy - CH - oy)}"{o} assetId="{ASSETS[file]}" name="{Path(file).stem}" id="{iid}"/>'


def patch(name, origin=(0, 0)):
    x, y, w, h = L["patches"][name]
    return image(f"art/{name}.png", x + w / 2, y + h / 2, op=0, origin=origin)


EASE = (0.42, 0, 0.58, 1)
OUT_ = (0.2, 0.8, 0.3, 1)


def kf(frames):
    out = []
    for fr in frames:
        e = fr[2] if len(fr) > 2 else EASE
        if e == "hold":
            out.append(f'<KeyFrameDouble frame="{fr[0]}" value="{f(fr[1])}" interpolationType="hold"/>')
        else:
            out.append(f'<KeyFrameDouble frame="{fr[0]}" value="{f(fr[1])}" interpolationType="cubic">'
                       f'<CubicEaseInterpolator x1="{e[0]}" y1="{e[1]}" x2="{e[2]}" y2="{e[3]}"/></KeyFrameDouble>')
    return "".join(out)


def keys(obj, props):
    return f'<KeyedObject objectId="{obj}">' + "".join(
        f'<KeyedProperty property="{p}">{kf(v)}</KeyedProperty>' for p, v in props.items()) + "</KeyedObject>"


ANIMS = []


def anim(name, length, k, loop=False):
    aid = nid()
    lv = ' loopValue="loop"' if loop else ""
    ANIMS.append(f'<LinearAnimation duration="{length}"{lv} name="{name}" id="{aid}">{"".join(k)}</LinearAnimation>')
    return aid


ARMS = list(L["arms"])
BODIES = L["bodies"]
NUMS = (("viseme", "gaze", "brow", "blink", "headRot", "headY", "bodyRot", "bunRot", "baseB")
        + tuple(f"{a}{c}" for a in ARMS for c in ("Y", "R")) + tuple(f"{b}B" for b in BODIES))
VM = {k: nid() for k in ("vm", "inst", "agentState") + NUMS}


def cond_state(v, op="equal"):
    return (f'<TransitionViewModelCondition opValue="{op}"><TransitionPropertyViewModelComparator><BindablePropertyString>'
            f'<DataBindContext sourcePathIds="{VM["vm"]}-{VM["agentState"]}" propertyKey="635"/></BindablePropertyString>'
            f'</TransitionPropertyViewModelComparator><TransitionValueStringComparator value="{v}"/></TransitionViewModelCondition>')


def cond_num(v, prop="viseme"):
    return (f'<TransitionViewModelCondition opValue="equal"><TransitionPropertyViewModelComparator><BindablePropertyNumber>'
            f'<DataBindContext sourcePathIds="{VM["vm"]}-{VM[prop]}" propertyKey="636"/></BindablePropertyNumber>'
            f'</TransitionPropertyViewModelComparator><TransitionValueNumberComparator value="{v}"/></TransitionViewModelCondition>')


LAYERS = []


def layer(name, states, entry, blend=0):
    """states: {key: (anim id, [(to, condition xml), ...])}; blend: transition length in ms"""
    sid = {k: nid() for k in states}
    dur = f' duration="{blend}"' if blend else ""
    body = "".join(
        f'<AnimationState x="{200 + 180 * i}" y="0" animationId="{a}" id="{sid[k]}">'
        + "".join(f'<StateTransition stateToId="{sid[to]}"{dur}>{c}</StateTransition>' for to, c in edges)
        + "</AnimationState>" for i, (k, (a, edges)) in enumerate(states.items()))
    LAYERS.append(f'<StateMachineLayer name="{name}" id="{nid()}"><AnyState x="0" y="-160"/><ExitState x="160" y="-160"/>'
                  f'<EntryState x="0" y="0"><StateTransition stateToId="{sid[entry]}"/></EntryState>{body}</StateMachineLayer>')


def loop_layer(name, aid):
    sid = nid()
    LAYERS.append(f'<StateMachineLayer name="{name}" id="{nid()}"><AnyState x="0" y="-160"/><ExitState x="160" y="-160"/>'
                  f'<EntryState x="0" y="0"><StateTransition stateToId="{sid}"/></EntryState>'
                  f'<AnimationState x="200" y="0" animationId="{aid}" id="{sid}"/></StateMachineLayer>')


SCRIPT = "0:999"
MOUTHS = ["mbp", "fv", "dt", "aa", "ee", "oh", "oo", "ch"]


def selector(name, prop, anims, blend=0):
    n = len(anims)
    layer(name, {v: (anims[v], [(o, cond_num(o, prop)) for o in range(n) if o != v]) for v in range(n)}, 0, blend)


GAZES = ["left", "right", "up"]


def main():
    PX, PY = L["pivot"]
    head_origin = (PX - CW / 2, PY - CH)            # the head node sits at the pivot, in crop-bottom-centre coords
    O = (head_origin[0], head_origin[1])
    ids = {k: nid() for k in ("breath", "sway", "talk", "head", "headbob")}
    # ---- base pose: head (turns about the neck) over gestures over body
    mouth_ids = {}
    head_kids = []
    brow_id, x = patch("brow_up", O); head_kids.append(x)
    blink_id, x = patch("eyes_closed", O); head_kids.append(x)
    half_id, x = patch("eyes_half", O); head_kids.append(x)
    gaze_ids = {}
    for i, g in enumerate(GAZES, start=1):
        gaze_ids[i], x = patch(f"gaze_{g}", O); head_kids.append(x)
    for i, m in enumerate(MOUTHS, start=1):
        mouth_ids[i], x = patch(f"mouth_{m}", O); head_kids.append(x)
    BX, BY = L["bun_pivot"]
    bun_origin = (BX - CW / 2, BY - CH)
    bun = node("BunPivot", [node("BunRig", [image("art/base_bun.png", CW / 2, CH / 2, origin=bun_origin)[1]], bind={15: "bunRot"})[1]],
               x=bun_origin[0] - O[0], y=bun_origin[1] - O[1])[1]
    head_kids.append(image("art/base_head.png", CW / 2, CH / 2, origin=O)[1])
    head_kids.insert(0, bun)
    head = node("Head", [node("HeadRig", [node("HeadBob", head_kids, nid_=ids["headbob"])[1]], bind={15: "headRot", 14: "headY"})[1]],
                x=O[0], y=O[1], nid_=ids["head"])[1]
    arms = []
    for a_ in ARMS:
        x, y, w, h, px = L["arms"][a_]
        o = (px - CW / 2, y + h - CH)
        rig = node(f"ArmRig {a_}", [image(f"art/arm_{a_}.png", x + w / 2, y + h / 2, origin=o)[1]], bind={14: f"{a_}Y", 15: f"{a_}R"})[1]
        arms.append(node(f"Arm {a_}", [rig], x=o[0], y=o[1])[1])
    # the base body, and the body of each arm drawing (shown with it, y 0 or 3000 like the arms)
    bodies = [node("Body base", [image("art/base_body.png", CW / 2, CH / 2)[1]], bind={14: "baseB"})[1]]
    bodies += [node(f"Body {b}", [image(f"art/body_{b}.png", CW / 2, CH / 2)[1]], bind={14: f"{b}B"})[1] for b in BODIES]
    life = f'<ScriptedDrawable scriptAssetId="{SCRIPT}" name="Life" id="{nid()}"/>'
    figure = node("Breath", [node("Sway", [node("Talk", [node("Scale", arms + [head] + bodies, extra=f' scaleX="{f(S)}" scaleY="{f(S)}"')[1]],
                                                  nid_=ids["talk"])[1]], nid_=ids["sway"], bind={15: "bodyRot"})[1]],
                  x=W / 2, y=H + DROP, nid_=ids["breath"])[1]
    figure = life + figure

    # ---- breathing; a slow sway with the shoulders a beat behind
    loop_layer("Breath", anim("Breath", 240, [keys(ids["breath"], {"scaleY": [(0, 1), (120, 1.009), (240, 1)],
                                                                   "scaleX": [(0, 1), (120, 0.997), (240, 1)]})], loop=True))

    # talking bob on the head; nods on the whole figure while listening
    bob = anim("Head_bob", 52, [keys(ids["headbob"], {"y": [(0, 0), (13, -2), (26, 0), (39, -1), (52, 0)]})], loop=True)
    still = anim("Head_still", 12, [keys(ids["headbob"], {"y": [(0, 0), (12, 0)], "rotation": [(0, 0), (12, 0)]})])
    layer("Talk", {"still": (still, [("bob", cond_state("speaking"))]), "bob": (bob, [("still", cond_state("speaking", "notEqual"))])}, "still")
    nod = anim("Nod", 150, [keys(ids["talk"], {"y": [(0, 0), (10, 9), (24, 0), (34, 7), (48, 0), (150, 0)],
                                               "rotation": [(0, 0), (10, 0.02), (24, 0), (34, 0.015), (48, 0), (150, 0)]})], loop=True)
    calm = anim("Nod_off", 12, [keys(ids["talk"], {"y": [(0, 0), (12, 0)], "rotation": [(0, 0), (12, 0)]})])
    layer("Nod", {"off": (calm, [("on", cond_state("listening"))]), "on": (nod, [("off", cond_state("listening", "notEqual"))])}, "off")

    # ---- face: mouth (viseme), glances, brows
    selector("Mouth", "viseme", [anim(f"Viseme_{v}", 1, [keys(m, {"opacity": [(0, 1 if i == v else 0, "hold")]}) for i, m in mouth_ids.items()])
                                 for v in range(9)])
    selector("Gaze", "gaze", [anim(f"Gaze_{v}", 1, [keys(g, {"opacity": [(0, 1 if i == v else 0, "hold")]}) for i, g in gaze_ids.items()])
                              for v in range(4)])
    selector("Brow", "brow", [anim(f"Brow_{v}", 6, [keys(brow_id, {"opacity": [(0, 1 - v), (6, v)]})]) for v in range(2)])

    # ---- blinks (single and double), half lids on pause
    selector("Blink", "blink", [anim(f"Blink_{v}", 1, [keys(blink_id, {"opacity": [(0, v, "hold")]})]) for v in range(2)])
    off = anim("Half_off", 1, [keys(half_id, {"opacity": [(0, 0, "hold")]})])     # a cut, like a blink: a fade
    on = anim("Half_on", 1, [keys(half_id, {"opacity": [(0, 1, "hold")]})])       # shows two pairs of eyes
    # half lids on pause, and looking down at the book while reading (disconnected)
    sid = {k: nid() for k in ("off", "on")}
    LAYERS.append(f'<StateMachineLayer name="Lids" id="{nid()}"><AnyState x="0" y="-160"/><ExitState x="160" y="-160"/>'
                  f'<EntryState x="0" y="0"><StateTransition stateToId="{sid["on"]}"/></EntryState>'
                  f'<AnimationState x="200" y="0" animationId="{off}" id="{sid["off"]}">'
                  f'<StateTransition stateToId="{sid["on"]}">{cond_state("pause")}</StateTransition>'
                  f'<StateTransition stateToId="{sid["on"]}">{cond_state("disconnected")}</StateTransition></AnimationState>'
                  f'<AnimationState x="380" y="0" animationId="{on}" id="{sid["on"]}">'
                  f'<StateTransition stateToId="{sid["off"]}">{cond_state("pause", "notEqual")}{cond_state("disconnected", "notEqual")}</StateTransition>'
                  f'</AnimationState></StateMachineLayer>')

    START = {**{f"{a_}Y": 3000 for a_ in ARMS}, **{f"{b}B": 3000 for b in BODIES}}   # arm drawings start out of frame
    sm, style = nid(), nid()
    artboard = (f'<Artboard defaultStateMachineId="{sm}" viewModelId="{VM["vm"]}" viewModelInstanceId="{VM["inst"]}" '
                f'width="{W}" height="{H}" styleId="{style}" name="Teacher" id="0:2">'
                f'<LayoutComponentStyle name="Artboard Style" id="{style}"/>{figure}'
                f'<StateMachine name="Teacher" id="{sm}">{"".join(LAYERS)}</StateMachine>{"".join(ANIMS)}</Artboard>')
    vm = (f'<ViewModel defaultInstanceId="{VM["inst"]}" name="Teacher" id="{VM["vm"]}">'
          f'<ViewModelPropertyString name="agentState" id="{VM["agentState"]}"/>'
          + "".join(f'<ViewModelPropertyNumber name="{n}" id="{VM[n]}"/>' for n in NUMS) +
          f'<ViewModelInstance exports="true" name="Default" id="{VM["inst"]}">'
          f'<ViewModelInstanceString propertyValue="disconnected" viewModelPropertyId="{VM["agentState"]}"/>'
          + "".join(f'<ViewModelInstanceNumber propertyValue="{f(START.get(n, 0))}" viewModelPropertyId="{VM[n]}"/>' for n in NUMS) +
          f'</ViewModelInstance></ViewModel>')
    assets = "".join(f'<ImageAsset file="{fl}" name="{Path(fl).stem}" id="{a}"/>' for fl, a in ASSETS.items())
    assets += f'<ScriptAsset file="scripts/life.luau" name="life" id="{SCRIPT}"/>'
    (PROJ / "scene.rml").write_text(f'<Rive version="1" kind="fragment">{artboard}{vm}{assets}</Rive>\n')
    print("wrote", PROJ / "scene.rml")


if __name__ == "__main__":
    main()
