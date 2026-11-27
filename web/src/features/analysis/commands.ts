import { ApiError, api } from '../../api/client';
export type Pending = { path: string; method: string; body: Record<string, unknown> };
export function readPending(key: string): Pending | null {
  const raw = localStorage.getItem(key);
  if (!raw) return null;
  const p = JSON.parse(raw);
  if (
    typeof p.path !== 'string' ||
    !['POST', 'PUT'].includes(p.method) ||
    !p.body ||
    typeof p.body.request_id !== 'string'
  )
    throw Error('Повреждена сохранённая команда. Скачайте её перед очисткой.');
  return p;
}
export function prepare(key: string, path: string, body: Record<string, unknown>, method = 'POST'): Pending {
  const old = readPending(key);
  if (old) {
    const { request_id: _, ...oldBody } = old.body;
    if (old.path !== path || old.method !== method || JSON.stringify(oldBody) !== JSON.stringify(body))
      throw new ApiError('pending', 'Есть незавершённая отправка. Повторите её или скачайте и снимите блокировку.');
    return old;
  }
  const pending = { path, method, body: { ...body, request_id: crypto.randomUUID() } };
  localStorage.setItem(key, JSON.stringify(pending));
  return pending;
}
// Отказ сервера по существу (422) и запись в устаревшую версию разметки не применены, и повтор ответит так же:
// такая отправка не держится как незавершённая, иначе она запирает вкладку. Конфликт ревизии (409) остаётся
// незавершённым — его решает человек, без тихой подмены ревизии.
const rejected = (e: unknown) =>
  e instanceof ApiError && (e.status === 422 || (e.status === 409 && e.code === 'stale_analysis_run'));
export async function retryJson<T>(key: string, pending: Pending): Promise<T> {
  let result: T;
  try {
    result = await api<T>(pending.path, { method: pending.method, body: JSON.stringify(pending.body) });
  } catch (e) {
    if (rejected(e)) localStorage.removeItem(key);
    throw e;
  }
  localStorage.removeItem(key);
  return result;
}
export async function sendJson<T>(key: string, path: string, body: Record<string, unknown>, method = 'POST') {
  return retryJson<T>(key, prepare(key, path, body, method));
}
