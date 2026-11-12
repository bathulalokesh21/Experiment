// The conversation engine: ask -> stream -> speak (first clause ASAP) -> captions -> follow-up.
import { emit, on, state, setMode, persona, $, el } from './bus.js';
import { chatStream, post, put } from './api.js';
import { voice, randomAck } from './audio.js';
import { Chunker, captionText, quickCommand } from './text.js';
import { speech } from './speech.js';
import { sfx } from '../fx/sfx.js';

let turn = 0;
let abort = null;
let debateOn = false;
let captionTimer = null;

// ---------------------------------------------------------------- captions + history

function showCaption(who, text, { user = false, duration = 0 } = {}) {
  const speaker = $('#caption-speaker');
  const box = $('#caption-text');
  clearInterval(captionTimer);
  speaker.textContent = user ? 'YOU' : who.toUpperCase();
  box.classList.toggle('user', user);
  box.textContent = '';
  const words = text.split(/\s+/).filter(Boolean);
  const spans = words.map((w) => { const s = el('span', { class: 'w', text: w + ' ' }); box.append(s); return s; });
  if (user || !duration) { spans.forEach((s) => s.classList.add('on')); return; }
  // word-synced reveal: each word gets a share of the clip proportional to its length
  const total = words.reduce((n, w) => n + w.length + 2, 0);
  const t0 = performance.now();
  let shown = 0;
  const marks = [];
  let acc = 0;
  for (const w of words) { marks.push((acc / total) * duration * 1000); acc += w.length + 2; }
  captionTimer = setInterval(() => {
    const t = performance.now() - t0;
    while (shown < spans.length && marks[shown] <= t) spans[shown++].classList.add('on');
    if (shown >= spans.length) clearInterval(captionTimer);
  }, 30);
}

export function addLine(who, text, id = '') {
  if (!text) return;
  const p = who === 'you' ? null : persona(id || who);
  const line = el('div', { class: 'line', style: p ? `--pc:${p.colour}` : '' },
    el('span', { class: 'who', text: who === 'you' ? 'YOU' : p.name }), document.createTextNode(text));
  const convo = $('#convo');
  convo.append(line);
  while (convo.children.length > 60) convo.firstChild.remove();
  convo.scrollTop = convo.scrollHeight;
}

export function chip(text) {
  if (!text) return;
  const node = el('div', { class: 'chip', text });
  $('#holo-chips').append(node);
  sfx.chip();
  setTimeout(() => node.remove(), 3700);
}
export function toast(text) {
  const node = el('div', { class: 'toast', text });
  $('#toasts').append(node);
  setTimeout(() => node.remove(), 4300);
}

on('voice:chunk', (item) => {
  state.speaking = true;
  state.lastSpokeAt = Date.now();
  setMode('speak');
  if (item.caption) showCaption(persona(item.personaId).name, captionText(item.caption), { duration: item.duration });
  if (item.caption && state.timings.t0 && !state.timings.firstAudio) {
    state.timings.firstAudio = Math.round(performance.now() - state.timings.t0);
    state.timings.last = { persona: item.personaId, firstAudio: state.timings.firstAudio, firstToken: state.timings.firstToken };
    emit('timing', state.timings.last);
  }
});

async function settle(my) {
  await voice.drain();
  if (my !== undefined && my !== turn) return false;
  state.speaking = false;
  state.lastSpokeAt = Date.now();
  if (!state.busy) setMode(speech.capturing ? 'listen' : 'idle');
  return true;
}

// ---------------------------------------------------------------- core actions

export function switchTo(id, { silent = false } = {}) {
  if (!state.personas.some((p) => p.id === id) || id === state.persona) return false;
  const from = state.persona;
  state.persona = id;
  document.body.dataset.persona = id;
  emit('persona', { id, from });
  if (!silent) sfx.morph();
  put('/api/settings', { active: id });
  return true;
}

export function stop(internal = false) {
  turn++;
  debateOn = internal ? debateOn : false;
  if (abort) { abort.abort(); abort = null; }
  const wasBusy = state.busy || state.speaking;
  voice.stop();
  clearInterval(captionTimer);
  state.busy = false;
  state.speaking = false;
  if (wasBusy) post('/api/stop', { persona: state.persona });
  if (!internal) { setMode('idle'); emit('stopped'); }
}

/** Speak a line without the model (reminders, greetings, results of approvals). */
export async function sayLocal(text, id = state.persona, { log = true, cache = false } = {}) {
  if (!text) return;
  if (log) { addLine(id, text); post('/api/log', { who: id, persona: id, text }); }
  const my = turn;
  voice.say(id, text, { cache });
  await settle(my);
}

/** Send a request to the crew. Resolves with the full reply, or null if it was cancelled. */
export async function ask(text, opts = {}) {
  text = (text || '').trim();
  if (!text) return null;
  const id = opts.persona || state.persona;
  if (id !== state.persona) switchTo(id);

  if (!opts.raw) {
    const quick = quickCommand(text, { hasApproval: state.approvals.length > 0, speaking: state.speaking });
    if (quick) { emit('command', quick.cmd); return null; }
    state.busy = true;   // from this moment a request is in flight (prevents double handling)
    const routine = await post('/api/routines/run', { utterance: text });
    if (routine.ok && routine.matched) {
      state.busy = false;
      addLine('you', text);
      await runSteps(routine.steps || [], routine.name);
      return null;
    }
    if (/^when i say\b/i.test(text)) text += '\n(Save this as a routine with routine_save.)';
  }

  stop(true);
  const my = ++turn;
  state.busy = true;
  state.currentReply = '';
  state.timings = { t0: performance.now() };
  setMode('think');
  if (opts.display !== null) {
    addLine('you', opts.display || text);
    showCaption('you', opts.display || text, { user: true });
  }
  emit('ask', { id, text });

  const chunker = new Chunker();
  let full = '';
  let gotText = false;
  let checkpoint = null;
  let errorMessage = '';
  const speakChunk = (piece) => { if (/[A-Za-z0-9]/.test(piece)) voice.say(id, piece); };
  // instant acknowledgement if the first words are slow
  const ackTimer = setTimeout(() => {
    if (my === turn && !gotText) { const a = randomAck(id); if (a) voice.say(id, a, { cache: true, caption: '' }); }
  }, 1300);

  abort = new AbortController();
  const s = state.settings;
  await chatStream({
    persona: id, text, effort: opts.effort || s.effort, humor: opts.humor ?? s.humor, no_learn: !!opts.noLearn,
    context: { people: state.people, mode: opts.mode || (state.drill ? 'drill' : ''), smart_routing: !!s.smart_routing },
  }, (ev) => {
    if (my !== turn) return;
    if (ev.type === 'delta') {
      gotText = true;
      full += ev.text;
      state.currentReply = full;
      chunker.feed(ev.text).forEach(speakChunk);
    } else if (ev.type === 'chip') chip(ev.text);
    else if (ev.type === 'timing') state.timings.firstToken = ev.first_token_ms;
    else if (ev.type === 'checkpoint') checkpoint = ev;
    else if (ev.type === 'error') errorMessage = ev.message;
    else if (ev.type === 'done') { if (!full && ev.text) { full = ev.text; chunker.feed(full).forEach(speakChunk); } chunker.flush().forEach(speakChunk); }
  }, abort.signal);
  clearTimeout(ackTimer);
  if (my !== turn) return null;

  if (errorMessage) {
    sfx.error();
    toast(errorMessage);
    if (!full) { full = errorMessage; voice.say(id, errorMessage); }
  }
  addLine(id, full);
  if (!(await settle(my))) return null;   // stays "busy" until the voice has finished, so nothing talks over it
  state.busy = false;
  if (checkpoint) { toast(`Power ${checkpoint.value}%`); await sayLocal(checkpoint.text, id); if (my !== turn) return null; }
  setMode('idle');
  speech.followUp();
  emit('answer', { id, text: full });
  return full;
}

/** Run the dashboard side of a routine: say / ask / ui steps in order. */
export async function runSteps(steps, name = '') {
  if (name) chip(`Routine: ${name}`);
  for (const step of steps) {
    if (step.say) await sayLocal(step.say);
    else if (step.ask) await ask(step.ask, { raw: true, display: null });
    else if (step.ui) emit('ui:action', { action: step.ui, value: step.value || '' });
  }
}

// ---------------------------------------------------------------- modes

const DEBATE_TOPICS = ['Is a hot dog a sandwich?', 'Electric guitar or acoustic first?', 'Consulting or product management for a tech-anchored manager?',
  'Subbed or dubbed anime?', 'Will AI agents replace dashboards?', 'Is Pink Floyd better than Audioslave?'];

export async function debate(topic) {
  topic = (topic || '').trim() || DEBATE_TOPICS[Math.floor(Math.random() * DEBATE_TOPICS.length)];
  stop();
  debateOn = true;
  chip('Crew debate · Esc to cancel');
  const said = [];
  const rounds = [
    ['jarvis', 'Open the debate with your position in two sentences.'],
    ['friday', 'React to JARVIS and give your own position in two sentences.'],
    ['robin', 'React to both of them and give your own position in two sentences.'],
    ['jarvis', 'Give the final verdict in two sentences, acknowledging the best point each of them made.'],
  ];
  for (let i = 0; i < rounds.length; i++) {
    if (!debateOn) break;
    const [id, instruction] = rounds[i];
    const prompt = `Crew debate on: "${topic}".\n${said.length ? 'So far:\n' + said.join('\n') + '\n' : ''}${instruction}`;
    const reply = await ask(prompt, { persona: id, raw: true, mode: 'debate', noLearn: true, display: i === 0 ? `Crew debate: ${topic}` : null });
    if (reply == null || !debateOn) break;
    said.push(`${persona(id).name}: ${reply}`);
  }
  debateOn = false;
  emit('debate:end', said);
  return said;
}

export const roast = () => ask('Roast me. Rules: be kind underneath, punch at my habits and choices (guitar, MBA, consulting slides, anime), never at looks, family, health or anything genuinely hurtful. Three lines, then one sincere compliment.',
  { raw: true, humor: 95, mode: 'roast', noLearn: true, display: 'Roast me.' });

const DRILLS = {
  cv: 'a CV grill: search my files for my CV and grill me on specific lines of it',
  guesstimate: 'a guesstimate drill with an India-flavoured market-sizing question',
  case: 'a consulting case drill (profitability, market entry or operations)',
  hr: 'an HR interview drill (behavioural questions; expect STAR answers)',
};
export function startDrill(kind) {
  state.drill = kind;
  emit('drill', kind);
  return ask(`Start ${DRILLS[kind]}. Ask ONE question at a time and wait for my answer. After each answer give a score out of 10 with one line of feedback, log it with log_drill, then ask the next question.`,
    { raw: true, mode: 'drill', display: `Start ${kind} drill` });
}
export function endDrill() {
  if (!state.drill) return null;
  state.drill = null;
  emit('drill', null);
  return ask('End the drill. Check drill_history and tell me in two sentences how I did and what to work on.', { raw: true, display: 'End drill' });
}

export const QUICK = {
  brief: () => ask('Give me my morning brief.', { raw: true, display: 'Brief my day' }),
  headlines: () => ask('What are the headlines that matter to me right now? Three, briefly.', { raw: true, display: 'Headlines' }),
  weather: () => ask("What's the weather, and will it rain?", { raw: true, display: 'Weather' }),
  guesstimate: () => ask('Give me one quick guesstimate question, then walk me through a crisp approach after I try.', { raw: true, display: 'Guesstimate' }),
  debate: () => debate($('#talk-input').value),
  roast,
  party: () => emit('ui:action', { action: 'house_party' }),
  clean: () => emit('ui:action', { action: 'clean_slate' }),
  recap: () => ask('How was my day? Use day_recap.', { raw: true, display: 'How was my day?' }),
  screen: () => ask("What's on my screen right now? Take a look and explain it briefly.", { raw: true, display: "What's on my screen?" }),
  clipboard: () => ask('Summarise what I copied to the clipboard.', { raw: true, display: 'Summarise clipboard' }),
  sketch: () => emit('ui:action', { action: 'sketch' }),
};

// ---------------------------------------------------------------- wiring

on('speech:wake', ({ persona: id }) => {
  const changed = switchTo(id);
  if (!changed) sfx.wake(id);
  if (state.speaking || state.busy) stop();
  setMode('notice');
  setTimeout(() => { if (state.mode === 'notice') setMode(speech.capturing ? 'listen' : 'idle'); }, 700);
  emit('notice', 'wake');
});
on('speech:final', ({ text, persona: id }) => ask(text, { persona: id }));
on('speech:interim', (text) => { if (!state.speaking) showCaption('you', text, { user: true }); });
on('speech:barge', () => { stop(); chip('Listening'); });
on('srv:chip', (ev) => { if (!state.busy) chip(ev.text); });
on('srv:memory', (ev) => { chip(ev.text.length > 70 ? ev.text.slice(0, 68) + '…' : ev.text); emit('memory:changed'); });
on('srv:reminder', async ({ item }) => {
  sfx.reminder();
  toast(`Reminder: ${item.text}`);
  const late = item.late_minutes > 5 ? ' This was due earlier while I was offline.' : '';
  if (!state.busy && !state.speaking) await sayLocal(`Reminder, ${persona().address}: ${item.text}.${late}`);
  else addLine(state.persona, `Reminder: ${item.text}`);
});
on('srv:routine', ({ name, steps }) => {
  // the crew started a routine mid-answer: run the dashboard steps once it has finished speaking
  if (!state.busy && !state.speaking) return runSteps(steps, name);
  const off = on('answer', () => { off(); runSteps(steps, name); });
});
