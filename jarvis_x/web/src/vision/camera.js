// Vision 2.0. Camera FIRST (so the permission prompt always appears), then the bundled
// MediaPipe (local files, no CDN). Everything is processed in the browser; faces are only counted.
import { $, el, on, emit, state, persona, setMode } from '../core/bus.js';
import { post, put, upload } from '../core/api.js';
import { GestureEngine, POSE_ICON, classify, handSize } from './gestures.js';
import { PresenceTracker } from './presence.js';
import { ask, sayLocal, stop, switchTo, toast } from '../core/conversation.js';
import { speech } from '../core/speech.js';
import { resolve as resolveApproval } from '../ui/approvals.js';
import { setMuted } from '../ui/panels.js';
import { sfx } from '../fx/sfx.js';

let stream = null, hands = null, faces = null, loop = null, holo = null, calibrating = null;
export const engine = new GestureEngine();
export const presence = new PresenceTracker();
export const bindHologram = (h) => { holo = h; };
const status = (text) => { $('#cam-status').textContent = text; };

export async function cameraOn() {
  if (stream) return true;
  // step 1: the camera itself. Nothing else is allowed to delay the permission prompt.
  status('Asking for the camera…');
  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480, facingMode: 'user' }, audio: false });
  } catch (err) {
    status(err.name === 'NotAllowedError' ? 'Step 1 failed: camera permission was blocked. Click the lock icon in the address bar, allow the camera, and try again.'
      : err.name === 'NotFoundError' ? 'Step 1 failed: no camera was found.' : `Step 1 failed: the camera is busy or unavailable (${err.name}). Close other apps using it.`);
    return false;
  }
  const video = $('#cam');
  video.srcObject = stream;
  await video.play().catch(() => {});
  $('#cam-off').hidden = true;
  $('#cam-toggle').textContent = 'Turn off camera';
  state.cameraOn = true;
  status('Camera on. Step 2: loading hand tracking…');
  $('#gesture-hud').hidden = false;
  // step 2 + 3: models. The preview keeps working even if these fail.
  try {
    const vision = await import('/vendor/mediapipe/vision_bundle.mjs');
    const files = await vision.FilesetResolver.forVisionTasks('/vendor/mediapipe/wasm');
    // try the GPU first, then fall back to the CPU (some drivers refuse the GPU delegate)
    const create = async (Task, model, extra) => {
      let last = null;
      for (const delegate of ['GPU', 'CPU']) {
        try { return await Task.createFromOptions(files, { baseOptions: { modelAssetPath: model, delegate }, runningMode: 'VIDEO', ...extra }); }
        catch (err) { last = err; }
      }
      throw last;
    };
    try { hands = await create(vision.HandLandmarker, '/models/hand_landmarker.task', { numHands: 2 }); }
    catch (err) { status(`Step 2 failed: the hand model did not load (${err.message || err}). The preview still works.`); }
    try { faces = await create(vision.FaceDetector, '/models/blaze_face_short_range.tflite', {}); }
    catch (err) { status(`Step 3 failed: the face detector did not load (${err.message || err}). Gestures still work.`); }
    if (hands && faces) status('Vision ready. Hands and faces are processed on this laptop only.');
    if (hands && !(state.settings.calibration && state.settings.calibration.size)) toast('First time? Press Calibrate so gestures fit your hand and distance.');
  } catch (err) {
    status(`Step 2 failed: MediaPipe could not start (${err.message || err}). The camera preview still works.`);
  }
  startLoop();
  return true;
}

export function cameraOff() {
  if (!stream) return;
  stream.getTracks().forEach((t) => t.stop());
  stream = null; cancelAnimationFrame(loop);
  $('#cam').srcObject = null;
  $('#cam-off').hidden = false; $('#cam-toggle').textContent = 'Turn on camera';
  $('#gesture-hud').hidden = true; $('#air-cursor').hidden = true;
  state.cameraOn = false; engine.reset();
  status('Camera off.');
  setPeople(0);
}

function startLoop() {
  const video = $('#cam'), overlay = $('#cam-overlay'), g = overlay.getContext('2d');
  let lastTime = -1, lastFace = 0;
  const tick = () => {
    if (!stream) return;
    loop = requestAnimationFrame(tick);
    if (video.readyState < 2 || video.currentTime === lastTime) return;
    lastTime = video.currentTime;
    const now = performance.now();
    let landmarks = [];
    if (hands) { try { landmarks = hands.detectForVideo(video, now).landmarks || []; } catch { /* a dropped frame */ } }
    if (faces && now - lastFace > 400) {
      lastFace = now;
      try { handleFaces(faces.detectForVideo(video, now).detections.length, now / 1000); } catch { /* a dropped frame */ }
    }
    if (overlay.width !== video.videoWidth) { overlay.width = video.videoWidth; overlay.height = video.videoHeight; }
    g.clearRect(0, 0, overlay.width, overlay.height);
    g.fillStyle = getComputedStyle(document.body).getPropertyValue('--c');
    for (const lm of landmarks) for (const p of lm) g.fillRect(p.x * overlay.width - 2, p.y * overlay.height - 2, 4, 4);
    feed(landmarks, now / 1000);
  };
  loop = requestAnimationFrame(tick);
}

/** One frame of hand landmarks -> gesture events -> actions. Tests call this with synthetic hands. */
export function feed(landmarks, t) {
  if (calibrating && landmarks[0]) calibrating.sizes.push(handSize(landmarks[0]));
  const events = engine.update({ t, hands: landmarks });
  const hud = engine.hud;
  $('#hud-pose').textContent = POSE_ICON[hud.pose] || '·';
  $('#hud-label').textContent = hud.label || 'show a hand';
  $('#hud-ring').style.strokeDashoffset = String(119.4 * (1 - hud.progress));
  for (const ev of events) act(ev);
  return events;
}

const order = () => state.personas.map((p) => p.id);
function act(ev) {
  const discrete = !['rotate', 'zoom', 'cursor', 'cursor_up'].includes(ev.type);
  if (discrete) { sfx.gesture(); emit('gesture', ev.type); }
  switch (ev.type) {
    case 'switch_next': case 'switch_prev': {
      const ids = order(); const i = ids.indexOf(state.persona);
      switchTo(ids[(i + (ev.type === 'switch_next' ? 1 : ids.length - 1)) % ids.length]); break;
    }
    case 'stop': stop(); toast('Stopped'); break;
    case 'mute': setMuted(!state.muted); break;
    case 'listen': speech.capture(8); toast('Listening'); break;
    case 'approve': if (state.approvals.length) resolveApproval('approve', 'gesture'); break;
    case 'cancel': if (state.approvals.length) resolveApproval('cancel', 'gesture'); break;
    case 'confirm': if (state.approvals.length) toast('Use 👍 to approve a card.'); else emit('confirm'); break;
    case 'party': emit('ui:action', { action: 'house_party' }); break;
    case 'wave': emit('ui:action', { action: 'wake' }); setMode('notice'); setTimeout(() => { if (state.mode === 'notice') setMode('idle'); }, 800); emit('notice', 'wave'); break;
    case 'volume_up': post('/api/tool', { name: 'volume', args: { action: 'up', steps: 3 } }); toast('Volume up'); break;
    case 'volume_down': post('/api/tool', { name: 'volume', args: { action: 'down', steps: 3 } }); toast('Volume down'); break;
    case 'rotate': if (holo) holo.rotate(ev.dx * 6, ev.dy * 4); break;
    case 'zoom': if (holo) holo.setZoom(holo.zoomTarget * ev.factor); break;
    case 'cursor': moveCursor(ev.x, ev.y); break;
    case 'cursor_up': $('#air-cursor').classList.remove('down'); break;
    case 'click': airClick(ev.x, ev.y); break;
    default: break;
  }
}

// ---- air mouse: the index fingertip drives a cursor; pinch clicks whatever is under it
let cursor = { x: innerWidth / 2, y: innerHeight / 2 };
function toScreen(x, y) {   // mirrored, with margins so the screen edges are reachable
  const nx = Math.min(1, Math.max(0, (1 - x - 0.15) / 0.7)), ny = Math.min(1, Math.max(0, (y - 0.15) / 0.6));
  return { x: nx * innerWidth, y: ny * innerHeight };
}
function moveCursor(x, y) {
  const target = toScreen(x, y);
  cursor.x += (target.x - cursor.x) * 0.35; cursor.y += (target.y - cursor.y) * 0.35;   // smoothing
  const node = $('#air-cursor');
  node.hidden = false;
  node.style.left = `${cursor.x}px`; node.style.top = `${cursor.y}px`;
}
function airClick(x, y) {
  moveCursor(x, y);
  const node = $('#air-cursor');
  node.classList.add('down');
  setTimeout(() => node.classList.remove('down'), 220);
  const target = document.elementFromPoint(cursor.x, cursor.y);
  const clickable = target && target.closest('button, a, input, [data-expand], .crew, .t, li');
  if (clickable) { clickable.click(); sfx.tick(); }
}

// ---- presence
function setPeople(count) {
  if (state.people === count) return;
  state.people = count;
  $('#people-count').textContent = `People in view: ${count}`;
  post('/api/vision/context', { people: count });
}
let dimmed = false;
export function handleFaces(count, t) {
  for (const ev of presence.update(count, t)) {
    if (ev.type === 'people') setPeople(ev.count);
    else if (ev.type === 'arrive') { setMode('notice'); emit('notice', 'presence'); setTimeout(() => { if (state.mode === 'notice') setMode('idle'); }, 900);
      if (state.booted && !state.busy && !state.speaking) sayLocal(`Good to see you, ${persona().address}.`, undefined, { log: false }); }
    else if (ev.type === 'away') { dimmed = true; document.body.classList.add('dim'); speech.cancelCapture(); state.muted = true; toast('You stepped away. Listening paused.'); }
    else if (ev.type === 'return') { if (dimmed) { dimmed = false; document.body.classList.remove('dim'); state.muted = false; toast('Welcome back.'); emit('notice', 'presence'); } }
    else if (ev.type === 'friend') { if (state.booted && !state.busy && !state.speaking) sayLocal(`I see we have company. Hello there. I'll keep private things discreet, ${persona().address}.`, undefined, { log: false }); }
  }
}

// ---- calibration (20 s): learns how big his hand looks at his normal distance
export async function calibrate() {
  if (!(await cameraOn())) return;
  if (!hands) return toast('Hand tracking is not loaded, so I cannot calibrate.');
  calibrating = { sizes: [] };
  const seconds = new URLSearchParams(location.search).has('fast') ? 1 : 20;
  toast(`Calibration: hold an open palm up at your normal distance for ${seconds} seconds.`);
  status(`Calibrating… keep your open palm in view (${seconds} s).`);
  await new Promise((r) => setTimeout(r, seconds * 1000));
  finishCalibration();
}
export function finishCalibration() {
  const sizes = (calibrating ? calibrating.sizes : []).sort((a, b) => a - b);
  calibrating = null;
  if (sizes.length < 5) { status('Calibration failed: I never saw your hand. Try again with better light.'); return null; }
  const median = sizes[Math.floor(sizes.length / 2)];
  engine.refSize = median;
  put('/api/settings', { calibration: { size: median, at: Date.now() } });
  status(`Calibrated to your hand (size ${median.toFixed(3)}). Gestures are tuned to your distance.`);
  toast('Calibration saved.');
  return median;
}
export const beginCalibration = () => { calibrating = { sizes: [] }; };

/** Sketch to life: one frame from the webcam, sent to the crew to read. */
export async function sketchToLife() {
  if (!(await cameraOn())) return;
  toast('Hold your drawing up to the camera… capturing in 3');
  await new Promise((r) => setTimeout(r, new URLSearchParams(location.search).has('fast') ? 50 : 3000));
  const video = $('#cam');
  const canvas = el('canvas', { width: video.videoWidth || 640, height: video.videoHeight || 480 });
  canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
  sfx.tick();
  const blob = await new Promise((r) => canvas.toBlob(r, 'image/jpeg', 0.9));
  const res = await upload('/api/vision/snapshot', new File([blob], 'sketch.jpg', { type: 'image/jpeg' }));
  if (!res.ok) return toast(res.message);
  ask(res.prompt, { raw: true, display: 'Sketch to life: read what I am holding up' });
}

export function initVision() {
  const s = state.settings;
  if (s.calibration && s.calibration.size) engine.refSize = s.calibration.size;
  engine.sensitivity = s.gesture_sensitivity || 1;
  $('#cam-toggle').addEventListener('click', () => (stream ? cameraOff() : cameraOn()));
  $('#cam-calibrate').addEventListener('click', calibrate);
  $('#air-toggle').addEventListener('change', (e) => { engine.airMouse = e.target.checked; if (!e.target.checked) $('#air-cursor').hidden = true; });
  $('#sens').addEventListener('change', (e) => { engine.sensitivity = +e.target.value; put('/api/settings', { gesture_sensitivity: +e.target.value }); });
  // first run: offer calibration once the camera is on
  on('gesture', () => {});
}
