// Ambient world behind the whole dashboard (Canvas2D, cheap):
// JARVIS neural constellation · FRIDAY drifting embers and bokeh · ROBIN falling petals.
import { on, state } from '../core/bus.js';
import { features } from '../core/audio.js';

export function startAmbient(canvas) {
  const g = canvas.getContext('2d');
  let W = 0, H = 0, items = [], world = state.persona, fade = 1, last = performance.now();
  const resize = () => { W = canvas.width = innerWidth; H = canvas.height = innerHeight; seed(); };
  const rnd = (a, b) => a + Math.random() * (b - a);
  function seed() {
    const n = { jarvis: 70, friday: 55, robin: 46 }[world] || 60;
    items = Array.from({ length: n }, () => make(true));
  }
  function make(anywhere) {
    if (world === 'jarvis') return { x: rnd(0, W), y: rnd(0, H), vx: rnd(-6, 6), vy: rnd(-6, 6), r: rnd(0.8, 2), p: rnd(0, 6.28) };
    if (world === 'friday') return { x: rnd(0, W), y: anywhere ? rnd(0, H) : H + 20, vx: rnd(-8, 8), vy: rnd(-26, -8), r: Math.random() < 0.2 ? rnd(14, 40) : rnd(1, 2.6), p: rnd(0, 6.28) };
    return { x: rnd(-40, W), y: anywhere ? rnd(0, H) : -20, vx: rnd(8, 28), vy: rnd(18, 46), r: rnd(4, 9), p: rnd(0, 6.28), s: rnd(0.6, 2.2) };
  }
  on('persona', ({ id }) => { world = id; fade = 0; seed(); });
  addEventListener('resize', resize);
  resize();

  function frame(now) {
    requestAnimationFrame(frame);
    if (document.hidden) { last = now; return; }
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    fade = Math.min(1, fade + dt * 0.8);
    const f = features();
    const energy = state.mode === 'speak' ? f.out.level : state.mode === 'listen' ? f.mic.level : 0;
    g.clearRect(0, 0, W, H);
    g.globalAlpha = fade;
    if (world === 'jarvis') {
      g.fillStyle = 'rgba(255,194,74,.55)'; g.strokeStyle = 'rgba(255,194,74,.07)'; g.lineWidth = 1;
      for (const a of items) {
        a.x += a.vx * dt; a.y += a.vy * dt;
        if (a.x < 0 || a.x > W) a.vx *= -1;
        if (a.y < 0 || a.y > H) a.vy *= -1;
        const tw = 0.5 + 0.5 * Math.sin(now / 900 + a.p);
        g.globalAlpha = fade * (0.25 + 0.5 * tw + energy * 0.4);
        g.beginPath(); g.arc(a.x, a.y, a.r, 0, 6.28); g.fill();
      }
      g.globalAlpha = fade;
      for (let i = 0; i < items.length; i++) for (let j = i + 1; j < items.length; j++) {
        const dx = items[i].x - items[j].x, dy = items[i].y - items[j].y;
        if (dx * dx + dy * dy < 150 * 150) { g.beginPath(); g.moveTo(items[i].x, items[i].y); g.lineTo(items[j].x, items[j].y); g.stroke(); }
      }
    } else if (world === 'friday') {
      for (let i = 0; i < items.length; i++) {
        const a = items[i];
        a.x += (a.vx + Math.sin(now / 1300 + a.p) * 10) * dt; a.y += a.vy * dt * (1 + energy);
        if (a.y < -50) items[i] = make(false);
        const big = a.r > 10;
        g.globalAlpha = fade * (big ? 0.05 : 0.5 + 0.4 * Math.sin(now / 300 + a.p));
        g.fillStyle = big ? '#ff8a4a' : '#ffb070';
        g.beginPath(); g.arc(a.x, a.y, a.r, 0, 6.28); g.fill();
      }
    } else {
      for (let i = 0; i < items.length; i++) {
        const a = items[i];
        a.p += a.s * dt;
        a.x += (a.vx + Math.sin(a.p) * 22) * dt; a.y += a.vy * dt;
        if (a.y > H + 20 || a.x > W + 40) items[i] = make(false);
        g.save();
        g.translate(a.x, a.y); g.rotate(a.p); g.scale(1, 0.35 + 0.65 * Math.abs(Math.cos(a.p * 1.3)));
        g.globalAlpha = fade * 0.5;
        g.fillStyle = i % 3 ? '#ffb7d5' : '#d9c2ff';
        g.beginPath(); g.moveTo(0, -a.r); g.bezierCurveTo(a.r, -a.r * 0.6, a.r * 0.7, a.r, 0, a.r * 0.75);
        g.bezierCurveTo(-a.r * 0.7, a.r, -a.r, -a.r * 0.6, 0, -a.r); g.fill();
        g.restore();
      }
    }
    g.globalAlpha = 1;
  }
  requestAnimationFrame(frame);
}
