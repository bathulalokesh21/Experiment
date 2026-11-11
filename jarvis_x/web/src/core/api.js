// Server calls. Every failure becomes a plain-English message, never an exception in the UI.
import { emit } from './bus.js';

async function request(method, url, body, isForm = false) {
  try {
    const res = await fetch(url, {
      method, headers: body && !isForm ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? (isForm ? body : JSON.stringify(body)) : undefined,
    });
    const data = await res.json().catch(() => ({ ok: false, message: `The server answered ${res.status}.` }));
    if (!res.ok && data.ok === undefined) data.ok = false;
    return data;
  } catch (err) {
    return { ok: false, offline: true, message: 'The JARVIS server is not answering. Is `python run.py` still running?' };
  }
}
export const get = (url) => request('GET', url);
export const post = (url, body = {}) => request('POST', url, body);
export const put = (url, body = {}) => request('PUT', url, body);
export const del = (url) => request('DELETE', url);
export const upload = (url, file, name = 'file') => {
  const form = new FormData();
  form.append('file', file, file.name || name);
  return request('POST', url, form, true);
};

/** POST /api/chat and call onEvent for each SSE event. Resolves when the stream ends. */
export async function chatStream(body, onEvent, signal) {
  let res;
  try {
    res = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal });
  } catch (err) {
    if (err.name !== 'AbortError') onEvent({ type: 'error', message: 'The JARVIS server is not answering.' });
    onEvent({ type: 'done', text: '', aborted: err.name === 'AbortError' });
    return;
  }
  if (!res.ok || !res.body) {
    const data = await res.json().catch(() => ({}));
    onEvent({ type: 'error', message: data.message || `The server answered ${res.status}.` });
    onEvent({ type: 'done', text: '' });
    return;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let sawDone = false;
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let cut;
      while ((cut = buffer.indexOf('\n\n')) >= 0) {
        const block = buffer.slice(0, cut);
        buffer = buffer.slice(cut + 2);
        for (const line of block.split('\n')) {
          if (!line.startsWith('data: ')) continue;
          try {
            const event = JSON.parse(line.slice(6));
            if (event.type === 'done') sawDone = true;
            onEvent(event);
          } catch { /* partial line */ }
        }
      }
    }
  } catch (err) {
    if (err.name !== 'AbortError') onEvent({ type: 'error', message: 'The answer was cut off.' });
  }
  if (!sawDone) onEvent({ type: 'done', text: '', aborted: true });
}

/** Server push: reminders, weather, approvals, memory chips, routines, proactive cards. */
export function connectEvents() {
  const source = new EventSource('/api/events');
  source.onmessage = (msg) => {
    try {
      const event = JSON.parse(msg.data);
      emit(`srv:${event.type}`, event);
    } catch { /* ignore */ }
  };
  source.onerror = () => emit('srv:offline');
  source.onopen = () => emit('srv:online');
  return source;
}
