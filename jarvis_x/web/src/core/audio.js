// Audio engine: one AudioContext, the microphone analyser, and the voice player.
// The hologram reads features() every frame, so its motion follows the REAL audio.
import { emit, state, persona } from './bus.js';

let ctx = null;
let outGain = null;
let outAnalyser = null;
let micAnalyser = null;
let micStream = null;
const outFreq = new Uint8Array(512);
const micFreq = new Uint8Array(512);
const micTime = new Float32Array(4096);
let prevSpectrum = new Float32Array(64);
let fluxAvg = 0;
const feat = { out: { level: 0, bands: [0, 0, 0, 0], onset: 0 }, mic: { level: 0, bands: [0, 0, 0, 0] } };

export function audioContext() {
  if (!ctx) {
    ctx = new (window.AudioContext || window.webkitAudioContext)();
    outGain = ctx.createGain();
    outAnalyser = ctx.createAnalyser();
    outAnalyser.fftSize = 1024;
    outAnalyser.smoothingTimeConstant = 0.55;
    outGain.connect(outAnalyser);
    outAnalyser.connect(ctx.destination);
  }
  if (ctx.state === 'suspended') ctx.resume().catch(() => {});
  return ctx;
}
export const output = () => { audioContext(); return outGain; };

export async function startMic() {
  if (micStream) return true;
  try {
    micStream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
  } catch (err) {
    emit('mic:error', err.name === 'NotAllowedError'
      ? 'Microphone permission was blocked. Click the lock icon in the address bar and allow the microphone.'
      : 'No microphone was found.');
    return false;
  }
  const source = audioContext().createMediaStreamSource(micStream);
  micAnalyser = ctx.createAnalyser();
  micAnalyser.fftSize = 4096;
  micAnalyser.smoothingTimeConstant = 0.5;
  source.connect(micAnalyser);
  emit('mic:ready');
  return true;
}
export const micReady = () => !!micAnalyser;
export function micSamples() {
  if (!micAnalyser) return null;
  micAnalyser.getFloatTimeDomainData(micTime);
  return { data: micTime, rate: ctx.sampleRate };
}

function bandsOf(freq, binHz, edges) {
  const out = [];
  for (let b = 0; b < edges.length - 1; b++) {
    const lo = Math.max(1, Math.floor(edges[b] / binHz));
    const hi = Math.min(freq.length - 1, Math.ceil(edges[b + 1] / binHz));
    let sum = 0;
    for (let i = lo; i <= hi; i++) sum += freq[i];
    out.push(sum / ((hi - lo + 1) * 255));
  }
  return out;
}
const EDGES = [80, 300, 900, 2500, 7000];

/** Called once per frame by the hologram. */
export function features() {
  if (outAnalyser) {
    outAnalyser.getByteFrequencyData(outFreq);
    const binHz = ctx.sampleRate / outAnalyser.fftSize;
    const bands = bandsOf(outFreq, binHz, EDGES);
    const level = Math.min(1, (bands[0] * 0.9 + bands[1] * 1.2 + bands[2] + bands[3] * 0.6) / 2.2);
    // onset detection: positive spectral flux against a running average (syllable starts)
    let flux = 0;
    for (let i = 0; i < 64; i++) {
      const v = outFreq[i + 2] / 255;
      const d = v - prevSpectrum[i];
      if (d > 0) flux += d;
      prevSpectrum[i] = v;
    }
    fluxAvg = fluxAvg * 0.92 + flux * 0.08;
    const hit = flux > fluxAvg * 1.7 + 0.35 ? Math.min(1, (flux - fluxAvg) / 3) : 0;
    feat.out.onset = Math.max(hit, feat.out.onset * 0.86);
    feat.out.level += (level - feat.out.level) * 0.5;
    feat.out.bands = bands;
  }
  if (micAnalyser && !state.muted) {
    micAnalyser.getByteFrequencyData(micFreq);
    const bands = bandsOf(micFreq, ctx.sampleRate / micAnalyser.fftSize, EDGES);
    const level = Math.min(1, (bands[0] + bands[1] * 1.3 + bands[2]) / 1.6);
    feat.mic.level += (level - feat.mic.level) * 0.4;
    feat.mic.bands = bands;
  } else {
    feat.mic.level *= 0.9;
  }
  return feat;
}

// ---------------------------------------------------------------- voice player

/** Plays speech chunks in order, gapless: every chunk is fetched (prefetched while the
 *  previous one plays), decoded, and scheduled on the audio clock back to back. */
class VoicePlayer {
  constructor() { this.reset(); this.cache = new Map(); }
  reset() {
    this.queue = []; this.sources = []; this.nextTime = 0; this.token = (this.token || 0) + 1;
    this.active = 0; this.spoken = ''; this.started = false; this.ended = false;
  }
  get speaking() { return this.active > 0 || this.queue.some((q) => !q.done); }

  async fetchAudio(personaId, text, cache = false) {
    const key = `${personaId}|${text}`;
    if (this.cache.has(key)) return this.cache.get(key);
    const res = await fetch(`/api/tts?persona=${personaId}&text=${encodeURIComponent(text)}${cache ? '&cache=1' : ''}`);
    if (!res.ok) throw new Error('tts');
    const buf = await audioContext().decodeAudioData(await res.arrayBuffer());
    if (cache) this.cache.set(key, buf);
    return buf;
  }
  prefetch(personaId, phrases) {
    for (const text of phrases) this.fetchAudio(personaId, text, true).catch(() => {});
  }

  /** Add a chunk. Returns a promise that resolves when it has finished playing. */
  say(personaId, text, { caption = text, cache = false } = {}) {
    const token = this.token;
    const item = { personaId, text, caption, done: false };
    item.audio = this.fetchAudio(personaId, text, cache).catch(() => null);  // prefetch starts now
    this.queue.push(item);
    const previous = this.chain || Promise.resolve();
    this.chain = previous.then(() => this._play(item, token)).catch(() => {});
    return this.chain;
  }

  async _play(item, token) {
    if (token !== this.token) return;
    const buffer = await item.audio;
    if (token !== this.token) return;
    if (!buffer) { await this._fallback(item, token); item.done = true; return; }
    const ac = audioContext();
    const src = ac.createBufferSource();
    src.buffer = buffer;
    src.connect(outGain);
    const startAt = Math.max(ac.currentTime + 0.02, this.nextTime);
    this.nextTime = startAt + buffer.duration;
    this.sources.push(src);
    this.active++;
    const delay = Math.max(0, (startAt - ac.currentTime) * 1000);
    setTimeout(() => {
      if (token !== this.token) return;
      this.spoken += ' ' + item.text;
      if (!this.started) { this.started = true; emit('voice:first'); }
      emit('voice:chunk', { ...item, duration: buffer.duration });
    }, delay);
    src.start(startAt);
    await new Promise((resolve) => { src.onended = resolve; });
    this.active = Math.max(0, this.active - 1);
    item.done = true;
  }

  /** The voice service failed even after its own retry + fallback voice: use a browser
   *  voice that matches the persona (never a random one). */
  _fallback(item, token) {
    return new Promise((resolve) => {
      if (!('speechSynthesis' in window)) { emit('voice:chunk', { ...item, duration: 1.5, silent: true }); return setTimeout(resolve, 1500); }
      const utter = new SpeechSynthesisUtterance(item.text);
      const voices = speechSynthesis.getVoices().filter((v) => v.lang.startsWith('en'));
      const male = /ryan|george|daniel|david|mark|guy|thomas|james|male/i;
      const female = /sonia|libby|hazel|zira|aria|jenny|emily|susan|ava|emma|female|samantha|karen|moira/i;
      const want = item.personaId === 'jarvis' ? male : female;
      const avoid = item.personaId === 'jarvis' ? female : male;
      utter.voice = voices.find((v) => want.test(v.name)) || voices.find((v) => !avoid.test(v.name)) || null;
      if (item.personaId !== 'jarvis' && utter.voice && male.test(utter.voice.name)) utter.pitch = 1.5;
      if (item.personaId === 'jarvis') utter.pitch = 0.85;
      this.spoken += ' ' + item.text;
      if (!this.started) { this.started = true; emit('voice:first'); }
      emit('voice:chunk', { ...item, duration: Math.max(1, item.text.split(' ').length * 0.36), fallback: true });
      this.active++;
      const finish = () => { this.active = Math.max(0, this.active - 1); resolve(); };
      utter.onend = finish; utter.onerror = finish;
      if (token !== this.token) return finish();
      speechSynthesis.speak(utter);
    });
  }

  stop() {
    for (const src of this.sources) { try { src.onended = null; src.stop(); } catch { /* already ended */ } }
    if ('speechSynthesis' in window) speechSynthesis.cancel();
    this.reset();
    this.chain = Promise.resolve();
  }
  /** Resolves when everything queued so far has been spoken. */
  async drain() { await (this.chain || Promise.resolve()); }
}
export const voice = new VoicePlayer();

export function prefetchAcks() {
  for (const p of state.personas) voice.prefetch(p.id, [...(p.acks || []), p.greeting].filter(Boolean));
}
export function randomAck(id = state.persona) {
  const acks = persona(id).acks || [];
  return acks[Math.floor(Math.random() * acks.length)] || '';
}
