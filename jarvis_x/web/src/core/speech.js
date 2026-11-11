// Speech recognition: wake words, follow-up window, barge-in, echo filter.
import { emit, on, state, setMode, $ } from './bus.js';
import { parseWake, bargeIn, isEcho } from './text.js';
import { voice } from './audio.js';
import { sfx } from '../fx/sfx.js';

const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let rec = null;
let wanted = false;
let captureUntil = 0;      // while now < captureUntil, anything he says is a request (no wake word needed)
let lastInterim = '';
let restartTimer = null;

export const speech = {
  supported: !!Recognition,
  start() {
    wanted = true;
    if (!Recognition) { emit('speech:status', 'unsupported'); return false; }
    if (rec) return true;
    rec = new Recognition();
    rec.lang = 'en-IN';
    rec.continuous = true;
    rec.interimResults = true;
    rec.maxAlternatives = 1;
    rec.onresult = (event) => {
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        hear(result[0].transcript, result.isFinal);
      }
    };
    rec.onerror = (event) => {
      if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
        wanted = false;
        emit('speech:status', 'blocked');
      } else if (event.error === 'network') emit('speech:status', 'offline');
    };
    rec.onend = () => {
      rec = null;
      if (wanted) { clearTimeout(restartTimer); restartTimer = setTimeout(() => speech.start(), 250); }
    };
    try { rec.start(); emit('speech:status', 'on'); } catch { rec = null; }
    return true;
  },
  stop() { wanted = false; try { rec && rec.stop(); } catch { /* not running */ } rec = null; emit('speech:status', 'off'); },
  /** Mic button / Space / point gesture: the next thing he says is the request. */
  capture(seconds = 8) {
    captureUntil = Date.now() + seconds * 1000;
    if (!state.speaking) setMode('listen');
    sfx.listenStart();
    emit('speech:capture', seconds);
  },
  followUp() { captureUntil = Date.now() + (state.drill ? 20000 : 8000); },
  cancelCapture() { captureUntil = 0; },
  get capturing() { return Date.now() < captureUntil; },
  hear,
};

/** Everything recognised goes through here (tests call it directly). */
export function hear(transcript, isFinal = true) {
  const text = (transcript || '').trim();
  if (!text || state.muted || state.asleep && !parseWake(text) && !/wake/i.test(text)) return;
  $('#mic-heard').textContent = text;

  // 1. while the assistant is talking: echo filter + barge-in
  if (state.speaking) {
    const verdict = bargeIn(text, voice.spoken + ' ' + (state.currentReply || ''), state.settings.interrupt !== false);
    if (!verdict.interrupt) return;
    if (!isFinal && verdict.reason === 'speech' && text.split(' ').length < 4) return;  // wait for a little more
    emit('speech:barge', verdict);
    if (verdict.stopOnly) { lastInterim = ''; return; }
    if (!isFinal) { lastInterim = text; captureUntil = Date.now() + 6000; return; }
  }
  if (!isFinal) {
    if (speech.capturing || parseWake(text)) { emit('speech:interim', text); if (!state.speaking && !state.busy) setMode('listen'); }
    return;
  }
  if (isEcho(text, voice.spoken) && Date.now() - (state.lastSpokeAt || 0) < 2500) return;

  // 2. a name anywhere switches assistant and passes on the rest of the sentence
  const wake = parseWake(text);
  if (wake) {
    captureUntil = 0;
    emit('speech:wake', wake);
    if (wake.rest) emit('speech:final', { text: wake.rest, persona: wake.persona });
    else speech.capture(8);
    return;
  }
  // 3. no name: only a request inside the capture / follow-up window
  if (speech.capturing) {
    captureUntil = 0;
    emit('speech:final', { text });
    return;
  }
  emit('speech:ignored', text);
}

on('mode', (mode) => { if (mode === 'idle' && speech.capturing) setMode('listen'); });
setInterval(() => {
  if (state.mode === 'listen' && !speech.capturing && !state.busy) { setMode('idle'); sfx.listenStop(); }
}, 400);
