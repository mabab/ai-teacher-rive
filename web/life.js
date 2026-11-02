// The teacher's "life", built on the principles of Richard Williams' Animator's Survival Kit.
// It runs in the page and drives the rig through its view model (teacher.riv has no scripts of its own, so the
// file needs no signing). It reads `agentState` and `viseme` and writes the numbers the rig is bound to:
//   headRot, headY  the head about the neck      bodyRot  the shoulders (follow the head)
//   bunRot          the bun (drags behind)        gaze 0-3, blink 0/1, brow 0/1
//   <drawing>Y, <drawing>B, baseB                which arm drawing and body show (0) or hide (3000)
// * every move is a spring: it eases out, overshoots a little and settles (no linear motion);
// * anticipation: a small move the other way before a head move;
// * the eyes lead: a glance toward the new side, the head follows a few frames later;
// * overlapping action: the shoulders follow the head later and less; the bun drags and wobbles;
// * blinks land on head moves (and otherwise at irregular intervals);
// * accents: an open vowel after a pause nods the head on the stressed syllable;
// * moving holds: a held pose keeps drifting, never dead still; no mirrored, twinned poses;
// * one figure for every state; arms are drawn, not slid: each move is a key pose reached through
//   in-between drawings, shown one at a time on twos (12 a second), slow out of the rest, and settling on
//   the key; going down plays the drawings back, faster; the old arm is down before the new one starts;
//   the wave alternates two drawings; the book is lifted.
// Usage: const life = TeacherLife(viewModelInstance); then life.advance(seconds) every frame.
(function () {
  const MOVES = {
    listen: ["listen1", "listen2", "listen"], wave: ["wave1", "wave"], read: ["read", "read", "read"],
    palm: ["palm1", "palm"], thumb: ["thumb1", "thumb"], count: ["count1", "count"], both: ["both1", "both"],
  };
  const LAYERS = ["listen1", "listen2", "listen", "wave1", "wave", "wave2", "read", "palm1", "palm", "thumb1", "thumb",
    "count1", "count", "both1", "both"];
  const BODIES = LAYERS.filter((a) => a !== "read");        // arm drawings that come with a body of their own
  const UP_ONLY = { listen1: true };                         // reads as a wave on the way down: skipped
  const READ_Y = [0, 170, 60, 0];                            // the book is lifted into view (by drawing index)
  const SIDE = { listen: -1, wave: -1, palm: -1, thumb: 1 }; // which way the shoulders lean
  const HIDDEN = 3000;
  const GESTURES = ["palm", "palm", "thumb", "count", "both"];

  const spring = (k, zeta) => ({ x: 0, v: 0, target: 0, k, zeta });
  function step(s, dt) {
    const a = s.k * (s.target - s.x) - 2 * s.zeta * Math.sqrt(s.k) * s.v;
    s.v += a * dt;
    s.x += s.v * dt;
  }

  window.TeacherLife = function (vm) {
    const num = (name) => { try { return vm.number(name); } catch (e) { return null; } };
    const p = {
      state: vm.string("agentState"), viseme: num("viseme"),
      headRot: num("headRot"), headY: num("headY"), bodyRot: num("bodyRot"), bunRot: num("bunRot"),
      gaze: num("gaze"), blink: num("blink"), brow: num("brow"), baseB: num("baseB"),
      ly: Object.fromEntries(LAYERS.map((a) => [a, num(a + "Y")])),
      lb: Object.fromEntries(BODIES.map((b) => [b, num(b + "B")])),
    };
    const set = (prop, v) => { if (prop && prop.value !== v) prop.value = v; };
    const s = {
      want: "", cur: "", idx: 0, nextStep: 0, stateWas: "", stateSince: 0,
      head: spring(90, 0.55), lift: spring(120, 0.5), body: spring(30, 0.7), bun: spring(70, 0.3),
      t: 0, seed: 20261102, pending: 0, pendingRot: 0, pendingLift: 0,
      nextHead: 0.8, nextGaze: 2, gazeUntil: 0, nextBlink: 1.5, blinkUntil: 0,
      nextGesture: 0.8, browUntil: 0, nextBrow: 2, silentSince: 0, lastVis: 0,
    };
    function rand() {
      s.seed = (s.seed * 1103515245 + 12345) % 2147483648;
      return s.seed / 2147483648;
    }
    const range = (a, b) => a + (b - a) * rand();
    function blink() {
      s.blinkUntil = s.t + 0.1;
      s.nextBlink = s.t + range(2.0, 5.5);
    }

    // a new head pose: anticipation now, the real move a beat later, the eyes going first
    function newHead(rot, lift, speaking) {
      const delta = rot - s.head.target;
      s.head.target -= delta * 0.18;
      s.pendingRot = rot; s.pendingLift = lift;
      s.pending = s.t + 0.09;
      if (Math.abs(delta) > 0.02 && rand() < 0.6) {
        set(p.gaze, delta > 0 ? 2 : 1);
        s.gazeUntil = s.t + range(0.3, 0.6);
      }
      if (Math.abs(delta) > 0.035 && rand() < 0.55) blink();
      if (speaking && rand() < 0.35) s.browUntil = s.t + range(0.3, 0.55);
    }

    // which arm this state wants: the book, a wave now and then, the hand at the ear, gestures while talking
    function wantedArm(st, t) {
      if (st !== s.stateWas) {
        s.stateWas = st; s.stateSince = t;
        s.nextGesture = t + range(0.4, 0.9);
      }
      const since = t - s.stateSince;
      if (st === "disconnected") return "read";
      if (st === "connecting" || st === "initializing") return since % 7 < 2.8 ? "wave" : "";   // a wave, a rest, a wave again
      if (st === "listening") return since > 0.3 ? "listen" : "";                             // the head turns to listen first
      if (st !== "speaking") return "";
      if (t < s.nextGesture) return s.want;
      if (s.want !== "") {
        s.nextGesture = t + range(0.9, 2.2);
        return "";
      }
      s.nextGesture = t + range(1.4, 2.8);
      return GESTURES[Math.floor(range(0, GESTURES.length))];
    }

    // one step of the drawings: down through the old move first, then up through the new one
    function stepArm(want, t) {
      const frames = MOVES[s.cur] || [];
      if (s.cur !== want && s.idx > 0) {
        s.idx -= 1;
        if (s.idx > 0 && UP_ONLY[frames[s.idx - 1]]) s.idx -= 1;
        s.nextStep = t + 0.07;                               // going down is quicker
      } else if (s.cur !== want) {
        s.cur = want;
        s.nextStep = t + 0.04;
        if (want !== "") {
          s.lift.v += 45;                                    // the head dips into the move
          s.body.v += 0.06 * (SIDE[want] || 0);
        }
      } else if (s.idx < frames.length) {
        s.idx += 1;
        if (s.idx === frames.length) {
          s.lift.v += 25;                                    // the body settles into the key pose
          s.nextStep = t + 0.1;
        } else {
          s.nextStep = t + (s.idx === 1 ? 0.1 : 0.075);      // slow out of the rest
        }
      } else {
        s.nextStep = t + 0.05;
      }
    }

    // show the current drawing, hide the rest; arms never turn on their own: they are drawn onto the body
    function showArm(t) {
      const frames = MOVES[s.cur] || [];
      let shown = s.idx > 0 ? frames[s.idx - 1] : "";
      if (shown === "wave" && Math.floor(t / 0.16) % 2 === 1) shown = "wave2";
      const y = shown === "read" ? READ_Y[s.idx] || 0 : 0;
      for (const b of BODIES) set(p.lb[b], b === shown ? 0 : HIDDEN);
      set(p.baseB, BODIES.includes(shown) ? HIDDEN : 0);
      for (const a of LAYERS) set(p.ly[a], a === shown ? y : HIDDEN);
    }

    function advance(seconds) {
      const dt = Math.min(seconds, 1 / 30);
      s.t += seconds;
      const t = s.t;
      const st = p.state ? p.state.value : "idle";
      const speaking = st === "speaking";
      const calm = st === "pause" || st === "disconnected";

      // head: asymmetric poses, more often while she talks; a slow drift in between (moving hold)
      if (t >= s.nextHead) {
        if (st === "disconnected") {
          newHead(range(-0.015, 0.02), range(9, 13), false);          // down at the book
          s.nextHead = t + range(3, 6);
        } else if (st === "listening") {
          newHead(range(0.008, 0.02), range(-2, 2), false);           // a little toward the hand at her ear
          s.nextHead = t + range(2.5, 4.5);
        } else if (calm) {
          newHead(0.01, 2, false);
          s.nextHead = t + range(3, 6);
        } else {
          const side = rand() < 0.5 ? -1 : 1;
          const rot = side * range(speaking ? 0.015 : 0.02, speaking ? 0.06 : 0.05);
          newHead(rot, range(-4, 3), speaking);
          s.nextHead = t + (speaking ? range(0.8, 1.9) : range(2.4, 5.0));
        }
      }
      if (s.pending > 0 && t >= s.pending) {
        s.head.target = s.pendingRot;
        s.lift.target = s.pendingLift;
        s.pending = 0;
      }
      const drift = 0.006 * Math.sin(t * 0.7) + 0.004 * Math.sin(t * 1.9 + 1.3);

      // accents: an open vowel after a short silence nods the head down on the stress
      const vis = p.viseme ? p.viseme.value : 0;
      if (vis === 0 || vis === 1) {
        if (s.lastVis !== 0 && s.lastVis !== 1) s.silentSince = t;
      } else if ((vis === 4 || vis === 5 || vis === 6) && (s.lastVis === 0 || s.lastVis === 1) && t - s.silentSince > 0.22) {
        s.lift.v += 70;
        s.head.v += (rand() < 0.5 ? -1 : 1) * 0.25;
        if (rand() < 0.3) s.browUntil = t + 0.35;
      }
      s.lastVis = vis;

      // overlapping action: shoulders follow later and less, the bun drags behind the head's speed
      s.body.target = s.head.x * 0.35;
      s.bun.target = -s.head.v * 0.09;
      const headTarget = s.head.target;
      s.head.target = headTarget + drift;
      step(s.head, dt); step(s.lift, dt); step(s.body, dt); step(s.bun, dt);
      s.head.target = headTarget;
      set(p.headRot, s.head.x);
      set(p.headY, s.lift.x);
      set(p.bodyRot, s.body.x);
      set(p.bunRot, s.bun.x);

      // eyes: on the book while reading; back to the child after a glance; occasional glances of their own
      if (st === "disconnected") {
        set(p.gaze, 0);                                    // reading: the half lids look down at the book
        s.gazeUntil = 0;
      } else if (s.gazeUntil > 0 && t >= s.gazeUntil) {
        set(p.gaze, 0); s.gazeUntil = 0;
        s.nextGaze = t + range(1.5, 4);
      } else if (s.gazeUntil === 0 && t >= s.nextGaze && !calm) {
        set(p.gaze, Math.floor(range(1, 4)));
        s.gazeUntil = t + range(0.35, 0.8);
      }

      // blinks at irregular intervals, sometimes double
      if (t >= s.nextBlink) {
        blink();
        if (rand() < 0.2) s.nextBlink = t + 0.25;
      }
      set(p.blink, t < s.blinkUntil ? 1 : 0);

      // brows on emphasis
      if (t >= s.nextBrow && !calm) {
        if (rand() < (speaking ? 0.5 : 0.15)) s.browUntil = t + range(0.3, 0.6);
        s.nextBrow = t + range(1.5, 4);
      }
      set(p.brow, t < s.browUntil ? 1 : 0);

      s.want = wantedArm(st, t);
      if (t >= s.nextStep) stepArm(s.want, t);
      showArm(t);
    }

    // drives itself on animation frames; stop() to end
    let raf = 0, last = 0;
    const frame = (now) => {
      raf = requestAnimationFrame(frame);
      if (last) advance(Math.min((now - last) / 1000, 0.25));
      last = now;
    };
    raf = requestAnimationFrame(frame);
    return { advance, stop: () => cancelAnimationFrame(raf) };
  };
})();
