// Guitar companion: live tuner (mic), metronome the hologram breathes to, practice timer.
import { $, el, on, state } from '../core/bus.js';
import { post } from '../core/api.js';
import { audioContext, startMic, micSamples } from '../core/audio.js';
import { detectPitch, describe, STRINGS } from './pitch.js';
import { openOverlay, closeOverlay } from '../ui/overlay.js';
import { toast } from '../core/conversation.js';

let tunerTimer = null;
export async function openTuner() {
  if (!(await startMic())) return toast('The tuner needs the microphone.');
  const note = el('div', { class: 'note', text: '–' });
  const needle = el('div', { class: 'needle' });
  const info = el('div', { class: 'sub', text: 'Pluck one string and let it ring.' });
  const strings = el('div', { class: 'strings' }, ...STRINGS.map((s) => el('span', { class: 'pill', 'data-string': s.name, text: s.name })));
  openOverlay('Guitar tuner', el('div', { class: 'tuner' }, note, el('div', { class: 'needle-wrap' }, needle), info, strings), () => clearInterval(tunerTimer));
  let smooth = 0;
  clearInterval(tunerTimer);
  tunerTimer = setInterval(() => {
    const s = micSamples();
    if (!s) return;
    const d = describe(detectPitch(s.data, s.rate));
    if (!d) return;
    smooth += (d.stringCents - smooth) * 0.35;
    const cents = Math.max(-50, Math.min(50, smooth));
    note.textContent = d.string.name;
    needle.style.transform = `rotate(${cents * 0.9}deg)`;
    const ok = Math.abs(cents) <= 5;
    needle.classList.toggle('ok', ok);
    info.textContent = ok ? `${d.hz} Hz · in tune` : `${d.hz} Hz · ${Math.abs(Math.round(cents))} cents ${cents < 0 ? 'flat: tighten' : 'sharp: loosen'}`;
    strings.querySelectorAll('[data-string]').forEach((n) => n.classList.toggle('on', n.dataset.string === d.string.name));
  }, 90);
}
export const closeTuner = () => { clearInterval(tunerTimer); closeOverlay(); };

// ---------------------------------------------------------------- metronome
const metro = { on: false, bpm: 80, next: 0, beat: 0, timer: null };
let holo = null;
export const bindHologram = (h) => { holo = h; };
function click(time, accent) {
  const ac = audioContext();
  const osc = ac.createOscillator(), g = ac.createGain();
  osc.frequency.value = accent ? 1760 : 1175;
  g.gain.setValueAtTime(0.0001, time); g.gain.exponentialRampToValueAtTime(0.16, time + 0.002); g.gain.exponentialRampToValueAtTime(0.0001, time + 0.05);
  osc.connect(g); g.connect(ac.destination);
  osc.start(time); osc.stop(time + 0.06);
}
export function metronome(on_, bpm) {
  if (bpm) { metro.bpm = Math.max(40, Math.min(208, Math.round(bpm))); $('#metro-bpm').value = metro.bpm; $('#metro-bpm-label').textContent = metro.bpm; }
  if (on_ === metro.on) return;
  metro.on = on_;
  $('#metro-toggle').classList.toggle('on', on_);
  $('#metro-toggle').textContent = on_ ? 'Stop metronome' : 'Metronome';
  clearInterval(metro.timer);
  if (!on_) return;
  const ac = audioContext();
  metro.next = ac.currentTime + 0.08; metro.beat = 0;
  metro.timer = setInterval(() => {   // look-ahead scheduler: sample-accurate clicks
    while (metro.next < ac.currentTime + 0.12) {
      const accent = metro.beat % 4 === 0, at = metro.next;
      click(at, accent);
      setTimeout(() => { $('#metro-dot').classList.add('beat'); if (holo) holo.beat(accent ? 1 : 0.6); setTimeout(() => $('#metro-dot').classList.remove('beat'), 90); }, Math.max(0, (at - ac.currentTime) * 1000));
      metro.next += 60 / metro.bpm; metro.beat++;
    }
  }, 25);
}

// ---------------------------------------------------------------- practice timer
const practice = { on: false, since: 0, timer: null };
function togglePractice() {
  practice.on = !practice.on;
  $('#practice-toggle').textContent = practice.on ? 'Stop & log' : 'Start practice';
  $('#practice-toggle').classList.toggle('on', practice.on);
  if (practice.on) {
    practice.since = Date.now();
    practice.timer = setInterval(() => { const s = Math.floor((Date.now() - practice.since) / 1000); $('#practice-time').textContent = `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`; }, 500);
  } else {
    clearInterval(practice.timer);
    const minutes = (Date.now() - practice.since) / 60000;
    $('#practice-time').textContent = '00:00';
    if (minutes >= 0.5) post('/api/guitar/log', { minutes: Math.round(minutes * 10) / 10 }).then(() => toast(`Logged ${Math.round(minutes)} min of practice.`));
    else toast('Under 30 seconds: not logged.');
  }
}

export function initGuitar() {
  $('#tuner-open').addEventListener('click', openTuner);
  $('#metro-toggle').addEventListener('click', () => metronome(!metro.on));
  $('#metro-bpm').addEventListener('input', (e) => { metro.bpm = +e.target.value; $('#metro-bpm-label').textContent = metro.bpm; });
  $('#practice-toggle').addEventListener('click', togglePractice);
  on('command', (cmd) => { if (cmd === 'tuner') openTuner(); });
}
