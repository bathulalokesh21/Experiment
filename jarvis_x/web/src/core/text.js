// Pure text helpers: wake words, echo filter, speech chunking, quick voice commands.
// No DOM here, so everything is unit-testable.

export const WAKE = {
  jarvis: ['jarvis', 'jarvus', 'javis', 'jervis', 'jarves', 'travis', 'charvis', 'jarviz', 'darvis', 'garvis', 'jarvi', 'service', 'jarvis\'s'],
  friday: ['friday', 'fri day', 'fryday', 'frida', 'fridays', 'freddy', 'fry day', 'friede'],
  robin: ['robin', 'robyn', 'robbin', 'robing', 'ruben', 'reuben', 'robbing', 'rob in', 'robins', 'robben'],
};
const norm = (s) => s.toLowerCase().replace(/[^a-z0-9' ]+/g, ' ').replace(/\s+/g, ' ').trim();

/** Find an assistant's name in what was heard. Returns {persona, rest, index} or null.
 *  "hey jarvis what's the time" -> {persona:'jarvis', rest:"what's the time"}
 *  Mid-sentence names work too: "...actually friday tell me a joke" -> friday + "tell me a joke". */
export function parseWake(heard) {
  const text = norm(heard);
  let best = null;
  for (const [persona, names] of Object.entries(WAKE)) {
    for (const name of names) {
      const re = new RegExp(`(^|\\s)${name.replace(/ /g, '\\s')}(?=\\s|$)`);
      const m = re.exec(text);
      if (!m) continue;
      const index = m.index + m[1].length;
      // "service" is only a wake word at the very start (it is a real word)
      if (name === 'service' && index > 4) continue;
      // prefer the LAST name spoken: "jarvis... no, friday, do it"
      if (!best || index > best.index) best = { persona, index, len: name.length };
    }
  }
  if (!best) return null;
  let rest = text.slice(best.index + best.len).trim();
  rest = rest.replace(/^(please|can you|could you|hey|um|uh)\s+/, (m0) => (m0.startsWith('can') || m0.startsWith('could') ? m0 : ''));
  return { persona: best.persona, rest, index: best.index };
}

const tokens = (s) => norm(s).split(' ').filter((w) => w.length > 1);

/** Is what the mic heard just the assistant's own voice coming back through the speakers? */
export function isEcho(heard, spoken) {
  const h = tokens(heard);
  if (!h.length || !spoken) return false;
  const pool = new Set(tokens(spoken));
  const hits = h.filter((w) => pool.has(w)).length;
  return hits / h.length >= 0.6;
}

const STOP_RE = /^(stop|wait|hold on|enough|quiet|shut up|pause|cancel that|never mind|nevermind|okay stop|ok stop|stop it|stop talking|that's enough)\b/;
/** Should this utterance interrupt the assistant while it is speaking? */
export function bargeIn(heard, spoken, enabled = true) {
  if (!enabled) return { interrupt: false };
  const text = norm(heard);
  if (!text || isEcho(text, spoken)) return { interrupt: false };
  if (STOP_RE.test(text)) return { interrupt: true, reason: 'stop', stopOnly: text.split(' ').length <= 3 };
  if (parseWake(text)) return { interrupt: true, reason: 'name' };
  if (text.split(' ').length >= 3) return { interrupt: true, reason: 'speech' };
  return { interrupt: false };
}

/** Voice commands handled instantly, without asking the model. */
export function quickCommand(heard, { hasApproval = false, speaking = false } = {}) {
  const text = norm(heard).replace(/^(hey |ok |okay )?(jarvis|friday|robin)\s+/, '');
  if (hasApproval) {
    if (/^(send it|send|approve|approved|yes send it|yes send|go ahead|do it|confirm|yes approve|make the call|call them|install it|yes)$/.test(text)) return { cmd: 'approve' };
    if (/^(cancel|cancel it|don't send|do not send|discard|scrap it|no|no cancel|delete it|don't call|don't install)$/.test(text)) return { cmd: 'cancel' };
  }
  if (STOP_RE.test(text) && text.split(' ').length <= 3) return { cmd: 'stop' };
  if (/^(not now|later|snooze|leave me alone)$/.test(text)) return { cmd: 'snooze' };
  if (/^(house party|house party protocol|party mode)$/.test(text)) return { cmd: 'party' };
  if (/^(clean slate|clean slate protocol|shut down|shutdown|go to sleep)$/.test(text)) return { cmd: 'clean' };
  if (/^(wake up|wake)$/.test(text)) return { cmd: 'wake' };
  if (/^(mute|mute yourself|mute the mic|stop listening)$/.test(text)) return { cmd: 'mute' };
  if (/^(ambient mode|screensaver)$/.test(text)) return { cmd: 'ambient' };
  if (/^(open (the )?tuner|tune my guitar|guitar tuner)$/.test(text)) return { cmd: 'tuner' };
  if (/^(end|stop) (the )?drill$/.test(text)) return { cmd: 'drill_end' };
  return null;
}

/** Turns a token stream into speakable chunks: the first clause as early as possible
 *  (so the voice starts fast), then whole sentences. */
export class Chunker {
  constructor() { this.buf = ''; this.first = true; }
  feed(delta) {
    this.buf += delta;
    const out = [];
    for (;;) {
      const cut = this._cut();
      if (cut < 0) break;
      const piece = this.buf.slice(0, cut).trim();
      this.buf = this.buf.slice(cut);
      if (piece) { out.push(piece); this.first = false; }
    }
    return out;
  }
  _cut() {
    const b = this.buf;
    // sentence end: . ! ? followed by space/newline (not "3.5", not "e.g.")
    const sentence = /[.!?]["')\]]?(\s|\n)/g;
    let m;
    while ((m = sentence.exec(b))) {
      const end = m.index + m[0].length;
      const before = b.slice(0, m.index + 1);
      if (/\b(e\.g|i\.e|mr|mrs|dr|vs|etc|no)\.$/i.test(before)) continue;
      if (/\d\.$/.test(before) && /^\d/.test(b.slice(end))) continue;
      if (before.trim().split(/\s+/).length >= 2 || !this.first) return end;
    }
    const nl = b.indexOf('\n');
    if (nl > 0 && b.slice(0, nl).trim().length > 12) return nl + 1;
    if (this.first) {
      const clause = /[,;:](\s)/.exec(b);
      if (clause && b.slice(0, clause.index).trim().split(/\s+/).length >= 3) return clause.index + clause[0].length;
    }
    if (b.length > 220) {  // a very long sentence: break at the last comma or space
      const comma = b.lastIndexOf(', ', 200);
      return comma > 60 ? comma + 2 : b.lastIndexOf(' ', 200) + 1;
    }
    return -1;
  }
  flush() {
    const piece = this.buf.trim();
    this.buf = '';
    return piece ? [piece] : [];
  }
}

/** What the caption shows for a chunk (markdown marks removed, bullets kept readable). */
export function captionText(chunk) {
  return chunk.replace(/```[\s\S]*?```/g, ' ').replace(/[*_`#>]/g, '').replace(/^\s*[-•]\s+/gm, '· ').replace(/\s+/g, ' ').trim();
}

export function humorLabel(value) {
  return value < 15 ? 'Serious' : value < 40 ? 'Dry wit' : value < 65 ? 'Playful' : value < 85 ? 'Banter' : 'Chaos';
}
export const EFFORT_EXPLAIN = {
  auto: 'Auto: each model decides how hard to think.',
  fast: 'Fast: quickest answers, least thinking.',
  med: 'Med: balanced thinking.',
  deep: 'Deep: slow, careful reasoning for hard questions.',
};
