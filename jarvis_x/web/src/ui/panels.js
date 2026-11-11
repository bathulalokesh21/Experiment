// Left + right column panels. Every panel is always visible; columns scroll.
import { $, $$, el, on, emit, state, persona } from '../core/bus.js';
import { get, post, put, del } from '../core/api.js';
import { ask, switchTo, sayLocal, toast, QUICK, startDrill, endDrill, addLine } from '../core/conversation.js';
import { humorLabel, EFFORT_EXPLAIN } from '../core/text.js';
import { speech } from '../core/speech.js';
import { sfx } from '../fx/sfx.js';

const saveSetting = async (patch) => { const res = await put('/api/settings', patch); if (res.ok) { state.settings = res.settings; emit('settings', res.settings); } };

// ---------------------------------------------------------------- crew, quick asks, style, drill

function renderCrew() {
  $('#crew-list').replaceChildren(...state.personas.map((p) => el('button', {
    class: 'crew' + (p.id === state.persona ? ' on' : ''), 'data-persona': p.id, style: `--pc:${p.colour}`, title: `Switch to ${p.name}`,
    onclick: () => { switchTo(p.id); },
  }, el('span', { class: 'orb' }), el('span', {}, el('span', { class: 'n', text: p.name }), el('div', { class: 'sub', text: p.tagline })),
  el('span', { class: 'ready', 'data-ready': p.id, text: state.ready?.[p.id] ? (state.ready[p.id].ok ? 'ready' : 'offline') : (state.fake ? 'demo' : 'warming') }))));
}
function renderPersona() {
  const p = persona();
  $('#brand-persona').textContent = p.name;
  $('#persona-name').textContent = p.name;
  $('#persona-sub').textContent = p.tagline || '';
  $$('.crew').forEach((b) => b.classList.toggle('on', b.dataset.persona === p.id));
  renderStyle();
}
function renderStyle() {
  const s = state.settings;
  $$('#effort-seg button').forEach((b) => b.classList.toggle('on', b.dataset.effort === s.effort));
  $('#effort-explain').textContent = EFFORT_EXPLAIN[s.effort] + (persona().model === 'haiku' ? ' (ROBIN runs on Haiku, which ignores effort.)' : '');
  $('#humor').value = s.humor;
  $('#humor-label').textContent = humorLabel(s.humor);
  $('#interrupt-toggle').checked = s.interrupt !== false;
  $('#sound-toggle').checked = s.sound !== false;
  $('#proactive-toggle').checked = s.proactive !== false;
  $('#routing-toggle').checked = !!s.smart_routing;
  $('#quiet-start').value = s.quiet_start; $('#quiet-end').value = s.quiet_end;
  $('#sens').value = s.gesture_sensitivity || 1;
}
function initLeft() {
  renderCrew(); renderPersona();
  on('persona', renderPersona);
  on('srv:crew_ready', (ev) => { state.ready = state.ready || {}; state.ready[ev.persona] = ev; const n = $(`[data-ready="${ev.persona}"]`); if (n) n.textContent = ev.ok ? 'ready' : 'offline'; if (!ev.ok) toast(ev.message); });
  $('#quick-list').addEventListener('click', (e) => { const b = e.target.closest('[data-quick]'); if (b && QUICK[b.dataset.quick]) QUICK[b.dataset.quick](); });
  $('#effort-seg').addEventListener('click', (e) => { const b = e.target.closest('[data-effort]'); if (b) saveSetting({ effort: b.dataset.effort }).then(renderStyle); });
  $('#humor').addEventListener('input', (e) => { $('#humor-label').textContent = humorLabel(+e.target.value); emit('humor', +e.target.value); });
  $('#humor').addEventListener('change', (e) => saveSetting({ humor: +e.target.value }));
  for (const [id, key] of [['interrupt-toggle', 'interrupt'], ['sound-toggle', 'sound'], ['proactive-toggle', 'proactive'], ['routing-toggle', 'smart_routing']]) {
    $('#' + id).addEventListener('change', (e) => saveSetting({ [key]: e.target.checked }));
  }
  $('#quiet-start').addEventListener('change', (e) => saveSetting({ quiet_start: e.target.value }));
  $('#quiet-end').addEventListener('change', (e) => saveSetting({ quiet_end: e.target.value }));
  $$('[data-drill]').forEach((b) => b.addEventListener('click', () => startDrill(b.dataset.drill)));
  $('#drill-end').addEventListener('click', endDrill);
  on('drill', (kind) => { $('#drill-status').textContent = kind ? `${kind.toUpperCase()} drill running. I listen longer after each question.` : 'No drill running.'; $$('[data-drill]').forEach((b) => b.classList.toggle('on', b.dataset.drill === kind)); });
  on('command', (cmd) => { if (cmd === 'drill_end') endDrill(); });
}

// ---------------------------------------------------------------- routines, daily panels

async function loadRoutines() {
  const res = await get('/api/routines');
  if (!res.ok) return;
  $('#routine-list').replaceChildren(...res.routines.map((r) => el('div', { class: 'item' },
    el('span', { class: 'txt', title: r.steps.map((s) => s.say || s.ask || s.tool || s.ui).join(' → '), text: r.name }),
    el('span', { class: 'when', text: `“${r.trigger}”` }),
    el('button', { text: '▶', title: 'Run', onclick: async () => { const out = await post('/api/routines/run', { name: r.name }); if (out.ok && out.matched) { const { runSteps } = await import('../core/conversation.js'); runSteps(out.steps, out.name); } } }),
    r.builtin ? null : el('button', { text: '✕', title: 'Delete', onclick: async () => { await del(`/api/routines/${encodeURIComponent(r.name)}`); loadRoutines(); } }))));
}

let daily = null;
export async function loadDaily() {
  const res = await get('/api/daily');
  if (!res.ok) return;
  daily = res;
  const c = res.guitar.chord, g = res.guitar.stats;
  $('#chord-name').textContent = c.name; $('#chord-frets').textContent = c.frets; $('#chord-tip').textContent = c.tip;
  $('#guitar-stats').textContent = g.sessions ? `${Math.round(g.week_minutes)} min this week · ${g.streak}-day streak` : 'No practice logged yet.';
  const cc = res.comic.counts;
  $('#comic-summary').textContent = `${cc.characters} characters · ${cc.world} world · ${cc.scripts} scripts`;
  $('#cards-summary').textContent = res.flashcards.total ? `${res.flashcards.due} due of ${res.flashcards.total}` : 'no decks yet';
  $('#journal-summary').textContent = res.journal.count ? `${res.journal.count} entries` : 'empty';
  $('#learn-today').textContent = 'Today: ' + res.learn;
  renderExpenses(res.expenses);
  renderPlugins(res.plugins);
  renderLights(res.lights, res.scenes);
}
function renderExpenses(s) {
  $('#exp-total').textContent = `₹${Math.round(s.total).toLocaleString('en-IN')}`;
  $('#exp-today').textContent = `this month · ₹${Math.round(s.today)} today`;
  const max = Math.max(1, ...Object.values(s.categories));
  $('#exp-bars').replaceChildren(...Object.entries(s.categories).slice(0, 5).map(([cat, v]) => el('div', { class: 'bar' },
    el('span', { text: cat }), el('i', { style: `width:${Math.max(4, (v / max) * 100)}%` }), el('span', { text: `₹${Math.round(v)}` }))));
}
function renderPlugins(items) {
  $('#plugin-list').replaceChildren(...(items.length ? items.map((p) => el('div', { class: 'item' },
    el('span', { class: 'txt', title: p.summary, text: p.name }),
    el('button', { text: p.enabled ? 'on' : 'off', class: p.enabled ? 'on' : '', onclick: async () => { await post(`/api/plugins/${p.name}/toggle`, { enabled: !p.enabled }); loadDaily(); } }),
    el('button', { text: '✕', title: 'Remove', onclick: async () => { await del(`/api/plugins/${p.name}`); loadDaily(); } })))
    : [el('div', { class: 'sub', text: 'None yet. Say “I wish you could …”.' })]));
}
let light = null;
function renderLights(devices, scenes) {
  light = devices[0] || null;
  $('#home-empty').hidden = !!light; $('#home-controls').hidden = !light;
  if (!light) return;
  $('#light-name').textContent = `${light.name} (${light.driver})`;
  const on_ = !!light.state.on;
  $('#light-toggle').textContent = on_ ? 'On' : 'Off'; $('#light-toggle').classList.toggle('on', on_);
  $('#light-bright').value = light.state.brightness || 100; $('#light-kelvin').value = light.state.kelvin || 4000;
  if (!$('#light-scenes').children.length) $('#light-scenes').replaceChildren(...scenes.map((s) => el('button', { text: s, onclick: () => setLight({ scene: s }) })));
}
async function setLight(change) {
  const res = await post('/api/lights', change);
  if (!res.ok) toast(res.message);
}

function initDaily() {
  loadRoutines(); loadDaily();
  on('srv:routines_changed', loadRoutines);
  for (const ev of ['srv:guitar', 'srv:comic', 'srv:flashcards', 'srv:plugins_changed', 'srv:approval_done']) on(ev, loadDaily);
  on('srv:expenses', (ev) => renderExpenses(ev.summary));
  on('srv:lights', (ev) => renderLights(ev.devices, daily ? daily.scenes : []));
  $('#exp-form').addEventListener('submit', async (e) => { e.preventDefault(); const input = $('#exp-input'); if (!input.value.trim()) return; const res = await post('/api/expenses', { text: input.value }); if (res.ok) { input.value = ''; renderExpenses(res.summary); sfx.tick(); } else toast(res.message); });
  $('#light-toggle').addEventListener('click', () => setLight({ on: !(light && light.state.on) }));
  $('#light-bright').addEventListener('change', (e) => setLight({ brightness: +e.target.value }));
  $('#light-kelvin').addEventListener('change', (e) => setLight({ kelvin: +e.target.value }));
  $('#cards-quiz').addEventListener('click', () => ask('Quiz me on my due flashcards, one at a time.', { raw: true, display: 'Quiz me' }));
  $('#journal-add').addEventListener('click', () => { const input = $('#talk-input'); input.value = 'Journal: today I learned '; input.focus(); });
  $('#comic-open').addEventListener('click', () => emit('ui:action', { action: 'comic' }));
}

// ---------------------------------------------------------------- memory, focus, tasks, mic, companion

async function loadMemory() {
  const [s, t] = await Promise.all([get('/api/state'), get('/api/transcripts')]);
  if (s.ok) { $('#mem-facts').textContent = s.memory.facts; $('#mem-files').textContent = s.knowledge; }
  if (t.ok) $('#mem-days').textContent = (t.days || []).length;
}

const focus = { total: 25 * 60, left: 25 * 60, running: false, timer: null };
function renderFocus() {
  const m = Math.floor(focus.left / 60), s = focus.left % 60;
  $('#focus-time').textContent = `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  $('#focus-start').textContent = focus.running ? 'Pause' : (focus.left < focus.total ? 'Resume' : 'Start');
  $$('#focus-seg button').forEach((b) => b.classList.toggle('on', +b.dataset.focus * 60 === focus.total));
}
export function focusStart(minutes, announce = true) {
  if (minutes) { focus.total = focus.left = Math.max(1, Math.round(minutes * 60)); }
  if (focus.running) return;
  focus.running = true;
  if (announce) sayLocal(`Focus timer started. ${Math.round(focus.left / 60)} minutes, ${persona().address}.`, undefined, { log: false });
  focus.timer = setInterval(() => {
    focus.left -= 1;
    if (focus.left <= 0) {
      focusStop(false);
      post('/api/focus/log', { minutes: focus.total / 60 });
      sfx.reminder();
      sayLocal(`Focus session complete, ${persona().address}. ${Math.round(focus.total / 60)} minutes done. Take a break.`);
      focus.left = focus.total;
    }
    renderFocus();
  }, 1000);
  renderFocus();
}
export function focusStop(announce = true) {
  if (!focus.running) return;
  focus.running = false; clearInterval(focus.timer);
  if (announce) sayLocal('Focus timer paused.', undefined, { log: false });
  renderFocus();
}
function initFocus() {
  renderFocus();
  $('#focus-seg').addEventListener('click', (e) => { const b = e.target.closest('[data-focus]'); if (!b) return; focusStop(false); focus.total = focus.left = +b.dataset.focus * 60; renderFocus(); });
  $('#focus-start').addEventListener('click', () => (focus.running ? focusStop() : focusStart()));
  $('#focus-reset').addEventListener('click', () => { focusStop(false); focus.left = focus.total; renderFocus(); });
}

async function loadTasks() {
  const res = await get('/api/tasks');
  if (!res.ok) return;
  $('#reminder-list').replaceChildren(...res.reminders.map((r) => el('div', { class: 'item' },
    el('span', { text: r.repeat ? '🔁' : '⏰' }), el('span', { class: 'txt', title: r.text, text: r.text }), el('span', { class: 'when', text: r.when.replace('today at ', '') }),
    el('button', { text: '✕', title: 'Cancel reminder', onclick: async () => { await del(`/api/reminders/${r.id}`); loadTasks(); } }))));
  $('#task-list').replaceChildren(...res.tasks.map((t) => el('div', { class: 'item' },
    el('button', { text: '○', title: 'Mark done', onclick: async () => { await post(`/api/tasks/${t.id}/done`); sfx.tick(); loadTasks(); } }),
    el('span', { class: 'txt', title: t.text, text: t.text }),
    el('button', { text: '✕', title: 'Remove', onclick: async () => { await del(`/api/tasks/${t.id}`); loadTasks(); } }))));
  if (!res.reminders.length && !res.tasks.length) $('#task-list').replaceChildren(el('div', { class: 'sub', text: 'Nothing pending. Enjoy it.' }));
}
function initTasks() {
  loadTasks();
  on('srv:tasks_changed', loadTasks);
  $('#task-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const input = $('#task-input'); const text = input.value.trim();
    if (!text) return;
    const reminder = /^remind( me)?\b/i.test(text) || /\b(in \d+ (min|hour)|at \d|tomorrow|tonight|every )/i.test(text);
    const res = reminder ? await post('/api/reminders', { text: text.replace(/^remind( me)?( to)?\s*/i, ''), when: text }) : await post('/api/tasks', { text });
    if (res.ok) { input.value = ''; loadTasks(); } else toast(res.message);
  });
}

function initMic() {
  on('speech:status', (s) => { $('#mic-state').textContent = { on: 'listening for a name', off: 'off', blocked: 'blocked', unsupported: 'typing only', offline: 'no internet' }[s] || s;
    if (s === 'unsupported') $('#mic-heard').textContent = 'Voice recognition needs Edge or Chrome.';
    if (s === 'blocked') $('#mic-heard').textContent = 'Allow the microphone from the lock icon in the address bar.'; });
  on('mic:error', (msg) => { $('#mic-heard').textContent = msg; toast(msg); });
  on('mode', (mode) => { $('#state-tag').textContent = mode; $('#mic-btn').classList.toggle('live', mode === 'listen'); });
  $('#mic-mute').addEventListener('click', () => setMuted(!state.muted));
  on('command', (cmd) => { if (cmd === 'mute') setMuted(true); });
}
export function setMuted(muted) {
  state.muted = muted;
  $('#mic-mute').textContent = muted ? 'Unmute' : 'Mute'; $('#mic-mute').classList.toggle('on', muted);
  $('#mic-btn').classList.toggle('muted', muted);
  if (muted) speech.cancelCapture();
  $('#mic-state').textContent = muted ? 'muted' : (speech.supported ? 'listening for a name' : 'typing only');
  toast(muted ? 'Microphone muted' : 'Microphone on');
}

async function loadCompanion() {
  const res = await get('/api/companion');
  if (!res.ok) return;
  $('#companion-toggle').checked = res.enabled;
  $('#companion-info').textContent = !res.enabled ? 'Off. Nothing is served outside this laptop.'
    : res.listening_lan ? `On your phone (same Wi-Fi): http://${res.ip}:${res.port}/m   PIN ${res.pin}`
      : 'Switched on. Restart JARVIS (Ctrl+C, then python run.py) so it can listen on your Wi-Fi.';
}
function initCompanion() {
  loadCompanion();
  $('#companion-toggle').addEventListener('change', async (e) => { await saveSetting({ phone_companion: e.target.checked }); loadCompanion(); });
}

export function initPanels() {
  initLeft(); initDaily(); initFocus(); initTasks(); initMic(); initCompanion(); loadMemory();
  on('memory:changed', loadMemory);
  on('settings', renderStyle);
  on('srv:proactive', ({ item }) => {
    const card = el('div', { class: 'pro-card', 'data-id': item.id }, el('span', { class: 'txt', text: item.text }),
      el('div', { class: 'acts' }, el('button', { class: 'mini', text: 'Not now', onclick: async () => { await post('/api/proactive/snooze', { minutes: 60 }); card.remove(); } }),
        el('button', { class: 'mini ghost', text: 'Dismiss', onclick: () => card.remove() })));
    $('#proactive-zone').append(card);
    if (!state.busy && !state.speaking && !state.asleep) sayLocal(item.text);
  });
  on('command', async (cmd) => { if (cmd === 'snooze') { await post('/api/proactive/snooze', { minutes: 60 }); $('#proactive-zone').replaceChildren(); toast('Okay. Quiet for an hour.'); } });
}
