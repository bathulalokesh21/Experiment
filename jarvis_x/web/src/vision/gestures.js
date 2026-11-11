// Gesture recognition as pure functions fed by landmark frames (21 points per hand, x/y in 0..1,
// y pointing down). No camera or DOM in here: tests drive it with synthetic hands.

const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
export const POSE_ICON = { open: '🖐️', fist: '✊', point: '☝️', two: '✌️', three: '🤟', thumbs_up: '👍', thumbs_down: '👎', pinch: '🤏', rock: '🤘', ok: '👌', none: '·' };
export const POSE_LABEL = { open: 'open palm', fist: 'fist', point: 'point', two: 'two fingers', three: 'three fingers', thumbs_up: 'thumbs up',
  thumbs_down: 'thumbs down', pinch: 'pinch', rock: 'rock sign', ok: 'OK sign', none: '' };

export function handSize(lm) { return dist(lm[0], lm[9]) || 1e-6; }   // wrist -> middle knuckle

/** Classify one hand. Returns {pose, extended:[thumb,index,middle,ring,pinky], size, centre, pinchGap}. */
export function classify(lm) {
  const size = handSize(lm);
  const wrist = lm[0];
  const ext = (tip, pip) => dist(lm[tip], wrist) > dist(lm[pip], wrist) * 1.12;
  const index = ext(8, 6), middle = ext(12, 10), ring = ext(16, 14), pinky = ext(20, 18);
  const thumb = dist(lm[4], lm[17]) > dist(lm[2], lm[17]) * 1.15 && dist(lm[4], lm[5]) > size * 0.45;
  const pinchGap = dist(lm[4], lm[8]) / size;
  // a real pinch reaches forward; in a fist the index tip folds back behind its knuckle
  const reaching = dist(lm[8], wrist) > dist(lm[5], wrist) * 1.05;
  const touching = pinchGap < 0.3 && reaching;
  const centre = { x: (lm[0].x + lm[5].x + lm[17].x) / 3, y: (lm[0].y + lm[5].y + lm[17].y) / 3 };
  const up = (lm[2].y - lm[4].y) / size;      // > 0 when the thumb tip is above its base
  let pose = 'none';
  const fingers = [index, middle, ring, pinky].filter(Boolean).length;
  if (touching && middle && ring && pinky) pose = 'ok';
  else if (touching && fingers <= 2 && !(index && middle && !ring)) pose = 'pinch';
  else if (fingers === 0 && thumb && up > 0.55) pose = 'thumbs_up';
  else if (fingers === 0 && thumb && up < -0.55) pose = 'thumbs_down';
  else if (fingers === 0) pose = 'fist';
  else if (index && pinky && !middle && !ring) pose = 'rock';
  else if (index && middle && ring && pinky) pose = thumb ? 'open' : 'open';
  else if (index && middle && ring && !pinky) pose = 'three';
  else if (index && middle && !ring && !pinky) pose = 'two';
  else if (index && !middle && !ring && !pinky) pose = 'point';
  return { pose, extended: [thumb, index, middle, ring, pinky], size, centre, pinchGap, tip: lm[8] };
}

const HOLD = { open: ['stop', 0.7], fist: ['mute', 0.8], point: ['listen', 0.8], thumbs_up: ['approve', 0.55], thumbs_down: ['cancel', 0.55],
  rock: ['party', 0.7], ok: ['confirm', 0.6] };
const COOLDOWN = { stop: 1.5, mute: 2.0, listen: 2.5, approve: 2.5, cancel: 2.5, party: 4, confirm: 2, switch_next: 1.2, switch_prev: 1.2,
  volume_up: 0.45, volume_down: 0.45, wave: 4, click: 0.5 };

/** Stateful recogniser. update({t, hands:[landmarks,...]}) -> list of events.
 *  Hysteresis: a pose must be seen for STABLE frames before it counts, and survives brief dropouts. */
export class GestureEngine {
  constructor({ sensitivity = 1, refSize = 0.2, airMouse = false } = {}) {
    this.sensitivity = sensitivity; this.refSize = refSize; this.airMouse = airMouse;
    this.reset();
  }
  reset() {
    this.pose = 'none'; this.candidate = 'none'; this.candidateFrames = 0; this.missFrames = 0;
    this.poseSince = 0; this.fired = false; this.trail = []; this.cool = {}; this.pinchPrev = null; this.twoPinchPrev = null;
    this.waveTurns = []; this.lastDir = 0; this.lastX = null; this.cursorDown = false;
    this.hud = { pose: 'none', progress: 0, label: '' };
  }
  _ready(name, t) { return !(this.cool[name] > t); }
  _fire(events, name, t, extra = {}) {
    if (!this._ready(name, t)) return false;
    this.cool[name] = t + (COOLDOWN[name] || 1);
    events.push({ type: name, ...extra });
    return true;
  }

  update({ t, hands }) {
    const events = [];
    const infos = (hands || []).map(classify);
    // scale movement thresholds by how big the hand looks (near camera = bigger motion)
    const primary = infos[0];
    if (!primary) {
      if (++this.missFrames > 4) { this.pose = 'none'; this.candidate = 'none'; this.trail = []; this.pinchPrev = null; this.twoPinchPrev = null; this.hud = { pose: 'none', progress: 0, label: '' }; this.lastX = null; }
      return events;
    }
    this.missFrames = 0;
    const scale = Math.max(0.5, Math.min(2.2, primary.size / this.refSize)) / this.sensitivity;

    // --- two-hand pinch: zoom
    if (infos.length >= 2 && infos[0].pose === 'pinch' && infos[1].pose === 'pinch') {
      const gap = dist(infos[0].tip, infos[1].tip);
      if (this.twoPinchPrev) events.push({ type: 'zoom', factor: gap / Math.max(1e-4, this.twoPinchPrev) });
      this.twoPinchPrev = gap; this.pinchPrev = null;
      this.hud = { pose: 'pinch', progress: 1, label: 'zoom' };
      return events;
    }
    this.twoPinchPrev = null;

    // --- pose hysteresis
    const STABLE = 3;
    if (primary.pose === this.candidate) this.candidateFrames++; else { this.candidate = primary.pose; this.candidateFrames = 1; }
    if (this.candidate !== this.pose && this.candidateFrames >= STABLE) {
      this.pose = this.candidate; this.poseSince = t; this.fired = false; this.trail = [];
      this.waveTurns = []; this.lastDir = 0; this.lastX = null;
      if (this.pose !== 'pinch') { this.pinchPrev = null; if (this.cursorDown) { this.cursorDown = false; events.push({ type: 'cursor_up' }); } }
    }
    const pose = this.pose;
    const held = t - this.poseSince;
    this.hud = { pose, progress: 0, label: POSE_LABEL[pose] || '' };

    // --- air mouse (when enabled): point moves, pinch clicks
    if (this.airMouse && (pose === 'point' || pose === 'pinch')) {
      events.push({ type: 'cursor', x: primary.tip.x, y: primary.tip.y });
      if (pose === 'pinch' && !this.cursorDown) { this.cursorDown = true; this._fire(events, 'click', t, { x: primary.tip.x, y: primary.tip.y }); }
      this.hud.label = 'air mouse'; this.hud.progress = pose === 'pinch' ? 1 : 0;
      return events;
    }

    // --- holds
    const hold = HOLD[pose];
    if (hold && !(pose === 'point' && this.airMouse)) {
      const [name, need] = hold;
      // an open palm that is waving is not a "stop" hold
      const moving = pose === 'open' && this.waveTurns.length >= 2;
      this.hud.progress = this.fired || moving ? (this.fired ? 1 : 0) : Math.min(1, held / need);
      this.hud.label = `${POSE_LABEL[pose]} · ${name}`;
      if (!this.fired && !moving && held >= need) { this.fired = this._fire(events, name, t) || true; }
    }

    // --- movement trail (last 0.5 s)
    this.trail.push({ t, x: primary.centre.x, y: primary.centre.y });
    while (this.trail.length && t - this.trail[0].t > 0.5) this.trail.shift();
    const first = this.trail[0];
    const dx = primary.centre.x - first.x, dy = primary.centre.y - first.y, span = t - first.t;

    // ✌️ flick left/right: fast and decisive; a slow drift is not a swipe
    if (pose === 'two' && span >= 0.08 && Math.abs(dx) > 0.16 * scale && Math.abs(dx) > Math.abs(dy) * 1.5 && Math.abs(dx) / span > 0.55 * scale) {
      // the preview is mirrored: moving the hand to HIS right decreases x
      if (this._fire(events, dx < 0 ? 'switch_next' : 'switch_prev', t)) this.trail = [];
    }
    // 🤟 three fingers swipe up/down: volume (repeats while he keeps moving)
    if (pose === 'three' && span >= 0.08 && Math.abs(dy) > 0.09 * scale && Math.abs(dy) > Math.abs(dx) * 1.3 && Math.abs(dy) / span > 0.3 * scale) {
      if (this._fire(events, dy < 0 ? 'volume_up' : 'volume_down', t)) this.trail = [];
    }
    // 👋 wave: an open palm reversing direction three times
    if (pose === 'open') {
      if (this.lastX != null) {
        const step = primary.centre.x - this.lastX;
        if (Math.abs(step) > 0.012 * scale) {
          const dir = Math.sign(step);
          if (this.lastDir && dir !== this.lastDir) this.waveTurns.push(t);
          this.lastDir = dir;
        }
      }
      this.lastX = primary.centre.x;
      this.waveTurns = this.waveTurns.filter((w) => t - w < 1.4);
      if (this.waveTurns.length >= 3 && this._fire(events, 'wave', t)) { this.waveTurns = []; this.fired = true; }
    }
    // 🤏 pinch + move: grab and rotate the hologram
    if (pose === 'pinch') {
      if (this.pinchPrev) {
        const mx = primary.tip.x - this.pinchPrev.x, my = primary.tip.y - this.pinchPrev.y;
        if (Math.abs(mx) + Math.abs(my) > 0.002) events.push({ type: 'rotate', dx: -mx, dy: my });
      }
      this.pinchPrev = { x: primary.tip.x, y: primary.tip.y };
      this.hud.progress = 1; this.hud.label = 'pinch · rotate';
    }
    return events;
  }
}

// ---------------------------------------------------------------- synthetic hands (tests + calibration demo)

/** Build 21 plausible landmarks for a pose. cx, cy = palm centre; size = wrist->middle knuckle. */
export function synthHand(pose, { cx = 0.5, cy = 0.5, size = 0.2 } = {}) {
  const P = (x, y) => ({ x: cx + x * size, y: cy + y * size, z: 0 });
  const lm = new Array(21);
  lm[0] = P(0, 0.55);                                   // wrist (below the palm; y is down)
  const base = { 1: [-0.34, -0.02], 2: [-0.6, -0.22], 5: [-0.3, -0.42], 9: [0, -0.45], 13: [0.26, -0.4], 17: [0.48, -0.28] };
  const shape = {
    open: [1, 1, 1, 1, 1], fist: [0, 0, 0, 0, 0], point: [0, 1, 0, 0, 0], two: [0, 1, 1, 0, 0], three: [0, 1, 1, 1, 0],
    rock: [0, 1, 0, 0, 1], thumbs_up: [2, 0, 0, 0, 0], thumbs_down: [3, 0, 0, 0, 0], pinch: [4, 4, 0, 0, 0], ok: [4, 4, 1, 1, 1],
  }[pose] || [0, 0, 0, 0, 0];
  for (const [i, [x, y]] of Object.entries(base)) lm[i] = P(x, y);
  // fingers: mcp at 5/9/13/17, then pip, dip, tip
  [[5, shape[1], -0.08], [9, shape[2], 0], [13, shape[3], 0.06], [17, shape[4], 0.14]].forEach(([mcp, s, lean]) => {
    const [bx, by] = base[mcp];
    const seg = mcp === 17 ? 0.26 : 0.34;
    if (s === 1) { lm[mcp + 1] = P(bx + lean * 0.4, by - seg); lm[mcp + 2] = P(bx + lean * 0.7, by - seg * 1.8); lm[mcp + 3] = P(bx + lean, by - seg * 2.5); }
    else if (s === 4) { lm[mcp + 1] = P(bx - 0.06, by - seg * 0.9); lm[mcp + 2] = P(bx - 0.2, by - seg * 1.25); lm[mcp + 3] = P(-0.52, -0.62); }
    else { lm[mcp + 1] = P(bx, by - seg * 0.55); lm[mcp + 2] = P(bx, by - 0.02); lm[mcp + 3] = P(bx, by + 0.2); }   // curled into the palm
  });
  const t = shape[0];
  if (t === 1) { lm[3] = P(-0.86, -0.42); lm[4] = P(-1.08, -0.6); }                 // thumb out to the side
  else if (t === 2) { lm[2] = P(-0.42, -0.4); lm[3] = P(-0.44, -0.84); lm[4] = P(-0.46, -1.25); }   // thumb straight up
  else if (t === 3) { lm[1] = P(-0.3, 0.3); lm[2] = P(-0.42, 0.5); lm[3] = P(-0.44, 0.94); lm[4] = P(-0.46, 1.35); }   // thumb straight down
  else if (t === 4) { lm[3] = P(-0.62, -0.46); lm[4] = P(-0.55, -0.6); }           // thumb tip meets the index tip
  else { lm[3] = P(-0.4, -0.3); lm[4] = P(-0.16, -0.3); }                           // thumb tucked across the palm
  return lm;
}
