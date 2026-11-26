import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import type { Match } from '../../api/domain';
import { VideoTagging } from './VideoTagging';

const H1 = '11111111-1111-4111-8111-111111111111',
  A1 = '33333333-3333-4333-8333-333333333333';
const pass = {
  id: 'p1',
  kind: 'pass',
  player_id: H1,
  recipient_id: null,
  opponent_id: null,
  side: 'home',
  role: null,
  start_ms: 10000,
  end_ms: 11000,
  success: false,
  on_target: null,
  outcome: 'failure',
  possession_id: null,
  start_xy: null,
  end_xy: null,
  attacking_direction: 'unknown',
  penalty_conceded: false,
  source_episode_id: null,
  source_video_ms: null,
  shot_id: null,
  decision: 'accepted',
  review: 'auto',
  notes: '',
};
const overview = {
  match_id: 'm1',
  match_revision: 7,
  revision: 3,
  current: {
    id: 'v3',
    revision: 3,
    status: 'confirmed',
    auto: true,
    match_id: 'm1',
    document: {
      clock_basis: 'video',
      analysis_scope: 'full_match',
      duration_ms: 2_600_000,
      source_participation_version_id: null,
      source_analysis_run_id: 'run1',
      source_protocol_version_id: null,
      actions: [pass],
      links: [],
      completeness: { passes: [{ status: 'partial', intervals: null, player_ids: null }] },
      notes: '',
    },
    canonical_actions: [],
  },
  versions: [],
  lineup: [
    { player_id: H1, display_name: 'Иванов', side: 'home', shirt_number: '7' },
    { player_id: A1, display_name: 'Сидоров', side: 'away', shirt_number: '4' },
  ],
  rules: { periods_s: [1200, 1200] },
  pitch: { length_m: 40, width_m: 20 },
  protocol_versions: [],
  analysis_runs: [],
  participation_versions: [],
};
const moments = {
  run_id: 'run1',
  video_s: 2600,
  halves: [
    [45, 1250],
    [1375, 2590],
  ],
  side_map: { A: 'home', B: 'away' },
  board_final: { left: 1, right: 0 },
  board_goals: [{ t_s: 159, plate: 'left' }],
  replays: [[416, 427]],
  shots: [{ t_s: 397, side: 'home', on_target: true }],
};
const match = {
  id: 'm1',
  revision: 7,
  home: { team: { name: 'РЕХАБ' } },
  away: { team: { name: 'ВШЭ Ю' } },
  projection: { effective_score: { home: 1, away: 0 } },
  protocol: { draft: false, events: [] },
} as unknown as Match;

let puts: { url: string; body: Record<string, unknown> }[] = [];
let posts: { url: string; body: Record<string, unknown> }[] = [];
beforeEach(() => {
  puts = [];
  posts = [];
  vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: () => 'blob:match', revokeObjectURL: () => undefined }));
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: unknown, options: RequestInit = {}) => {
      const json = (v: unknown) => new Response(JSON.stringify(v), { headers: { 'Content-Type': 'application/json' } });
      const path = String(url);
      if (options.method === 'PUT') {
        puts.push({ url: path, body: JSON.parse(String(options.body)) });
        return json({ id: 'v4', revision: 4 });
      }
      if (options.method === 'POST') {
        posts.push({ url: path, body: JSON.parse(String(options.body)) });
        return json({ ...match, revision: 8 + posts.length });
      }
      if (path.includes('/moments')) return json(moments);
      if (path.endsWith('/matches/m1')) return json(match);
      return json(overview);
    }),
  );
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  localStorage.clear();
});

async function open() {
  render(<VideoTagging match={match} actorId="a1" />);
  const area = await screen.findByRole('region', { name: 'Разметка ударов и защиты' });
  const input = within(area).getByText('Открыть запись матча').querySelector('input')!;
  fireEvent.change(input, { target: { files: [new File(['mp4'], 'match.mp4', { type: 'video/mp4' })] } });
  const player = (await within(area).findByLabelText('Запись матча')) as HTMLVideoElement;
  return { area, player, grid: area.querySelector('.tagging-grid')! };
}

it('tags shots and defence by keys at the current moment and saves a version with the passes kept', async () => {
  const { area, player, grid } = await open();
  // Закладки: гол по табло (команда — по счёту протокола), повтор и удар по видео.
  const marks = within(area).getByRole('list', { name: 'Закладки' });
  expect(
    within(marks)
      .getAllByRole('listitem')
      .map((li) => li.textContent!.replace(/\s+/g, ' ')),
  ).toEqual(["2' Гол по табло · РЕХАБ", "6' Удар? по видео, в створ · РЕХАБ", "7' Повтор трансляции — опасный момент"]);
  fireEvent.click(within(marks).getByRole('button', { name: /Удар\? по видео/ }));
  expect(player.currentTime).toBe(393);
  fireEvent.keyDown(grid, { code: 'Digit1' }); // удар в створ хозяев
  player.currentTime = 600;
  fireEvent.keyDown(grid, { code: 'Digit5', shiftKey: true }); // отбор гостей
  const items = within(area).getByRole('list', { name: 'Отметки' });
  const text = (li: HTMLElement) => li.querySelector('.link-button')!.textContent!.replace(/\s+/g, ' ');
  expect(within(items).getAllByRole('listitem').map(text)).toEqual(["6' Удар в створ", "10' Отбор"]);
  expect(within(marks).getAllByRole('listitem')[1]).toHaveTextContent('отмечено');
  fireEvent.change(within(items).getAllByLabelText('Игрок')[0], { target: { value: H1 } });
  // Гостей в выборе игрока хозяев нет.
  expect(within(within(items).getAllByLabelText('Игрок')[0]).queryByText(/Сидоров/)).toBeNull();
  fireEvent.click(within(area).getByLabelText(/Весь матч просмотрен/));
  fireEvent.click(within(area).getByRole('button', { name: 'Сохранить разметку' }));
  await waitFor(() => expect(puts).toHaveLength(1));
  expect(puts[0].body).toMatchObject({ expected_revision: 3, expected_match_revision: 7, status: 'confirmed' });
  const doc = puts[0].body.document as {
    actions: { kind: string; side: string; start_ms: number; player_id: string | null }[];
    completeness: Record<string, { status: string }[]>;
  };
  expect(doc.actions.map((a) => [a.kind, a.side, a.start_ms])).toEqual([
    ['pass', 'home', 10000],
    ['shot', 'home', 393000],
    ['save', 'away', 393000],
    ['duel', 'away', 600000],
    ['duel', 'home', 600000],
    ['recovery', 'away', 600000],
  ]);
  expect(doc.actions[1].player_id).toBe(H1);
  expect(doc.completeness.shots[0].status).toBe('complete');
});

it('puts tagged goals into the protocol draft by half and time from its start', async () => {
  const { area, player, grid } = await open();
  player.currentTime = 150;
  fireEvent.keyDown(grid, { code: 'Digit4' });
  fireEvent.click(within(area).getByRole('button', { name: 'Внести голы в протокол (1)' }));
  await waitFor(() => expect(within(area).getByRole('status')).toHaveTextContent('Голы внесены'));
  expect(posts.map((p) => p.body.kind)).toEqual(['reopen', 'add_event']);
  expect(posts[1].body.expected_revision).toBe(9);
  expect(posts[1].body.payload).toMatchObject({
    event: { kind: 'goal', side: 'home', period: 1, elapsed_ms: 105000, player_id: null },
  });
});
