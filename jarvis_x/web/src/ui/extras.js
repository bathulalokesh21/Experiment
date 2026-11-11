// Memory panel, conversation search, comic bible, command palette, debug overlay,
// drag-and-drop files, and the always-on-top voice orb.
import { $, $$, el, on, emit, state, persona } from '../core/bus.js';
import { get, post, put, del, upload } from '../core/api.js';
import { ask, toast, QUICK, switchTo, stop, startDrill, endDrill } from '../core/conversation.js';
import { openOverlay, closeOverlay, h4, para } from './overlay.js';
import { features } from '../core/audio.js';

// ---------------------------------------------------------------- memory panel
export async function openMemory() {
  const list = el('div', {});
  const search = el('input', { placeholder: 'Search what I know about you…', style: 'width:100%', 'aria-label': 'Search memory' });
  const add = el('input', { placeholder: 'Teach me a fact…', class: 'grow', 'aria-label': 'New fact' });
  const files = el('div', { class: 'sub' });
  async function load() {
    const res = await get(`/api/memory/facts?q=${encodeURIComponent(search.value)}`);
    if (!res.ok) return;
    files.textContent = res.knowledge.length ? 'Files: ' + res.knowledge.join(', ') : 'No files yet. Drop a PDF, DOCX, PPTX, CSV or text file anywhere on the dashboard.';
    list.replaceChildren(...(res.facts.length ? res.facts.map((f) => {
      const input = el('input', { value: f.text, 'aria-label': 'Fact' });
      return el('div', { class: 'fact', 'data-fact': f.id }, el('span', { class: 'pill', text: f.category }), input,
        el('button', { class: 'mini', text: 'Save', onclick: async () => { const r = await put(`/api/memory/facts/${f.id}`, { text: input.value }); toast(r.ok ? 'Updated.' : r.message); } }),
        el('button', { class: 'mini ghost', text: 'Forget', onclick: async () => { await del(`/api/memory/facts/${f.id}`); load(); emit('memory:changed'); } }));
    }) : [para(search.value ? 'Nothing matches.' : 'Nothing learned yet. Tell me things about you and I will remember.', 'sub')]));
  }
  search.addEventListener('input', load);
  const form = el('form', { class: 'row' }, add, el('button', { class: 'mini', text: 'Remember' }));
  form.addEventListener('submit', async (e) => { e.preventDefault(); if (!add.value.trim()) return; const r = await post('/api/memory/facts', { text: add.value }); if (r.ok) { add.value = ''; load(); emit('memory:changed'); } else toast(r.message); });
  openOverlay('Memory', [search, form, list, h4('Your files'), files,
    para('I never store health details, account numbers, passwords or OTPs. Say “forget that” or “forget everything about X” any time.', 'sub')]);
  load();
}

export async function openHistory() {
  const list = el('div', {});
  const search = el('input', { placeholder: 'Search past conversations (e.g. cloud, guitar, Deloitte)…', style: 'width:100%', 'aria-label': 'Search conversations' });
  async function load() {
    const res = await get(`/api/transcripts?q=${encodeURIComponent(search.value)}`);
    if (!res.ok) return;
    list.replaceChildren(...(res.items.length ? res.items.slice(-80).map((i) => el('div', { class: 'fact' },
      el('span', { class: 'pill', text: `${i.day ? i.day.slice(5) + ' ' : ''}${i.t.slice(0, 5)}` }), el('b', { text: (i.who === 'nikesh' ? 'You' : (i.persona || i.who).toUpperCase()) + ': ' }),
      el('span', { class: 'grow', text: i.text }))) : [para('Nothing found.', 'sub')]));
  }
  search.addEventListener('input', load);
  openOverlay('Conversation history', [search, list]);
  load();
}

export async function openComic() {
  const res = await get('/api/comic');
  if (!res.ok) return;
  const b = res.bible;
  const body = [para(b.title, 'strong')];
  for (const sec of ['world', 'characters', 'timeline', 'scripts', 'ideas']) {
    body.push(h4(sec));
    body.push(...(b[sec].length ? b[sec].map((e) => el('div', { class: 'fact' }, el('b', { text: e.title + ': ' }), el('span', { class: 'grow', text: e.text }))) : [para('Empty.', 'sub')]));
  }
  body.push(para('Tell any assistant “add to my comic: …” and it will keep the canon consistent.', 'sub'));
  openOverlay('Comic studio · story bible', body);
}

// ---------------------------------------------------------------- command palette
function commands() {
  const act = (action, value) => () => emit('ui:action', { action, value });
  const list = [
    ...state.personas.map((p) => ({ name: `Switch to ${p.name}`, run: () => switchTo(p.id) })),
    { name: 'Brief my day', run: QUICK.brief }, { name: 'Headlines', run: QUICK.headlines }, { name: 'Weather', run: QUICK.weather },
    { name: 'How was my day? (recap)', run: QUICK.recap }, { name: 'Crew debate', run: QUICK.debate }, { name: 'Roast me', run: QUICK.roast },
    { name: 'What is on my screen?', run: QUICK.screen }, { name: 'Summarise clipboard', run: QUICK.clipboard }, { name: 'Sketch to life (camera snapshot)', run: QUICK.sketch },
    { name: 'House Party Protocol', run: act('house_party') }, { name: 'Clean Slate Protocol', run: act('clean_slate') }, { name: 'Ambient mode', run: act('ambient') },
    { name: 'Open memory panel', run: openMemory }, { name: 'Search conversation history', run: openHistory }, { name: 'Open comic story bible', run: openComic },
    { name: 'Guitar tuner', run: act('tuner') }, { name: 'Metronome start', run: act('metronome_start') }, { name: 'Metronome stop', run: act('metronome_stop') },
    { name: 'Focus 25 minutes', run: act('focus_start', '25') }, { name: 'Focus 50 minutes', run: act('focus_start', '50') }, { name: 'Focus 90 minutes', run: act('focus_start', '90') }, { name: 'Focus stop', run: act('focus_stop') },
    { name: 'Camera on', run: act('camera_on') }, { name: 'Camera off', run: act('camera_off') }, { name: 'Pop out voice orb', run: act('orb') },
    { name: 'Drill: CV grill', run: () => startDrill('cv') }, { name: 'Drill: guesstimate', run: () => startDrill('guesstimate') }, { name: 'Drill: case', run: () => startDrill('case') },
    { name: 'Drill: HR', run: () => startDrill('hr') }, { name: 'End drill', run: endDrill },
    { name: 'Media: play / pause', run: () => post('/api/tool', { name: 'media_control', args: { action: 'play_pause' } }) },
    { name: 'Media: next track', run: () => post('/api/tool', { name: 'media_control', args: { action: 'next' } }) },
    { name: 'Volume up', run: () => post('/api/tool', { name: 'volume', args: { action: 'up' } }) }, { name: 'Volume down', run: () => post('/api/tool', { name: 'volume', args: { action: 'down' } }) },
    { name: 'Lights on', run: () => post('/api/tool', { name: 'light_on' }) }, { name: 'Lights off', run: () => post('/api/tool', { name: 'light_off' }) },
    { name: 'Stop talking', run: stop }, { name: 'Debug overlay', run: toggleDebug },
  ];
  return list;
}
let sel = 0, shown = [];
function renderPalette() {
  const q = $('#palette-input').value.trim().toLowerCase();
  shown = commands().filter((c) => q.split(/\s+/).every((w) => c.name.toLowerCase().includes(w)));
  if (q) shown.push({ name: `Ask ${persona().name}: “${$('#palette-input').value.trim()}”`, run: () => ask($('#palette-input').value.trim()) });
  sel = Math.min(sel, Math.max(0, shown.length - 1));
  $('#palette-list').replaceChildren(...shown.map((c, i) => el('li', { class: i === sel ? 'sel' : '', text: c.name, onclick: () => runPalette(i) })));
}
function runPalette(i) { const cmd = shown[i]; closePalette(); if (cmd) cmd.run(); }
export function openPalette() { $('#palette').hidden = false; $('#palette-input').value = ''; sel = 0; renderPalette(); $('#palette-input').focus(); }
export function closePalette() { if ($('#palette').hidden) return false; $('#palette').hidden = true; return true; }

// ---------------------------------------------------------------- debug overlay (Ctrl+Shift+D)
let debugTimer = null, holo = null;
export const bindHologram = (h) => { holo = h; };
const TARGET = { robin: 1500, friday: 2500, jarvis: 3500 };
const timingLog = [];
on('timing', (t) => { timingLog.push(t); if (timingLog.length > 5) timingLog.shift(); });
export function toggleDebug() {
  const box = $('#debug');
  box.hidden = !box.hidden;
  clearInterval(debugTimer);
  if (box.hidden) return;
  debugTimer = setInterval(() => {
    const h = holo ? holo.stats() : {};
    const f = features();
    const lat = timingLog.map((t) => `  ${t.persona.padEnd(7)} first token ${String(t.firstToken ?? '-').padStart(5)} ms · first audio ${String(t.firstAudio).padStart(5)} ms ${t.firstAudio <= TARGET[t.persona] ? '✓' : '✗ target ' + TARGET[t.persona]}`).join('\n') || '  (ask something)';
    box.textContent = `hologram  ${h.mode} · ${h.fps} fps · ${h.particles} particles · q ${h.quality}\nstate     ${state.mode} · form ${h.form} · morph ${h.morph}\naudio     voice ${f.out.level.toFixed(2)} onset ${f.out.onset.toFixed(2)} · mic ${f.mic.level.toFixed(2)}\npeople    ${state.people} · camera ${state.cameraOn ? 'on' : 'off'}\nlatency (end of request → first audio)\n${lat}`;
  }, 250);
}

// ---------------------------------------------------------------- drag and drop
function initDrop() {
  let depth = 0;
  addEventListener('dragenter', (e) => { if (e.dataTransfer && [...e.dataTransfer.types].includes('Files')) { depth++; $('#dropzone').hidden = false; } });
  addEventListener('dragleave', () => { depth = Math.max(0, depth - 1); if (!depth) $('#dropzone').hidden = true; });
  addEventListener('dragover', (e) => e.preventDefault());
  addEventListener('drop', async (e) => {
    e.preventDefault(); depth = 0; $('#dropzone').hidden = true;
    for (const file of [...(e.dataTransfer?.files || [])].slice(0, 3)) await ingestFile(file);
  });
}
export async function ingestFile(file) {
  toast(`Reading ${file.name}…`);
  const res = await upload('/api/knowledge/upload', file);
  if (!res.ok) return toast(res.message);
  emit('memory:changed');
  return ask(res.prompt, { raw: true, display: `Dropped: ${file.name}` });
}

// ---------------------------------------------------------------- voice-only orb (always on top)
let pip = null;
export async function openOrb() {
  if (pip) { pip.close(); return; }
  if (!('documentPictureInPicture' in window)) return toast('The pop-out orb needs a recent Edge or Chrome (Document Picture-in-Picture).');
  try { pip = await window.documentPictureInPicture.requestWindow({ width: 300, height: 360 }); }
  catch { return toast('The browser blocked the pop-out. Click the orb button again.'); }
  const d = pip.document;
  d.body.style.cssText = 'margin:0;background:#04060c;color:#e9eef7;font:13px Segoe UI,system-ui,sans-serif;display:grid;grid-template-rows:1fr auto;height:100vh;text-align:center;overflow:hidden';
  const canvas = d.createElement('canvas');
  canvas.style.cssText = 'width:100%;height:100%;cursor:pointer';
  const cap = d.createElement('div');
  cap.style.cssText = 'padding:8px 12px 12px;min-height:54px';
  d.body.append(canvas, cap);
  canvas.title = 'Click to talk';
  canvas.addEventListener('click', () => emit('ui:action', { action: 'listen' }));
  const g = canvas.getContext('2d');
  const src = $('#holo');
  let alive = true;
  const draw = () => {
    if (!alive) return;
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (canvas.width !== w) { canvas.width = w; canvas.height = h; }
    const side = Math.min(src.width, src.height);
    g.clearRect(0, 0, w, h);
    try { g.drawImage(src, (src.width - side) / 2, (src.height - side) / 2, side, side, (w - Math.min(w, h)) / 2, (h - Math.min(w, h)) / 2, Math.min(w, h), Math.min(w, h)); } catch { /* canvas not ready */ }
    cap.textContent = `${$('#caption-speaker').textContent}  ${$('#caption-text').textContent}`.trim() || `${persona().name} · ${state.mode}`;
    cap.style.color = getComputedStyle(document.body).getPropertyValue('--c');
    pip.requestAnimationFrame(draw);
  };
  pip.requestAnimationFrame(draw);
  pip.addEventListener('pagehide', () => { alive = false; pip = null; });
}

export function initExtras() {
  initDrop();
  $('#memory-open').addEventListener('click', openMemory);
  $('#history-open').addEventListener('click', openHistory);
  $('#orb-btn').addEventListener('click', openOrb);
  $('#palette-input').addEventListener('input', () => { sel = 0; renderPalette(); });
  $('#palette-input').addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown') { sel = Math.min(shown.length - 1, sel + 1); renderPalette(); e.preventDefault(); }
    else if (e.key === 'ArrowUp') { sel = Math.max(0, sel - 1); renderPalette(); e.preventDefault(); }
    else if (e.key === 'Enter') { runPalette(sel); e.preventDefault(); }
  });
  $('#palette').addEventListener('click', (e) => { if (e.target.id === 'palette') closePalette(); });
}
