import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { AnalysisRun } from '../../api/domain';
import { dropConflicts, identityConflicts, intervalsClash } from './candidates';
import { IdentityReview } from './IdentityReview';
import { cosine, decodeLook } from './similar';

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
beforeEach(() => localStorage.clear());

describe('similar fragments', () => {
  it('decodes the package appearance to a unit vector', () => {
    const v = decodeLook(RED);
    expect(v).toHaveLength(156);
    expect(cosine(v, v)).toBeCloseTo(1, 6);
    expect(cosine(v, decodeLook(BLUE))).toBeLessThan(0.5);
  });
});

describe('simultaneous fragments of one player', () => {
  it('treats a short tracker duplicate inside a long fragment as a clash, like the server', () => {
    // 0,7 с внутри 49 с: пересечение меньше секунды, но начинается за 40 с до конца — сервер отклонит.
    expect(intervalsClash([[1670, 1719.5]], [[1678.2, 1678.9]])).toBe(true);
    // Передача между треками: новый начинается за 0,5 с до конца прежнего — один человек.
    expect(intervalsClash([[0, 10]], [[9.5, 20]])).toBe(false);
    expect(intervalsClash([[0, 10]], [[12, 20]])).toBe(false);
    // До 3 с перекрытия — та же передача (ВШЭ Ю — JWH: 2,0 с); больше — два человека.
    expect(intervalsClash([[790, 841.7]], [[839.7, 861.4]])).toBe(false);
    expect(intervalsClash([[0, 10]], [[6.5, 20]])).toBe(true);
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
