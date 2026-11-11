// Pitch detection for the guitar tuner (autocorrelation with parabolic interpolation). Pure.
export const NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
export const STRINGS = [{ name: 'E2', hz: 82.41 }, { name: 'A2', hz: 110.0 }, { name: 'D3', hz: 146.83 }, { name: 'G3', hz: 196.0 }, { name: 'B3', hz: 246.94 }, { name: 'E4', hz: 329.63 }];

/** Returns frequency in Hz, or 0 when the signal is too quiet or unclear. */
export function detectPitch(buf, sampleRate, { minHz = 65, maxHz = 1000 } = {}) {
  const n = buf.length;
  let rms = 0;
  for (let i = 0; i < n; i++) rms += buf[i] * buf[i];
  rms = Math.sqrt(rms / n);
  if (rms < 0.008) return 0;
  const minLag = Math.floor(sampleRate / maxHz), maxLag = Math.min(n - 2, Math.ceil(sampleRate / minHz));
  const half = Math.floor(n / 2);
  const corr = new Float32Array(maxLag + 2);
  let zero = 0;
  for (let i = 0; i < half; i++) zero += buf[i] * buf[i];
  for (let lag = minLag - 1; lag <= maxLag + 1; lag++) {
    let sum = 0;
    for (let i = 0; i < half; i++) sum += buf[i] * buf[i + lag];
    corr[lag] = sum / (zero || 1);
  }
  // first strong peak after the correlation has dipped (avoids picking an octave too high or low)
  let lag = minLag, dipped = false, best = -1, bestLag = 0;
  for (; lag <= maxLag; lag++) {
    if (corr[lag] < 0.5) dipped = true;
    if (dipped && corr[lag] > corr[lag - 1] && corr[lag] >= corr[lag + 1] && corr[lag] > 0.82) { best = corr[lag]; bestLag = lag; break; }
  }
  if (best < 0) return 0;
  const a = corr[bestLag - 1], b = corr[bestLag], c = corr[bestLag + 1];
  const shift = (a - c) / (2 * (a - 2 * b + c) || 1);
  return sampleRate / (bestLag + shift);
}

/** Hz -> {note, octave, cents (-50..50), string (nearest guitar string)} */
export function describe(hz) {
  if (!hz) return null;
  const midi = 69 + 12 * Math.log2(hz / 440);
  const nearest = Math.round(midi);
  const cents = Math.round((midi - nearest) * 100);
  const string = STRINGS.reduce((best, s) => (Math.abs(Math.log2(hz / s.hz)) < Math.abs(Math.log2(hz / best.hz)) ? s : best));
  return { note: NOTE_NAMES[((nearest % 12) + 12) % 12], octave: Math.floor(nearest / 12) - 1, cents, hz: Math.round(hz * 10) / 10, string,
    stringCents: Math.round(1200 * Math.log2(hz / string.hz)) };
}
