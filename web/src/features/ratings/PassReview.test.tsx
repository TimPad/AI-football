import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { PassReview } from './PassReview';

const H1 = '11111111-1111-4111-8111-111111111111',
  H2 = '22222222-2222-4222-8222-222222222222',
  A1 = '33333333-3333-4333-8333-333333333333';

const pass = (id: string, start: number, over: Record<string, unknown> = {}) => ({
  id,
  kind: 'pass',
  player_id: H1,
  recipient_id: H2,
  opponent_id: null,
  side: 'home',
  role: null,
  start_ms: start,
  end_ms: start + 1000,
  success: true,
  on_target: null,
  outcome: 'success',
  possession_id: null,
  start_xy: [10, 5],
  end_xy: [18, 6],
  attacking_direction: 'unknown',
  penalty_conceded: false,
  source_episode_id: null,
  source_video_ms: null,
  shot_id: null,
  decision: 'accepted',
  review: 'auto',
  notes: '',
  ...over,
});

function overview(auto = true) {
  const document = {
    clock_basis: 'video',
    analysis_scope: 'full_match',
    duration_ms: 240000,
    source_participation_version_id: null,
    source_analysis_run_id: null,
    source_protocol_version_id: null,
    actions: [
      pass('p1', 10000),
      pass('p2', 30000, { success: false, outcome: 'failure', recipient_id: null }),
      pass('p3', 50000, { review: undefined }),
    ],
    links: [],
    completeness: { passes: [{ status: 'partial', intervals: [[0, 240000]], player_ids: null }] },
    notes: '',
  };
  return {
    match_id: 'm1',
    match_revision: 7,
    revision: 1,
    current: {
      id: 'v1',
      revision: 1,
      status: 'confirmed',
      created_at: '2026-11-22T10:00:00Z',
      auto,
      match_id: 'm1',
      created_by: 'a1',
      context_hash: 'x',
      document,
      provenance: {},
      lineup: [],
      canonical_actions: [],
    },
    versions: [],
    lineup: [
      { player_id: H1, display_name: 'Иванов', side: 'home', shirt_number: '7' },
      { player_id: H2, display_name: 'Петров', side: 'home', shirt_number: '9' },
      { player_id: A1, display_name: 'Сидоров', side: 'away', shirt_number: '4' },
    ],
    rules: {},
    pitch: { length_m: 40, width_m: 20 },
    protocol_versions: [],
    analysis_runs: [],
    participation_versions: [],
  };
}

let puts: { url: string; body: Record<string, unknown> }[] = [];
const title = (area: HTMLElement) => area.querySelector('.pass-review-title')!;
beforeEach(() => {
  puts = [];
  // В jsdom нет воспроизведения: переход к моменту проверяется по currentTime.
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockImplementation(async () => undefined);
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => undefined);
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: unknown, options: RequestInit = {}) => {
      const json = (v: unknown) => new Response(JSON.stringify(v), { headers: { 'Content-Type': 'application/json' } });
      if (options.method === 'PUT') {
        puts.push({ url: String(url), body: JSON.parse(String(options.body)) });
        return json({ id: 'v2', revision: 2 });
      }
      return json(overview());
    }),
  );
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  localStorage.clear();
});

const reviewed = (body: Record<string, unknown>) =>
  Object.fromEntries(
    ((body.document as { actions: Record<string, unknown>[] }).actions ?? []).map((a) => [
      a.id,
      [a.review, a.decision, a.success, a.recipient_id],
    ]),
  );

it('walks through video passes: right, inaccurate, not a pass, and saves a checked version', async () => {
  render(<PassReview matchId="m1" actorId="a1" />);
  const area = await screen.findByRole('region', { name: 'Проверка передач' });
  // Передача без поля проверки в автоматической версии — тоже непроверенная.
  expect(within(area).getByRole('status', { name: 'Проверено передач' })).toHaveTextContent('0 / 3');
  expect(title(area)).toHaveTextContent('0:10 · Иванов → Петров · точная · не проверена');
  fireEvent.click(within(area).getByRole('button', { name: /^Верно/ }));
  // Следующая — неточная: клавиша T делает её точной, Enter — подтверждает.
  expect(title(area)).toHaveTextContent('0:30 · Иванов · неточная · не проверена');
  const grid = area.querySelector('.pass-review-grid')!;
  fireEvent.keyDown(grid, { key: 't' });
  fireEvent.change(within(area).getByLabelText('Принял'), { target: { value: H2 } });
  fireEvent.keyDown(grid, { key: 'Enter' });
  // Третья — не передача (русская раскладка: Ч на месте X).
  expect(title(area)).toHaveTextContent('0:50 · Иванов → Петров · точная');
  fireEvent.keyDown(grid, { key: 'ч' });
  expect(within(area).getByRole('status', { name: 'Проверено передач' })).toHaveTextContent('3 / 3');
  expect(within(area).getByRole('note')).toHaveTextContent('Все передачи проверены — сохраните проверку.');
  // «Сидоров» из другой команды в выборе игрока не предлагается.
  fireEvent.click(within(area).getByRole('button', { name: /^Все · 3/ }));
  fireEvent.click(within(area).getByRole('button', { name: /0:30/ }));
  expect(within(within(area).getByLabelText('Отдал')).queryByText(/Сидоров/)).toBeNull();

  fireEvent.click(within(area).getByRole('button', { name: 'Сохранить и подтвердить проверку' }));
  await waitFor(() => expect(puts).toHaveLength(1));
  expect(puts[0].url).toContain('/matches/m1/performance-actions');
  expect(puts[0].body).toMatchObject({ expected_revision: 1, expected_match_revision: 7, status: 'confirmed' });
  expect(reviewed(puts[0].body)).toEqual({
    p1: ['checked', 'accepted', true, H2],
    p2: ['checked', 'accepted', true, H2],
    p3: ['checked', 'rejected', true, H2],
  });
});

it('keeps unchecked passes as auto and does not save before any check', async () => {
  render(<PassReview matchId="m1" actorId="a1" />);
  const area = await screen.findByRole('region', { name: 'Проверка передач' });
  expect(within(area).getByRole('button', { name: 'Сохранить и подтвердить проверку' })).toBeDisabled();
  fireEvent.click(within(area).getByRole('button', { name: 'Неточная T' }));
  fireEvent.click(within(area).getByRole('button', { name: 'Сохранить как черновик версии' }));
  await waitFor(() => expect(puts).toHaveLength(1));
  expect(puts[0].body.status).toBe('review');
  expect(reviewed(puts[0].body)).toEqual({
    p1: ['checked', 'accepted', false, null],
    p2: ['auto', 'accepted', false, null],
    p3: ['auto', 'accepted', true, H2],
  });
});

it('opens the local recording and jumps to the selected pass', async () => {
  vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: () => 'blob:match', revokeObjectURL: () => undefined }));
  render(<PassReview matchId="m1" actorId="a1" />);
  const area = await screen.findByRole('region', { name: 'Проверка передач' });
  const input = within(area).getByText('Открыть запись матча').querySelector('input')!;
  fireEvent.change(input, { target: { files: [new File(['mp4'], 'match.mp4', { type: 'video/mp4' })] } });
  const player = (await within(area).findByLabelText('Запись матча')) as HTMLVideoElement;
  expect(player).toHaveAttribute('src', 'blob:match');
  // За 2 с до передачи на 10 с.
  await waitFor(() => expect(player.currentTime).toBe(8));
  fireEvent.click(within(area).getByRole('button', { name: /^Верно/ }));
  await waitFor(() => expect(player.currentTime).toBe(28));
});

it('stays hidden when the current version has no video passes', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => {
      const value = overview(false);
      value.current.document.actions = value.current.document.actions.map((a) => ({ ...a, review: null as never }));
      return new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' } });
    }),
  );
  const { container } = render(<PassReview matchId="m1" actorId="a1" />);
  await waitFor(() => expect(container.querySelector('.loading, [aria-busy]')).toBeNull());
  expect(screen.queryByRole('region', { name: 'Проверка передач' })).toBeNull();
});
