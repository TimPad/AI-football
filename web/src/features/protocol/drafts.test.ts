import { act, renderHook } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { useDraft } from './drafts';

const validate = (v: unknown): v is { text: string } =>
  !!v && typeof v === 'object' && 'text' in v && typeof v.text === 'string';
afterEach(() => localStorage.clear());
it('restores unsent input after remount', () => {
  let h = renderHook(() => useDraft('draft', { text: '' }, validate));
  act(() => h.result.current.change({ text: 'Несохранённый гол' }));
  h.unmount();
  h = renderHook(() => useDraft('draft', { text: '' }, validate));
  expect(h.result.current.value.text).toBe('Несохранённый гол');
  expect(h.result.current.dirty).toBe(true);
});
it('reports and preserves malformed draft rather than overwriting it', () => {
  localStorage.setItem('draft', '{broken');
  const h = renderHook(() => useDraft('draft', { text: '' }, validate));
  expect(h.result.current.error).toContain('Повреждён');
  act(() => h.result.current.change({ text: 'new' }));
  expect(localStorage.getItem('draft')).toBe('{broken');
  expect(h.result.current.raw).toBe('{broken');
});
it('remembers the version a draft started from until it is rebased', () => {
  const h = renderHook(({ base }) => useDraft('draft', { text: '' }, validate, base), {
    initialProps: { base: 'v1' },
  });
  expect(h.result.current.base).toBe('v1');
  act(() => h.result.current.change({ text: 'a' }));
  h.rerender({ base: 'v2' });
  expect(h.result.current.base).toBe('v1');
  expect(JSON.parse(localStorage.getItem('draft') ?? '{}').base).toBe('v1');
  act(() => h.result.current.rebase());
  expect(h.result.current.base).toBe('v2');
  act(() => h.result.current.change({ text: 'b' }));
  expect(JSON.parse(localStorage.getItem('draft') ?? '{}').base).toBe('v2');
  h.unmount();
  const again = renderHook(() => useDraft('draft', { text: '' }, validate, 'v3'));
  expect(again.result.current.base).toBe('v2');
  localStorage.setItem('draft', JSON.stringify({ version: 1, value: { text: 'old' } }));
  again.unmount();
  const legacy = renderHook(() => useDraft('draft', { text: '' }, validate, 'v3'));
  expect(legacy.result.current.base).toBeNull();
});
