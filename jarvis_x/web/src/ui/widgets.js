// Top row: clock, weather (with hourly sparkline), headlines, power meter. Each expands into a detail overlay.
import { $, el, on, state, persona } from '../core/bus.js';
import { get } from '../core/api.js';
import { ask, toast } from '../core/conversation.js';
import { openOverlay, h4, para } from './overlay.js';

let weather = null, news = null;
const ago = (ts) => { const m = Math.round((Date.now() / 1000 - ts) / 60); return m < 1 ? 'just now' : `${m} min ago`; };

function tickClock() {
  const now = new Date();
  const clock = now.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: true }).replace(/\s?(am|pm)/i, (m) => m.toUpperCase());
  $('#clock').textContent = clock;
  $('#ambient-clock').textContent = clock;
  $('#date').textContent = now.toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long' });
}

function ticker(node, to, suffix = '') {   // number ticker micro-interaction
  const from = parseFloat(node.dataset.v || to) || 0;
  node.dataset.v = to;
  const t0 = performance.now();
  const step = (now) => {
    const k = Math.min(1, (now - t0) / 500);
    node.textContent = Math.round(from + (to - from) * k) + suffix;
    if (k < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

export function drawSpark(canvas, hourly) {
  const g = canvas.getContext('2d');
  const W = canvas.width, H = canvas.height;
  g.clearRect(0, 0, W, H);
  if (!hourly || hourly.length < 2) return;
  const temps = hourly.map((h) => h.temp);
  const lo = Math.min(...temps), hi = Math.max(...temps), span = Math.max(1, hi - lo);
  const colour = getComputedStyle(document.body).getPropertyValue('--c').trim() || '#ffc24a';
  const x = (i) => (i / (hourly.length - 1)) * (W - 4) + 2;
  hourly.forEach((h, i) => {   // rain probability as soft bars behind the line
    if (h.pop >= 30) { g.fillStyle = `rgba(110,170,255,${Math.min(0.6, h.pop / 140)})`; g.fillRect(x(i) - 2, H - (h.pop / 100) * H, 4, (h.pop / 100) * H); }
  });
  g.beginPath();
  hourly.forEach((h, i) => { const y = H - 5 - ((h.temp - lo) / span) * (H - 12); i ? g.lineTo(x(i), y) : g.moveTo(x(i), y); });
  g.strokeStyle = colour; g.lineWidth = 1.6; g.stroke();
}

function renderWeather(w) {
  weather = w;
  const shown = w.ok ? w : w.stale;
  if (shown) {
    ticker($('#weather-temp'), shown.temp, '°');
    $('#weather-desc').textContent = `${shown.desc} · ${shown.city}`;
    $('#weather-meta').textContent = `Feels ${shown.feels}° · H ${shown.high}° L ${shown.low}° · ${shown.humidity}% · ${shown.wind} km/h`;
    $('#weather-rain').textContent = w.ok ? shown.rain : `${w.error} Showing the last reading.`;
    drawSpark($('#weather-spark'), shown.hourly);
    $('#ambient-weather').textContent = `${shown.temp}° ${shown.desc} · ${shown.city}`;
  } else {
    $('#weather-temp').textContent = '--°';
    $('#weather-desc').textContent = 'Weather unavailable';
    $('#weather-meta').textContent = '';
    $('#weather-rain').textContent = w.error || '';
  }
  $('#weather-updated').textContent = w.updated ? ago(w.updated) : '';
}

function renderNews(n) {
  news = n;
  const list = $('#news-list');
  if (!n.items || !n.items.length) { list.replaceChildren(el('li', { class: 'sub', text: n.error || 'No headlines right now.' })); return; }
  list.replaceChildren(...n.items.map((item) => el('li', {},
    item.new ? el('span', { class: 'new', text: 'NEW' }) : null,
    el('span', { class: 't', title: `${item.title} (${item.source}). Click for a spoken brief.`, text: item.title,
      onclick: (e) => { e.stopPropagation(); ask(`Brief me on this headline in three sentences: what happened and why it matters. "${item.title}" (${item.source})`, { raw: true, display: `Brief: ${item.title}` }); } }),
    el('a', { href: item.link, target: '_blank', rel: 'noopener', title: 'Open the article', text: '↗', onclick: (e) => e.stopPropagation() }))));
  $('#news-updated').textContent = n.updated ? ago(n.updated) : '';
}

export function renderPower(usage) {
  state.usage = usage;
  const pct = usage.percent;
  const names = { allowed: 'All good. Claude has not reported a percentage.', allowed_warning: 'Getting close to the limit.', rejected: 'Limit reached. Waiting for the reset.', unknown: 'Waiting for the first answer…' };
  if (pct != null) { $('#power-fill').style.width = `${Math.min(100, pct)}%`; $('#power-pct').textContent = `${pct}%`; $('#power-status').textContent = `${pct}% of the ${usage.limit_type ? usage.limit_type.replace(/_/g, ' ') : 'current'} window used.`; }
  else { $('#power-fill').style.width = usage.status === 'rejected' ? '100%' : usage.status === 'allowed_warning' ? '85%' : usage.status === 'allowed' ? '8%' : '0'; $('#power-pct').textContent = usage.status === 'unknown' ? '—' : usage.status === 'allowed' ? 'OK' : usage.status === 'rejected' ? 'MAX' : 'HIGH'; $('#power-status').textContent = names[usage.status] || names.unknown; }
  $('#power-reset').textContent = usage.resets_at ? `resets ${new Date(usage.resets_at * 1000).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}` : '';
}

async function loadWeather(refresh = false) {
  const res = await get(`/api/weather${refresh ? '?refresh=1' : ''}`);
  if (res.ok) renderWeather(res.weather); else renderWeather({ ok: false, error: res.message });
}
async function loadNews(refresh = false) {
  const res = await get(`/api/news${refresh ? '?refresh=1' : ''}`);
  if (res.ok) renderNews(res.news); else renderNews({ items: [], error: res.message });
}

function expand(kind) {
  if (kind === 'weather' && weather) {
    const w = weather.ok ? weather : weather.stale;
    if (!w) return openOverlay('Weather', para(weather.error || 'Weather is unavailable.'));
    const canvas = el('canvas', { width: 780, height: 150, style: 'width:100%' });
    const rows = w.hourly.slice(0, 24).filter((_, i) => i % 2 === 0).map((h) => el('tr', {}, el('td', { text: h.t }), el('td', { text: `${h.temp}°C` }), el('td', { text: `${h.pop}% rain` })));
    openOverlay(`Weather · ${w.city}`, [para(`${w.temp}°C, ${w.desc}. Feels like ${w.feels}°C. ${w.rain}`), canvas, h4('Next 24 hours'),
      el('table', {}, ...rows), para(`Source: ${w.source}. Refreshes every 5 minutes.`, 'sub')]);
    drawSpark(canvas, w.hourly);
  } else if (kind === 'news' && news) {
    const topics = ['top', 'business', 'technology', 'india', 'ai', 'startups', 'world', 'science', 'sports', 'anime', 'music'];
    const list = el('div', {});
    const show = (items) => list.replaceChildren(...items.map((i) => el('div', { class: 'fact' }, el('span', { class: 'grow', text: `${i.title} — ${i.source}` }),
      el('a', { href: i.link, target: '_blank', rel: 'noopener', text: 'open ↗' }))));
    show(news.items || []);
    openOverlay('Headlines', [el('div', { class: 'chips' }, ...topics.map((t) => el('button', { text: t, onclick: async () => { const r = await get(`/api/news?topic=${t}&refresh=1`); show(r.ok ? r.news.items : []); if (r.ok && r.news.error) toast(r.news.error); } }))), list]);
  } else if (kind === 'power') {
    const u = state.usage || {};
    openOverlay('Power', [para(u.percent != null ? `${u.percent}% of your Claude usage window is used.` : 'Claude has not sent a usage percentage yet. The card shows a status instead.'),
      para('Checkpoints at 25, 50, 85, 90 and 100% are announced once each, in character, after the answer.', 'sub'),
      para('Tip: ROBIN (Haiku) is the lightest on your limit, JARVIS (Opus) the heaviest.', 'sub')]);
  } else if (kind === 'brand') {
    const t = state.timings.last;
    openOverlay('JARVIS X', [para(`Active assistant: ${persona().name}. ${state.fake ? 'Running in offline demo mode.' : 'Running on your Claude Code login.'}`),
      para(t ? `Last answer: first audio after ${t.firstAudio} ms.` : 'No answers timed yet.', 'sub'),
      para('Space = talk · Esc = stop · Ctrl+K = commands · Ctrl+Shift+D = debug overlay', 'sub')]);
  }
}

export function initWidgets() {
  tickClock();
  setInterval(tickClock, 1000);
  loadWeather(); loadNews();
  setInterval(() => { loadWeather(); loadNews(); }, 5 * 60 * 1000);   // every 5 minutes, even if server push is down
  setInterval(() => { if (weather && weather.updated) $('#weather-updated').textContent = ago(weather.updated); if (news && news.updated) $('#news-updated').textContent = ago(news.updated); }, 30000);
  $('#weather-refresh').addEventListener('click', (e) => { e.stopPropagation(); $('#weather-desc').textContent = 'Refreshing…'; loadWeather(true); });
  $('#news-refresh').addEventListener('click', (e) => { e.stopPropagation(); loadNews(true); });
  on('srv:weather', (ev) => renderWeather(ev.weather));
  on('srv:news', (ev) => renderNews(ev.news));
  on('srv:usage', (ev) => renderPower(ev.usage));
  on('persona', () => { if (weather) drawSpark($('#weather-spark'), (weather.ok ? weather : weather.stale || {}).hourly); });
  for (const card of document.querySelectorAll('[data-expand]')) {
    card.addEventListener('click', () => expand(card.dataset.expand));
    card.addEventListener('keydown', (e) => { if (e.key === 'Enter') expand(card.dataset.expand); });
  }
}
