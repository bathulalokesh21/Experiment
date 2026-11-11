// Approval cards. Click, voice ("send it") and gestures (👍/👎) all end up in resolve().
import { $, el, on, state } from '../core/bus.js';
import { get, post } from '../core/api.js';
import { sayLocal, toast } from '../core/conversation.js';
import { sfx } from '../fx/sfx.js';

function render() {
  const zone = $('#approval-zone');
  zone.replaceChildren(...state.approvals.map((card) => el('div', { class: 'approval', 'data-id': card.id },
    el('h4', { text: card.title }),
    card.warning ? el('div', { class: 'warn', text: '⚠ ' + card.warning }) : null,
    card.result && card.status === 'pending' ? el('div', { class: 'result', text: card.result }) : null,
    el('dl', {}, ...card.fields.flatMap((f) => [el('dt', { text: f.label }), el('dd', {}, f.code ? el('pre', { text: f.value }) : document.createTextNode(f.value))])),
    el('div', { class: 'acts' },
      el('button', { class: 'yes approve-btn', text: card.kind === 'call' ? 'Call' : card.kind === 'plugin' ? 'Install' : 'Send', onclick: () => resolve('approve', 'click', card.id) }),
      el('button', { class: 'ghost cancel-btn', text: 'Cancel', onclick: () => resolve('cancel', 'click', card.id) }),
      el('span', { class: 'sub', text: 'or say “send it” / “cancel”, or 👍 / 👎' })))));
}

let working = false;
export async function resolve(action, via = 'click', id = 'latest') {
  if (working || !state.approvals.length) return null;
  working = true;
  const res = await post(`/api/approvals/${id}/${action}`, { via });
  working = false;
  await refresh();
  if (res.ok) { action === 'approve' ? sfx.approved() : sfx.cancelled(); }
  else sfx.error();
  if (res.message) { toast(res.message); sayLocal(res.message); }
  return res;
}

export async function refresh() {
  const res = await get('/api/approvals');
  if (res.ok) { state.approvals = res.cards; render(); }
}

export function initApprovals() {
  refresh();
  on('srv:approval', ({ card }) => { if (!state.approvals.some((c) => c.id === card.id)) state.approvals.push(card); render(); sfx.approval(); });
  on('srv:approval_done', () => refresh());
}
