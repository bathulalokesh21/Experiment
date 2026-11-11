// Cinematic boot, Clean Slate, House Party, ambient mode.
import { $, $$, el, emit, on, state, persona } from '../core/bus.js';
import { get, post } from '../core/api.js';
import { audioContext, startMic, prefetchAcks } from '../core/audio.js';
import { speech } from '../core/speech.js';
import { sayLocal, stop, ask, toast } from '../core/conversation.js';
import { sfx } from './sfx.js';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let holo = null;
export const bindHologram = (h) => { holo = h; };

export async function boot() {
  const lines = $('#boot-lines');
  const fast = new URLSearchParams(location.search).has('fast');
  const pace = fast ? 0 : 1;
  audioContext();
  $('#boot-start').hidden = true;
  sfx.bootHum();
  const checks = await get('/api/boot');
  for (const c of checks.ok ? checks.checks : [{ label: 'Server', value: 'not answering' }]) {
    lines.append(el('li', {}, el('span', { text: c.label }), el('b', { text: c.value })));
    sfx.tick();
    await sleep(170 * pace);
  }
  const micOk = await startMic();
  lines.append(el('li', {}, el('span', { text: 'Microphone' }), el('b', { text: micOk ? 'online' : 'unavailable (typing works)' })));
  speech.start();
  prefetchAcks();
  await sleep(260 * pace);
  sfx.bootBoom();
  $('#boot').classList.add('gone');
  document.body.classList.remove('powering');
  // panels power on with a stagger
  $$('.card, .panel').forEach((node, i) => { node.style.transitionDelay = `${i * (fast ? 0 : 45)}ms`; setTimeout(() => { node.style.transitionDelay = ''; }, 2500); });
  if (holo) holo.assembleIn();   // the hologram assembles from light
  await sleep(1400 * pace);
  state.booted = true;
  emit('booted');
  const p = persona();
  await sayLocal(p.greeting || 'Welcome home, sir.', p.id, { cache: true });
  morningBrief();
}

async function morningBrief() {
  const res = await get('/api/brief');
  if (!res.ok || !res.first_today) return;
  await post('/api/brief/seen');
  if (new URLSearchParams(location.search).has('nobrief')) return;
  ask('Give me my morning brief.', { raw: true, display: 'Morning brief (first open today)', noLearn: true });
}

export async function cleanSlate() {
  stop();
  sfx.shutdown();
  if (holo) holo.collapse();
  setParty(false);
  await sayLocal(`Clean slate. Powering down, ${persona().address}.`, undefined, { log: false });
  document.body.classList.add('powering');
  state.asleep = true;
  $('#shutdown').hidden = false;
}
export async function wakeUp() {
  if (state.ambient) return exitAmbient();
  if (!state.asleep) return;
  state.asleep = false;
  $('#shutdown').hidden = true;
  document.body.classList.remove('powering');
  sfx.bootBoom();
  if (holo) holo.assembleIn();
  await sayLocal(`Back online, ${persona().address}.`, undefined, { log: false });
}

export function setParty(on_) {
  if (state.party === on_) return;
  state.party = on_;
  document.body.classList.toggle('party', on_);
  if (holo) holo.setParty(on_);
  $('[data-quick="party"]').classList.toggle('on', on_);
  if (on_) { toast('House Party Protocol. Make some noise.'); sayLocal('House Party Protocol engaged.', undefined, { log: false }); }
}

let idleSince = Date.now();
export function enterAmbient() {
  if (state.ambient || state.asleep || state.busy || state.speaking) return;
  state.ambient = true;
  document.body.classList.add('ambient');
  $('#ambient-screen').hidden = false;
  if (holo) holo.setZoom(1.25);
}
export function exitAmbient() {
  idleSince = Date.now();
  if (!state.ambient) return;
  state.ambient = false;
  document.body.classList.remove('ambient');
  $('#ambient-screen').hidden = true;
  if (holo) holo.setZoom(1);
}

export function initProtocols() {
  $('#wake-btn').addEventListener('click', wakeUp);
  const begin = () => { if (!state.booted && !boot.started) { boot.started = true; boot(); } };
  $('#boot-start').addEventListener('click', begin);
  addEventListener('keydown', begin, { once: true });
  if (new URLSearchParams(location.search).has('autoboot')) begin();
  for (const type of ['pointerdown', 'keydown', 'pointermove']) addEventListener(type, () => exitAmbient(), { passive: true });
  for (const ev of ['ask', 'speech:wake', 'notice', 'srv:reminder', 'srv:approval']) on(ev, exitAmbient);
  setInterval(() => {
    const minutes = state.settings.ambient_minutes || 5;
    if (state.booted && !state.busy && !state.speaking && Date.now() - idleSince > minutes * 60000) enterAmbient();
    if (state.busy || state.speaking) idleSince = Date.now();
  }, 5000);
  on('command', (cmd) => { if (cmd === 'party') setParty(!state.party); else if (cmd === 'clean') cleanSlate(); else if (cmd === 'wake') wakeUp(); else if (cmd === 'ambient') enterAmbient(); else if (cmd === 'stop') stop(); });
}
