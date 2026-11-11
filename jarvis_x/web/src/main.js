// JARVIS X dashboard entry point.
import { $, on, emit, state, setMode } from './core/bus.js';
import { get, connectEvents } from './core/api.js';
import { features, startMic } from './core/audio.js';
import { speech, hear } from './core/speech.js';
import * as convo from './core/conversation.js';
import * as text from './core/text.js';
import { Hologram } from './holo/engine.js';
import { startAmbient } from './holo/ambient.js';
import { initOverlay, closeOverlay } from './ui/overlay.js';
import { initWidgets, renderPower } from './ui/widgets.js';
import { initPanels, focusStart, focusStop } from './ui/panels.js';
import { initApprovals, resolve as resolveApproval } from './ui/approvals.js';
import * as extras from './ui/extras.js';
import * as protocols from './fx/protocols.js';
import * as guitar from './guitar/tuner.js';
import * as vision from './vision/camera.js';
import * as gestures from './vision/gestures.js';
import { PresenceTracker } from './vision/presence.js';
import * as pitch from './guitar/pitch.js';
import { sfx } from './fx/sfx.js';

document.body.classList.add('powering');

async function start() {
  const res = await get('/api/state');
  if (!res.ok) {
    $('#boot-lines').innerHTML = '<li><span>Server</span><b style="color:#ff6b7d">not answering. Is python run.py running?</b></li>';
    return;
  }
  Object.assign(state, { personas: res.personas, settings: res.settings, fake: res.fake, ready: res.ready || {}, usage: res.usage });
  state.persona = res.personas.some((p) => p.id === res.settings.active) ? res.settings.active : 'jarvis';
  document.body.dataset.persona = state.persona;

  const holo = new Hologram($('#holo'));
  holo.setPersona(state.persona, true);
  holo.setMood(state.settings.humor);
  const mode = await holo.init();
  if (mode === '2d') convo.toast('WebGL is unavailable, so the hologram is running in simple mode.');
  startAmbient($('#ambient'));
  for (const mod of [protocols, guitar, vision, extras]) mod.bindHologram(holo);

  initOverlay(); initWidgets(); initPanels(); initApprovals(); extras.initExtras(); guitar.initGuitar(); vision.initVision();
  protocols.initProtocols();
  renderPower(res.usage);
  connectEvents();

  // hologram follows the conversation
  on('mode', (m) => holo.setState(m));
  on('persona', ({ id }) => holo.setPersona(id));
  on('humor', (v) => holo.setMood(v));
  on('settings', (s) => holo.setMood(s.humor));

  // drag to rotate, wheel to zoom
  const canvas = $('#holo');
  let drag = null;
  canvas.addEventListener('pointerdown', (e) => { drag = { x: e.clientX, y: e.clientY }; canvas.setPointerCapture(e.pointerId); });
  canvas.addEventListener('pointermove', (e) => { if (!drag) return; holo.rotate((e.clientX - drag.x) * 0.002, (e.clientY - drag.y) * 0.0015); drag = { x: e.clientX, y: e.clientY }; });
  canvas.addEventListener('pointerup', () => { drag = null; });
  canvas.addEventListener('wheel', (e) => { holo.setZoom(holo.zoomTarget * (e.deltaY < 0 ? 1.08 : 0.93)); e.preventDefault(); }, { passive: false });
  canvas.addEventListener('dblclick', () => speech.capture(8));

  // mic ring + level meter
  const ring = $('#mic-ring'), meter = $('#mic-level');
  const paint = () => {
    const f = features();
    const level = state.muted ? 0 : f.mic.level;
    meter.style.width = `${Math.min(100, level * 160)}%`;
    ring.style.opacity = String(Math.min(1, level * 2.2));
    ring.style.transform = `scale(${1 + level * 0.5})`;
    requestAnimationFrame(paint);
  };
  requestAnimationFrame(paint);

  // talk bar
  $('#talkbar').addEventListener('submit', (e) => {
    e.preventDefault();
    const input = $('#talk-input');
    const value = input.value.trim();
    if (!value) return;
    input.value = '';
    const wake = text.parseWake(value);
    if (wake && wake.index === 0 && wake.rest) convo.ask(wake.rest, { persona: wake.persona });
    else convo.ask(value);
  });
  $('#mic-btn').addEventListener('click', async () => { await startMic(); speech.start(); if (state.muted) return convo.toast('The microphone is muted.'); speech.capture(8); });
  $('#stop-btn').addEventListener('click', () => convo.stop());

  // keyboard: Space = talk, Esc = stop, Ctrl+K = palette, Ctrl+Shift+D = debug
  addEventListener('keydown', (e) => {
    const typing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName || '');
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); extras.openPalette(); }
    else if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === 'd') { e.preventDefault(); extras.toggleDebug(); }
    else if (e.key === 'Escape') { if (!extras.closePalette() && !closeOverlay()) convo.stop(); }
    else if (e.code === 'Space' && !typing && state.booted && !state.asleep) { e.preventDefault(); $('#mic-btn').click(); }
  });

  // actions the crew, routines, gestures and the palette can trigger
  on('ui:action', ({ action, value }) => {
    switch (action) {
      case 'house_party': protocols.setParty(!state.party); break;
      case 'clean_slate': protocols.cleanSlate(); break;
      case 'ambient': protocols.enterAmbient(); break;
      case 'wake': protocols.wakeUp(); protocols.exitAmbient(); break;
      case 'focus_start': focusStart(parseFloat(value) || 25); break;
      case 'focus_stop': focusStop(); break;
      case 'switch': convo.switchTo(String(value).toLowerCase()); break;
      case 'tuner': guitar.openTuner(); break;
      case 'metronome_start': guitar.metronome(true, parseFloat(value) || undefined); break;
      case 'metronome_stop': guitar.metronome(false); break;
      case 'orb': extras.openOrb(); break;
      case 'memory_panel': extras.openMemory(); break;
      case 'comic': extras.openComic(); break;
      case 'palette': extras.openPalette(); break;
      case 'camera_on': vision.cameraOn(); break;
      case 'camera_off': vision.cameraOff(); break;
      case 'sketch': vision.sketchToLife(); break;
      case 'listen': speech.capture(8); break;
      case 'open_url': window.open(value, '_blank', 'noopener'); break;
      default: break;
    }
  });
  on('srv:ui', (ev) => emit('ui:action', { action: ev.action, value: ev.value ?? ev.url }));
  on('command', (cmd) => { if (cmd === 'approve' || cmd === 'cancel') resolveApproval(cmd, 'voice'); });
  on('srv:offline', () => { $('#mic-state').textContent = 'server offline'; });
  on('speech:wake', () => holo.beat(0.8));
  on('notice', () => holo.beat(0.8));
  on('srv:approval', () => holo.beat(0.5));

  // test + debugging hooks (also handy in the browser console)
  window.JX = { state, holo, convo, speech, hear, text, gestures, vision, pitch, PresenceTracker, sfx, emit, on, extras, protocols, guitar, setMode };
  emit('ready');
  document.body.dataset.ready = '1';
}

start().catch((err) => { console.error(err); $('#boot-lines').innerHTML = `<li><span>Dashboard error</span><b style="color:#ff6b7d">${String(err.message || err)}</b></li>`; });
