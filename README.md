# AI tutor teacher (Rive)

**Demo: https://mabab.github.io/ai-teacher-rive/** — press «Почати урок». There is no LiveKit or agent server
on GitHub Pages, so the page emulates the agent: the states come in the order a real lesson goes through them
(connecting, initializing, speaking, listening, thinking), the teacher's lines are recorded with the agent's voice
(`gen/gen_demo_voice.py`, OpenAI `gpt-4o-mini-tts`), and the mouth is driven from that audio by the same analyser as
live audio. The state buttons show each state on its own. Run it locally with the agent (below) for a real lesson;
the page falls back to the emulation whenever `/token` is not there, or with `?demo`.

**Current teacher: the flat 2D one** (`flat/`, built by `gen/build_flat.py`, served as `web/teacher.riv`; the
vector one is kept as `web/teacher_vector.riv`). It is a cut-out rig made from generated art:
`gen/gen_2d_designs.py` (design options) → `gen/gen_flat_parts.py` (9 mouths, blink and half lids, gaze, brows,
arm poses; each an edit of the chosen design that changes only that part) → `gen/prep_flat.py` (white keyed out;
face patches; each arm pose cut out as the region where it differs from the design) → `gen/build_flat.py` (Rive).

Every state is the same figure: one head, one body. Arm moves are drawn, not slid: for each move there is a key
pose and one or two in-betweens (`i_*` edits: the arm partway up, the head untouched), each cut out as its own layer.
`flat/scripts/life.luau` shows one drawing at a time on twos (12 a second), slow out of the rest, settles on the key
with a small overshoot, plays the drawings back to lower the arm, and lowers the old arm before raising the new one:
book while disconnected (lifted into view), a wave while connecting (two drawings alternating), a hand at the ear
while listening, gestures while speaking. The head, eyes, blinks, shoulders and bun follow the Animator's Survival
Kit rules described at the top of the script. Same Rive contract as below.

A Rive avatar for the LiveKit AI tutor. The teacher is drawn in the browser and follows the agent's state. The agent only sends its voice and the `lk.agent.state` attribute, so there is no avatar video stream.

## What is here

| Path | What |
|---|---|
| `gen/build_teacher.py` | Generates `scene.rml`. It is the Charlie avatar rig (`~/avatar`) with a generated teacher head (`art/teacher_head.png`, no eyes, brows or mouth; the rig draws those). |
| `gen/gen_teacher_art.py` | Generates the head renders (OpenAI `gpt-image-1.5`) into `art/src/`. |
| `gen/gen_run_frames.py`, `gen/prep_run_frames.py` | The run sprite: 8 frames, each redrawn by the image model from a pose guide (`art/src/pose/pose_<i>.png`, the poses of the earlier jointed rig run: contact, down, passing, flight on each side) with her face and side-view body (`art/src/torso_2.png`) as references, then aligned on the head into `art/run/f_<i>.png`. One sheet of all 8 frames in a single request does not work: the model draws the same pose eight times. |
| `web/index.html` | Demo page: connects to LiveKit, drives the teacher, does lip sync from the agent's audio, shows captions. |
| `web/preview.html` | Teacher only, with `?state=` and `?viseme=`, for screenshots. |
| `agent/tutor.py` | A small LiveKit agent (OpenAI STT, LLM and TTS, plus Silero VAD) that goes through every agent state. |
| `agent/serve.py` | Serves `web/` and `POST /token` (a fresh room per lesson; the agent joins it on its own). |

## Run locally

```bash
livekit-server --dev --bind 127.0.0.1                 # keys devkey / secret
cd agent && .venv/bin/python tutor.py dev             # the agent; reads OPENAI_API_KEY from the backend .env
cd agent && .venv/bin/python serve.py                 # http://127.0.0.1:8773
python3 gen/build_teacher.py && rive . --once && cp build/teacher.riv web/   # after changing the rig
```

Set up the venv once: `python3.13 -m venv .venv && .venv/bin/pip install "livekit-agents[openai,silero]~=1.2" livekit-api`.

## The Rive contract

Artboard `Teacher`, state machine `Teacher`, view model `Teacher`:

| Property | Type | Meaning |
|---|---|---|
| `agentState` | string | `disconnected`, `connecting`, `initializing`, `idle`, `listening`, `thinking`, `speaking`, `pause`. Any other value keeps the current state. |
| `viseme` | number | Mouth shape while speaking: 0 rest, 1 m/b/p, 2 f/v, 3 d/t, 4 a, 5 e/i, 6 o, 7 u, 8 ch/sh. |
| `mood` | number | 0 neutral, 1 happy (default), 2 thinking, 3 surprised, 4 concerned, 5 relaxed. |
| `glasses`, `hat`, `outfit` | number | Wardrobe, 0–3. The teacher wears glasses 1 by default. |
| `fxStar`, `fxSuperStar`, `fxHeartEyes`, `fxConfetti`, `celebrate`, … | trigger | Classroom-style reactions, kept from Charlie. |

The state is resolved the way a LiveKit voice-assistant client resolves it:

1. A disconnected room gives `disconnected`.
2. While connecting, with no agent yet, or before the agent's `lk.agent.state` attribute arrives, the state is `connecting`.
3. When the learner has paused, the state is `pause`.
4. Otherwise the state is the attribute itself.

`livekit-agents` 1.8 also publishes `idle`, which the classroom's `AgentState` type does not list yet.

## Disconnected, connecting, arrival

- **`disconnected` is her routine.** It is an 8-second loop with tea and notes. She holds a mug and looks at it, blows on it, lifts it (eyes first), takes a long sip with her eyes closed and her head tipped back, lowers it with a contented "ahh", then reads her notes line by line. A separate mouth layer runs the blow, sip and "ahh" shapes.
- **`connecting` is a surprised double take toward the door.** The `Arrival` layer then dashes her out of frame (a step back as anticipation, then off fast), and the runner runs in.
- **The runner (old notes, superseded by the sprite).** The generated torso (head to hips, side view) has drawn limbs on joints: thigh, shin and sneaker, plus upper arm, forearm and fist. A classic 8-pose run cycle (contact, down, passing, push-off, lift, swing-up, swing, reach) loops every 0.67 s. The far leg is half a cycle behind, and each arm swings against the leg on its side with the elbows bent. The hips are lowest after contact and highest in flight, the shadow breathes with the bounce, and dust puffs off each footfall while speed lines stream past.
- **Arrival.** It starts in any state other than `connecting` or `disconnected`. The runner runs out ahead and the teacher comes in after her, brakes by leaning back, squashes and settles. A connection lost mid-run blends straight back to the routine.

The background is the page's, as in every other state. The teacher no longer follows the pointer.

## Motion

The rig is a chain, so a part that follows always lags behind and moves less than the part that leads it:

- **Torso.** It is pivoted at the waist and holds three nodes: `Torso` (the idle sway follow), `Lean` (posture for each agent state) and `Follow` (talk-gesture follow).
- **Chest.** `ChestFront` and `ChestBack` breathe about the waist. The collar and the neck clip are inside them.
- **Head.** It sits on the torso and turns about the base of the neck. The nodes go `TurnPivot` (pointer), then `ActHead` (agent state), `Gesture` (talk) and `Sway` (idle).

How each motion works:

- **Breathing** (secondary action) scales the chest by 1.2 % over 4 s. The head rides up by the amount the neck base rises, so it stays attached.
- **Following** (overlapping action) works the same everywhere. Where the eyes move, they lead the head by 6 frames. The torso takes the head's motion 6–18 frames later at about 0.3 of the amplitude: idle sway, nods while listening, glances while connecting, talk bob and interludes.
- **The neck stays seated.** All head rotations pivot at the neck base, and the render's neck is clipped along the collar line by a shape that moves with the chest. A tilt or a nod therefore never slides the neck out over the sweater, and a vector neck behind it fills the gap when the head lifts.
- **Every state keys all of `Lean`'s channels.** A state change (blended over 300 ms, ease in-out) always lands on a defined pose.

Lip sync runs in the page. An `AnalyserNode` on the agent's audio track turns loudness into how open the mouth is, and turns where the energy sits in the spectrum into the mouth shape. Each shape is held for at least 70 ms.
