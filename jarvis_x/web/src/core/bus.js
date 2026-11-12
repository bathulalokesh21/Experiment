// Tiny event bus + reactive state shared by every module.
const handlers = new Map();
export function on(type, fn) {
  if (!handlers.has(type)) handlers.set(type, new Set());
  handlers.get(type).add(fn);
  return () => handlers.get(type).delete(fn);
}
export function emit(type, data) {
  for (const fn of handlers.get(type) || []) {
    try { fn(data); } catch (err) { console.error(`[bus] ${type}`, err); }
  }
}
export const state = {
  personas: [], persona: 'jarvis', settings: {}, mode: 'idle', // idle | notice | listen | think | speak
  speaking: false, busy: false, muted: false, drill: null, party: false, ambient: false, asleep: false,
  people: 0, approvals: [], currentReply: '', timings: {}, cameraOn: false, booted: false, fake: false,
};
export function setMode(mode) {
  if (state.mode === mode) return;
  state.mode = mode;
  document.body.dataset.state = mode;
  emit('mode', mode);
}
export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
export function el(tag, attrs = {}, ...kids) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') node.className = v;
    else if (k === 'text') node.textContent = v;
    else if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
    else if (k === 'style') node.style.cssText = v;
    else if (v !== false && v != null) node.setAttribute(k, v === true ? '' : v);
  }
  for (const kid of kids.flat()) if (kid != null) node.append(kid);
  return node;
}
export function persona(id = state.persona) {
  return state.personas.find((p) => p.id === id) || { id, name: id.toUpperCase(), colour: '#ffc24a', address: 'sir', acks: [] };
}
