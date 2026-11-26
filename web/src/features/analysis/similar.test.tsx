import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { AnalysisRun } from '../../api/domain';
import { baseGroups, candidatesOf, dropConflicts, identityConflicts, intervalsClash } from './candidates';
import { IdentityReview } from './IdentityReview';
import { assignedShare, cosine, decodeLook, lookIndex, suggest } from './similar';

// Признак цвета из пакета: 156 байт в base64; здесь — «красная» и «синяя» форма.
const look = (hot: number) =>
  btoa(String.fromCharCode(...Array.from({ length: 156 }, (_, i) => (i === hot ? 255 : 8))));
const RED = look(0);
const BLUE = look(40);
const track = (id: number, team: string, from: number, to: number, appearance: string | null) => ({
  track_id: id,
  team,
  role: 'player',
  intervals: [[from, to]],
  thumb: `thumbs/${id}.jpg`,
  has_metrics: true,
  appearance,
});
// A: 1 (0–40, красный), 2 (50–90, красный), 3 (0–30, синий, виден вместе с 1), 4 (100–160, синий), 6 без признака.
const run = {
  job_id: 'job',
  match_id: 'match',
  id: 'run',
  revision: 0,
  status: 'review',
  context: {
    teams: { home: { id: 't1', name: 'Север' }, away: { id: 't2', name: 'Юг' } },
    rosters: [
      { player_id: 'p1', side: 'home', display_name: 'Север · игрок 1', shirt_number: null },
      { player_id: 'p2', side: 'home', display_name: 'Север · игрок 2', shirt_number: null },
      { player_id: 'p9', side: 'away', display_name: 'Юг · игрок 1', shirt_number: null },
    ],
  },
  side_map: { A: 'home', B: 'away' },
  assignments: [],
  tracks: [
    track(1, 'A', 0, 40, RED),
    track(2, 'A', 50, 90, RED),
    track(3, 'A', 0, 30, BLUE),
    track(4, 'A', 100, 160, BLUE),
    track(5, 'B', 0, 150, RED),
    track(6, 'A', 170, 175, null),
  ],
  groups: [],
} as unknown as AnalysisRun;
const index = lookIndex(run);
const candidates = candidatesOf(run, baseGroups(run));
const keys = (list: ReturnType<typeof suggest>) => list.map((s) => s.candidate.key);
beforeEach(() => localStorage.clear());

describe('similar fragments', () => {
  it('decodes the package appearance to a unit vector', () => {
    const v = decodeLook(RED);
    expect(v).toHaveLength(156);
    expect(cosine(v, v)).toBeCloseTo(1, 6);
    expect(cosine(v, decodeLook(BLUE))).toBeLessThan(0.5);
  });

  it('starts with the longest open fragments, then ranks by similarity without simultaneous ones', () => {
    const start = keys(suggest(index, candidates, 'A', [], [], new Set(), 3));
    expect(start[0]).toBe('4'); // 60 с, дальше 1 и 2 по 40 с
    expect(start.slice(1).sort()).toEqual(['1', '2']);
    // У игрока фрагмент 1: 3 виден одновременно — его нет; красный 2 выше синего 4, без признака — в конце.
    const ranked = suggest(index, candidates, 'A', [1], [{ track_id: 1, player_id: 'p1' }], new Set(), 10);
    expect(keys(ranked)).toEqual(['2', '4', '6']);
    expect(ranked[0].score).toBeCloseTo(1, 3);
    expect(ranked[2].score).toBeNull();
    // Отклонённые для игрока и уже назначенные не предлагаются.
    expect(keys(suggest(index, candidates, 'A', [1], [{ track_id: 1, player_id: 'p1' }], new Set(['2']), 10))).toEqual([
      '4',
      '6',
    ]);
  });

  it('counts the share of team time already given to players', () => {
    expect(assignedShare(candidates, 'A', [{ track_id: 4, player_id: 'p1' }])).toBeCloseTo(60 / 175);
  });

  it('adds marked fragments to the chosen player and saves them as track assignments', async () => {
    const save = vi.fn().mockResolvedValue(undefined);
    render(
      <MemoryRouter>
        <IdentityReview run={run} actorId="admin" editable onSave={save} />
      </MemoryRouter>,
    );
    expect(screen.getByRole('button', { name: 'Подбор' })).toHaveAttribute('aria-pressed', 'true');
    const picker = screen.getByRole('region', { name: 'Подбор похожих фрагментов' });
    expect(within(picker).getByLabelText('Игрок')).toHaveValue('p1');
    // Начало: самый длинный фрагмент (4, синий) — это игрок 1.
    const first = within(picker).getByRole('listitem', { name: 'Фрагмент 1:40–2:40' });
    fireEvent.click(within(first).getByRole('button', { name: 'Он' }));
    fireEvent.click(within(picker).getByRole('button', { name: 'Добавить отмеченных (1)' }));
    // Теперь подсказки по похожести: синий 3 первым, «не он» для красного 2.
    const cards = within(picker)
      .getAllByRole('listitem')
      .filter((li) => li.className.includes('similar-card'));
    expect(cards[0]).toHaveAccessibleName('Фрагмент 0:00–0:30');
    expect(within(picker).getByLabelText('Игрок')).toHaveValue('p1');
    fireEvent.click(within(cards[0]).getByRole('button', { name: 'Он' }));
    // 1 виден одновременно с отмеченным 3 — отметить его «он» нельзя.
    const one = within(picker).getByRole('listitem', { name: 'Фрагмент 0:00–0:40' });
    expect(within(one).getByRole('button', { name: 'Он' })).toBeDisabled();
    fireEvent.click(
      within(picker).getByRole('listitem', { name: 'Фрагмент 0:50–1:30' }).querySelector('button + button')!,
    );
    fireEvent.click(within(picker).getByRole('button', { name: 'Добавить отмеченных (1)' }));
    expect(within(picker).queryByRole('listitem', { name: 'Фрагмент 0:50–1:30' })).toBeNull();
    expect(within(picker).getByRole('status', { name: 'Назначено времени команды' })).toHaveTextContent('51%');
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить сопоставление' }));
    await vi.waitFor(() => expect(save).toHaveBeenCalled());
    expect(save.mock.calls[0][0].assignments).toEqual([
      { track_id: 4, player_id: 'p1' },
      { track_id: 3, player_id: 'p1' },
    ]);
  });
});

describe('marking all suggestions at once', () => {
  it('marks every suggestion as him, skipping ones seen together, or as not him', () => {
    render(
      <MemoryRouter>
        <IdentityReview
          run={{ ...run, assignments: [{ track_id: 4, player_id: 'p1' }] }}
          actorId="admin"
          editable
          onSave={vi.fn()}
        />
      </MemoryRouter>,
    );
    const picker = screen.getByRole('region', { name: 'Подбор похожих фрагментов' });
    fireEvent.change(within(picker).getByLabelText('Игрок'), { target: { value: 'p1' } });
    // Синий 3 (0:00–0:30) первым; красный 1 виден одновременно с ним — «он» ему не ставится.
    fireEvent.click(within(picker).getByRole('button', { name: 'Все — он' }));
    expect(within(picker).getByRole('button', { name: 'Добавить отмеченных (3)' })).toBeEnabled();
    const one = within(picker).getByRole('listitem', { name: 'Фрагмент 0:00–0:40' });
    expect(within(one).getByRole('button', { name: 'Он' })).toBeDisabled();
    fireEvent.click(within(picker).getByRole('button', { name: 'Все — не он' }));
    for (const card of within(picker)
      .getAllByRole('listitem')
      .filter((li) => li.className.includes('similar-card')))
      expect(within(card).getByRole('button', { name: 'Не он' })).toHaveAttribute('aria-pressed', 'true');
    // Только «не он» — кнопка всё равно применяет отметки: отклонённые уходят из подсказок игрока.
    fireEvent.click(within(picker).getByRole('button', { name: 'Добавить отмеченных (0)' }));
    expect(
      within(picker)
        .queryAllByRole('listitem')
        .filter((li) => li.className.includes('similar-card')),
    ).toEqual([]);
  });
});

describe('simultaneous fragments of one player', () => {
  it('treats a short tracker duplicate inside a long fragment as a clash, like the server', () => {
    // 0,7 с внутри 49 с: пересечение меньше секунды, но начинается за 40 с до конца — сервер отклонит.
    expect(intervalsClash([[1670, 1719.5]], [[1678.2, 1678.9]])).toBe(true);
    // Передача между треками: новый начинается за 0,5 с до конца прежнего — один человек.
    expect(intervalsClash([[0, 10]], [[9.5, 20]])).toBe(false);
    expect(intervalsClash([[0, 10]], [[12, 20]])).toBe(false);
  });

  it('drops the shorter fragment of each clashing pair from the draft', () => {
    const nested = {
      ...run,
      tracks: [...run.tracks, { ...run.tracks[0], track_id: 7, intervals: [[60, 61]], appearance: RED }],
    } as AnalysisRun;
    // 2 (50–90 с) и 7 (60–61 с) у одного игрока: снимается 7.
    const draft = [
      { track_id: 2, player_id: 'p1' },
      { track_id: 7, player_id: 'p1' },
      { track_id: 4, player_id: 'p1' },
    ];
    expect(identityConflicts(nested, draft)).toEqual([{ playerId: 'p1', keep: 2, drop: 7 }]);
    expect(dropConflicts(nested, draft)).toEqual([
      { track_id: 2, player_id: 'p1' },
      { track_id: 4, player_id: 'p1' },
    ]);
  });

  it('warns about conflicts in the draft and fixes them with one button', () => {
    const nested = {
      ...run,
      tracks: [...run.tracks, { ...run.tracks[0], track_id: 7, intervals: [[60, 61]], appearance: RED }],
      assignments: [
        { track_id: 2, player_id: 'p1' },
        { track_id: 7, player_id: 'p1' },
      ],
    } as AnalysisRun;
    render(
      <MemoryRouter>
        <IdentityReview run={nested} actorId="admin" editable onSave={vi.fn()} />
      </MemoryRouter>,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('видные одновременно: 1 пара');
    fireEvent.click(screen.getByRole('button', { name: 'Снять более короткие (1)' }));
    expect(screen.queryByRole('alert')).toBeNull();
  });
});
