// Detail overlay (widgets expand into this; nothing gets hidden) + toast helpers.
import { $, el } from '../core/bus.js';

let onClose = null;
export function openOverlay(title, body, closed) {
  $('#overlay-title').textContent = title;
  const box = $('#overlay-body');
  box.replaceChildren(...(Array.isArray(body) ? body : [body]));
  $('#overlay').hidden = false;
  onClose = closed || null;
  $('#overlay-close').focus();
}
export function closeOverlay() {
  if ($('#overlay').hidden) return false;
  $('#overlay').hidden = true;
  $('#overlay-body').replaceChildren();
  const fn = onClose; onClose = null;
  if (fn) fn();
  return true;
}
export function initOverlay() {
  $('#overlay-close').addEventListener('click', closeOverlay);
  $('#overlay').addEventListener('click', (e) => { if (e.target.id === 'overlay') closeOverlay(); });
}
export const h4 = (text) => el('h4', { text });
export const para = (text, cls = '') => el('p', { class: cls, text });
