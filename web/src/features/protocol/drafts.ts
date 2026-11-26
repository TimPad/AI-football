import { useEffect, useRef, useState } from 'react';
/**
 * Черновик ввода в localStorage. `base` — отпечаток версии сервера, с которой начат черновик: хук запоминает
 * его при первой правке и отдаёт в `base`, пока черновик не сохранён, не очищен или не перенесён на текущую
 * версию (`rebase`). Так страница видит, что сервер изменился под черновиком. У черновика старого формата
 * версия неизвестна — `base` равен null.
 */
export function useDraft<T>(key: string, initial: T, validate: (v: unknown) => v is T, base?: string) {
  const [loaded] = useState(() => {
    let raw: string | null = null;
    try {
      raw = localStorage.getItem(key);
      if (!raw) return { value: initial, raw: null, error: '', dirty: false, corrupt: false, base: null };
      const stored = JSON.parse(raw);
      if (raw.length > 1000000 || stored.version !== 1 || !validate(stored.value)) throw Error();
      const from = typeof stored.base === 'string' ? stored.base : null;
      return { value: stored.value as T, raw: null, error: '', dirty: true, corrupt: false, base: from };
    } catch {
      return {
        value: initial,
        raw,
        error: raw
          ? 'Повреждён черновик ввода. Скачайте его перед очисткой.'
          : 'Локальная копия ввода недоступна. Скачайте ввод перед закрытием.',
        dirty: !!raw,
        corrupt: !!raw,
        base: null,
      };
    }
  });
  const [started, setStarted] = useState<string | null | undefined>(loaded.dirty ? loaded.base : undefined);
  const startedRef = useRef(started);
  function begin(from: string | null | undefined) {
    startedRef.current = from;
    setStarted(from);
  }
  function persist(next: T) {
    const from = startedRef.current;
    localStorage.setItem(key, JSON.stringify({ version: 1, value: next, ...(from == null ? {} : { base: from }) }));
  }
  const [error, setError] = useState(loaded.error);
  const [value, setValue] = useState<T>(loaded.value);
  const [dirty, setDirty] = useState(loaded.dirty);
  const [raw, setRaw] = useState(loaded.raw);
  const [corrupt, setCorrupt] = useState(loaded.corrupt);
  const current = useRef(value);
  const dirtyRef = useRef(loaded.dirty);
  function change(next: T) {
    if (corrupt) return;
    if (!dirtyRef.current) begin(base);
    current.current = next;
    dirtyRef.current = true;
    setValue(next);
    setDirty(true);
    try {
      persist(next);
      setError('');
    } catch {
      setError('Локальная копия ввода недоступна. Скачайте черновик перед закрытием.');
    }
  }
  /** Оставить черновик поверх текущей версии сервера: дальше он считается начатым с неё. */
  function rebase() {
    if (corrupt || !dirtyRef.current) return;
    begin(base);
    try {
      persist(current.current);
    } catch {
      setError('Локальная копия ввода недоступна. Скачайте черновик перед закрытием.');
    }
  }
  function markSaved(saved: T) {
    if (corrupt || JSON.stringify(saved) !== JSON.stringify(current.current)) return;
    dirtyRef.current = false;
    setDirty(false);
    begin(undefined);
    try {
      localStorage.removeItem(key);
    } catch {}
  }
  function clear() {
    try {
      localStorage.removeItem(key);
      setError('');
      setRaw(null);
      setCorrupt(false);
    } catch {
      setError('Не удалось очистить локальный черновик');
      if (corrupt) return;
    }
    current.current = initial;
    dirtyRef.current = false;
    setValue(initial);
    setDirty(false);
    begin(undefined);
  }
  useEffect(() => {
    const before = (e: BeforeUnloadEvent) => {
      if (dirty) {
        e.preventDefault();
        e.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', before);
    return () => window.removeEventListener('beforeunload', before);
  }, [dirty]);
  useEffect(() => {
    if (!dirtyRef.current) {
      current.current = initial;
      setValue(initial);
    }
  }, [JSON.stringify(initial), dirty]);
  return {
    value,
    change,
    clear,
    rebase,
    markSaved,
    error,
    dirty,
    raw,
    corrupt,
    base: dirty ? (started ?? null) : (base ?? null),
  };
}
