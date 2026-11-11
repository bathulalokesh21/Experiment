// Sound design: every sound is synthesised (no audio files), subtle, and toggleable.
import { audioContext, output } from '../core/audio.js';
import { state } from '../core/bus.js';

function tone({ freq = 440, to = null, dur = 0.18, type = 'sine', gain = 0.06, delay = 0, attack = 0.008 }) {
  if (state.settings.sound === false) return;
  let ac;
  try { ac = audioContext(); } catch { return; }
  const t0 = ac.currentTime + delay;
  const osc = ac.createOscillator();
  const g = ac.createGain();
  osc.type = type;
  osc.frequency.setValueAtTime(freq, t0);
  if (to) osc.frequency.exponentialRampToValueAtTime(to, t0 + dur);
  g.gain.setValueAtTime(0.0001, t0);
  g.gain.exponentialRampToValueAtTime(gain, t0 + attack);
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
  osc.connect(g);
  g.connect(ac.destination);  // UI sounds bypass the voice analyser so they don't move the hologram
  osc.start(t0);
  osc.stop(t0 + dur + 0.05);
}
function noise({ dur = 0.6, from = 200, to = 3000, gain = 0.05, delay = 0 }) {
  if (state.settings.sound === false) return;
  let ac;
  try { ac = audioContext(); } catch { return; }
  const t0 = ac.currentTime + delay;
  const buffer = ac.createBuffer(1, Math.floor(ac.sampleRate * dur), ac.sampleRate);
  const data = buffer.getChannelData(0);
  for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;
  const src = ac.createBufferSource();
  src.buffer = buffer;
  const filter = ac.createBiquadFilter();
  filter.type = 'bandpass';
  filter.Q.value = 1.2;
  filter.frequency.setValueAtTime(from, t0);
  filter.frequency.exponentialRampToValueAtTime(to, t0 + dur);
  const g = ac.createGain();
  g.gain.setValueAtTime(0.0001, t0);
  g.gain.exponentialRampToValueAtTime(gain, t0 + dur * 0.3);
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
  src.connect(filter); filter.connect(g); g.connect(ac.destination);
  src.start(t0);
}
const WAKE_NOTES = { jarvis: [523, 784], friday: [587, 880], robin: [659, 988] };
export const sfx = {
  wake(id = state.persona) { const [a, b] = WAKE_NOTES[id] || WAKE_NOTES.jarvis; tone({ freq: a, dur: 0.12 }); tone({ freq: b, dur: 0.22, delay: 0.09 }); },
  listenStart() { tone({ freq: 620, to: 930, dur: 0.12, gain: 0.045 }); },
  listenStop() { tone({ freq: 930, to: 560, dur: 0.12, gain: 0.04 }); },
  approval() { tone({ freq: 660, dur: 0.1 }); tone({ freq: 880, dur: 0.1, delay: 0.1 }); tone({ freq: 1320, dur: 0.25, delay: 0.2 }); },
  approved() { tone({ freq: 784, dur: 0.1 }); tone({ freq: 1175, dur: 0.3, delay: 0.1 }); },
  cancelled() { tone({ freq: 440, to: 220, dur: 0.25, type: 'triangle' }); },
  tick() { tone({ freq: 1500, dur: 0.035, gain: 0.03, type: 'square' }); },
  gesture() { tone({ freq: 1100, to: 1400, dur: 0.06, gain: 0.035 }); },
  morph() { noise({ dur: 0.9, from: 400, to: 5000, gain: 0.03 }); tone({ freq: 220, to: 660, dur: 0.8, gain: 0.03, type: 'triangle' }); },
  chip() { tone({ freq: 1250, dur: 0.05, gain: 0.02 }); },
  error() { tone({ freq: 200, dur: 0.3, type: 'sawtooth', gain: 0.03 }); },
  bootHum() { tone({ freq: 55, to: 110, dur: 2.6, type: 'sawtooth', gain: 0.03, attack: 1.2 }); noise({ dur: 2.6, from: 120, to: 2400, gain: 0.025 }); },
  bootBoom() { tone({ freq: 90, to: 36, dur: 1.4, gain: 0.16, type: 'sine' }); noise({ dur: 1.1, from: 3000, to: 200, gain: 0.05 }); },
  shutdown() { tone({ freq: 660, to: 40, dur: 1.6, type: 'triangle', gain: 0.06 }); noise({ dur: 1.4, from: 4000, to: 120, gain: 0.03 }); },
  click(accent = false) { tone({ freq: accent ? 1800 : 1200, dur: 0.03, gain: 0.09, type: 'square' }); },
  reminder() { tone({ freq: 880, dur: 0.14 }); tone({ freq: 880, dur: 0.14, delay: 0.2 }); tone({ freq: 1175, dur: 0.3, delay: 0.4 }); },
};
