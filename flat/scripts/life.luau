-- The teacher's "life", built on the principles of Richard Williams' Animator's Survival Kit.
-- It reads `agentState` and `viseme` and writes the view model numbers the rig is bound to:
--   headRot, headY  the head about the neck      bodyRot  the shoulders (follow the head)
--   bunRot          the bun (drags behind)        gaze 0-3, blink 0/1, brow 0/1
-- * every move is a spring: it eases out, overshoots a little and settles (no linear motion);
-- * anticipation: a small move the other way before a head move;
-- * the eyes lead: a glance toward the new side, the head follows a few frames later;
-- * overlapping action: the shoulders follow the head later and less; the bun drags and wobbles;
-- * blinks land on head moves (and otherwise at irregular intervals);
-- * accents: an open vowel after a pause nods the head on the stressed syllable;
-- * moving holds: a held pose keeps drifting, never dead still; no mirrored, twinned poses;
-- * one figure for every state; arms are drawn, not slid: each move is a key pose reached through
--   in-between drawings, shown one at a time on twos (12 a second), slow out of the rest, and settling on
--   the key with a small overshoot (follow-through); going down plays the drawings back, faster; the old
--   arm is down before the new one starts; the wave alternates two drawings; the book is lifted.

local MOVES: { [string]: { string } } = {
    listen = { "listen1", "listen2", "listen" }, wave = { "wave1", "wave" }, read = { "read", "read", "read" },
    palm = { "palm1", "palm" }, thumb = { "thumb1", "thumb" }, count = { "count1", "count" }, both = { "both1", "both" },
}
local LAYERS = { "listen1", "listen2", "listen", "wave1", "wave", "wave2", "read", "palm1", "palm", "thumb1", "thumb",
    "count1", "count", "both1", "both" }
local BODIES = { "listen1", "listen2", "listen", "wave1", "wave", "wave2", "palm1", "palm", "thumb1", "thumb",
    "count1", "count", "both1", "both" }                       -- arm drawings that come with a body of their own
local UP_ONLY: { [string]: boolean } = { listen1 = true }      -- reads as a wave on the way down: skipped
local READ_Y = { 170, 60, 0 }                                   -- the book is lifted into view
local SIDE: { [string]: number } = { listen = -1, wave = -1, palm = -1, thumb = 1 }   -- which way the shoulders lean
local HIDDEN = 3000
local GESTURES = { "palm", "palm", "thumb", "count", "both" }

type Spring = { x: number, v: number, target: number, k: number, zeta: number }
type Life = {
    state: Property<string>?, viseme: Property<number>?,
    headRot: Property<number>?, headY: Property<number>?, bodyRot: Property<number>?, bunRot: Property<number>?,
    gaze: Property<number>?, blink: Property<number>?, brow: Property<number>?,
    ly: { [string]: Property<number>? }, lr: { [string]: Property<number>? }, lb: { [string]: Property<number>? },
    baseB: Property<number>?,
    want: string, cur: string, idx: number, nextStep: number, stateWas: string, stateSince: number,
    head: Spring, lift: Spring, body: Spring, bun: Spring,
    t: number, seed: number,
    pending: number, pendingRot: number, pendingLift: number,
    nextHead: number, nextGaze: number, gazeUntil: number, nextBlink: number, blinkUntil: number,
    nextGesture: number, browUntil: number, nextBrow: number, silentSince: number, lastVis: number,
}

local function spring(k: number, zeta: number): Spring
    return { x = 0, v = 0, target = 0, k = k, zeta = zeta }
end

local function step(s: Spring, dt: number)
    local c = 2 * s.zeta * math.sqrt(s.k)
    local a = s.k * (s.target - s.x) - c * s.v
    s.v += a * dt
    s.x += s.v * dt
end

local function rand(self: Life): number
    self.seed = (self.seed * 1103515245 + 12345) % 2147483648
    return self.seed / 2147483648
end

local function range(self: Life, a: number, b: number): number
    return a + (b - a) * rand(self)
end

local function set(p: Property<number>?, v: number)
    if p ~= nil and p.value ~= v then
        p.value = v
    end
end

local function blink(self: Life)
    self.blinkUntil = self.t + 0.1
    self.nextBlink = self.t + range(self, 2.0, 5.5)
end

function init(self: Life, context: Context): boolean
    local vm = context:viewModel()
    if vm ~= nil then
        self.state = vm:getString("agentState")
        self.viseme = vm:getNumber("viseme")
        self.headRot = vm:getNumber("headRot")
        self.headY = vm:getNumber("headY")
        self.bodyRot = vm:getNumber("bodyRot")
        self.bunRot = vm:getNumber("bunRot")
        self.gaze = vm:getNumber("gaze")
        self.blink = vm:getNumber("blink")
        self.brow = vm:getNumber("brow")
        for _, a in LAYERS do
            self.ly[a] = vm:getNumber(a .. "Y")
            self.lr[a] = vm:getNumber(a .. "R")
        end
        for _, b in BODIES do
            self.lb[b] = vm:getNumber(b .. "B")
        end
        self.baseB = vm:getNumber("baseB")
    end
    return true
end

-- a new head pose: anticipation now, the real move a beat later, the eyes going first
local function newHead(self: Life, rot: number, lift: number, speaking: boolean)
    local delta = rot - self.head.target
    self.head.target -= delta * 0.18
    self.pendingRot, self.pendingLift = rot, lift
    self.pending = self.t + 0.09
    if math.abs(delta) > 0.02 and rand(self) < 0.6 then
        set(self.gaze, if delta > 0 then 2 else 1)
        self.gazeUntil = self.t + range(self, 0.3, 0.6)
    end
    if math.abs(delta) > 0.035 and rand(self) < 0.55 then
        blink(self)
    end
    if speaking and rand(self) < 0.35 then
        self.browUntil = self.t + range(self, 0.3, 0.55)
    end
end

-- which arm this state wants: the book, a wave now and then, the hand at the ear, gestures while talking
local function wantedArm(self: Life, st: string, t: number): string
    if st ~= self.stateWas then
        self.stateWas, self.stateSince = st, t
        self.nextGesture = t + range(self, 0.4, 0.9)
    end
    local since = t - self.stateSince
    local want = ""
    if st == "disconnected" then
        want = "read"
    elseif st == "connecting" or st == "initializing" then
        want = if since % 7 < 2.8 then "wave" else ""          -- a wave, a rest, a wave again
    elseif st == "listening" then
        want = if since > 0.3 then "listen" else ""            -- the head turns to listen first
    elseif st == "speaking" then
        if t >= self.nextGesture then
            if self.want ~= "" then
                want = ""
                self.nextGesture = t + range(self, 0.9, 2.2)
            else
                want = GESTURES[math.floor(range(self, 1, #GESTURES + 1))]
                self.nextGesture = t + range(self, 1.4, 2.8)
            end
        else
            want = self.want
        end
    end
    return want
end

-- one step of the drawings: down through the old move first, then up through the new one
local function stepArm(self: Life, want: string, t: number)
    local frames: { string } = MOVES[self.cur] or {}
    if self.cur ~= want and self.idx > 0 then
        self.idx -= 1
        if self.idx > 0 and UP_ONLY[frames[self.idx]] then self.idx -= 1 end
        self.nextStep = t + 0.07                                -- going down is quicker
    elseif self.cur ~= want then
        self.cur = want
        self.nextStep = t + 0.04
        if want ~= "" then
            self.lift.v += 45                                   -- the head dips into the move
            self.body.v += 0.06 * (SIDE[want] or 0)
        end
    elseif self.idx < #frames then
        self.idx += 1
        if self.idx == #frames then
            self.lift.v += 25                                   -- the body settles into the key pose
            self.nextStep = t + 0.1
        else
            self.nextStep = t + (if self.idx == 1 then 0.1 else 0.075)   -- slow out of the rest
        end
    else
        self.nextStep = t + 0.05
    end
end

-- show the current drawing, hide the rest
local function showArm(self: Life, t: number, dt: number)
    local frames: { string } = MOVES[self.cur] or {}
    local shown: string = if self.idx > 0 then frames[self.idx] else ""
    if shown == "wave" and math.floor(t / 0.16) % 2 == 1 then
        shown = "wave2"
    end
    local y: number = if shown == "read" then READ_Y[self.idx] or 0 else 0
    local ownBody = false
    for _, b in BODIES do
        if b == shown then ownBody = true end
        set(self.lb[b], if b == shown then 0 else HIDDEN)
    end
    set(self.baseB, if ownBody then HIDDEN else 0)
    for _, a in LAYERS do
        set(self.ly[a], if a == shown then y else HIDDEN)   -- arms never turn on their own: they are drawn onto the body
    end
end

-- the old arm clears before the new one comes up
local function moveArms(self: Life, want: string, t: number, dt: number)
    self.want = want
    if t >= self.nextStep then
        stepArm(self, want, t)
    end
    showArm(self, t, dt)
end

function advance(self: Life, seconds: number): boolean
    local dt = math.min(seconds, 1 / 30)
    self.t += seconds
    local t = self.t
    local st = if self.state ~= nil then self.state.value else "idle"
    local speaking = st == "speaking"
    local calm = st == "pause" or st == "disconnected"

    -- head: asymmetric poses, more often while she talks; a slow drift in between (moving hold)
    if t >= self.nextHead then
        if st == "disconnected" then
            newHead(self, range(self, -0.015, 0.02), range(self, 9, 13), false)    -- down at the book
            self.nextHead = t + range(self, 3, 6)
        elseif st == "listening" then
            newHead(self, range(self, 0.008, 0.02), range(self, -2, 2), false)   -- a little toward the hand at her ear
            self.nextHead = t + range(self, 2.5, 4.5)
        elseif calm then
            newHead(self, 0.01, 2, false)
            self.nextHead = t + range(self, 3, 6)
        else
            local side = if rand(self) < 0.5 then -1 else 1
            local rot = side * range(self, if speaking then 0.015 else 0.02, if speaking then 0.06 else 0.05)
            newHead(self, rot, range(self, -4, 3), speaking)
            self.nextHead = t + (if speaking then range(self, 0.8, 1.9) else range(self, 2.4, 5.0))
        end
    end
    if self.pending > 0 and t >= self.pending then
        self.head.target = self.pendingRot
        self.lift.target = self.pendingLift
        self.pending = 0
    end
    local drift = 0.006 * math.sin(t * 0.7) + 0.004 * math.sin(t * 1.9 + 1.3)

    -- accents: an open vowel after a short silence nods the head down on the stress
    local vis = if self.viseme ~= nil then self.viseme.value else 0
    if vis == 0 or vis == 1 then
        if self.lastVis ~= 0 and self.lastVis ~= 1 then self.silentSince = t end
    elseif (vis == 4 or vis == 5 or vis == 6) and (self.lastVis == 0 or self.lastVis == 1) and t - self.silentSince > 0.22 then
        self.lift.v += 70
        self.head.v += (if rand(self) < 0.5 then -1 else 1) * 0.25
        if rand(self) < 0.3 then self.browUntil = t + 0.35 end
    end
    self.lastVis = vis

    -- overlapping action: shoulders follow later and less, the bun drags behind the head's speed
    self.body.target = self.head.x * 0.35
    self.bun.target = -self.head.v * 0.09
    local headTarget = self.head.target
    self.head.target = headTarget + drift
    step(self.head, dt); step(self.lift, dt); step(self.body, dt); step(self.bun, dt)
    self.head.target = headTarget
    set(self.headRot, self.head.x)
    set(self.headY, self.lift.x)
    set(self.bodyRot, self.body.x)
    set(self.bunRot, self.bun.x)

    -- eyes: on the book while reading; back to the child after a glance; occasional glances of their own
    if st == "disconnected" then
        set(self.gaze, 0)                                       -- reading: the half lids look down at the book
        self.gazeUntil = 0
    elseif self.gazeUntil > 0 and t >= self.gazeUntil then
        set(self.gaze, 0); self.gazeUntil = 0
        self.nextGaze = t + range(self, 1.5, 4)
    elseif self.gazeUntil == 0 and t >= self.nextGaze and not calm then
        set(self.gaze, math.floor(range(self, 1, 4)))
        self.gazeUntil = t + range(self, 0.35, 0.8)
    end

    -- blinks at irregular intervals, sometimes double
    if t >= self.nextBlink then
        blink(self)
        if rand(self) < 0.2 then self.nextBlink = t + 0.25 end
    end
    set(self.blink, if t < self.blinkUntil then 1 else 0)

    -- brows on emphasis
    if t >= self.nextBrow and not calm then
        if rand(self) < (if speaking then 0.5 else 0.15) then self.browUntil = t + range(self, 0.3, 0.6) end
        self.nextBrow = t + range(self, 1.5, 4)
    end
    set(self.brow, if t < self.browUntil then 1 else 0)

    moveArms(self, wantedArm(self, st, t), t, dt)
    return true
end

return function(): Node<Life>
    return {
        state = nil, viseme = nil, headRot = nil, headY = nil, bodyRot = nil, bunRot = nil,
        gaze = nil, blink = nil, brow = nil,
        ly = {}, lr = {}, lb = {}, baseB = nil, want = "", cur = "", idx = 0, nextStep = 0, stateWas = "", stateSince = 0,
        head = spring(90, 0.55), lift = spring(120, 0.5), body = spring(30, 0.7), bun = spring(70, 0.3),
        t = 0, seed = 20261102, pending = 0, pendingRot = 0, pendingLift = 0,
        nextHead = 0.8, nextGaze = 2, gazeUntil = 0, nextBlink = 1.5, blinkUntil = 0,
        nextGesture = 0.8, browUntil = 0, nextBrow = 2, silentSince = 0, lastVis = 0,
        init = init, advance = advance,
    }
end
