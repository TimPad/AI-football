import { describe, expect, it } from 'vitest';
import type { AnalysisAssignment, AnalysisRun } from '../../api/domain';
import { baseGroups, candidatesOf } from './candidates';
import { lookIndex } from './similar';
import { CONFIDENT_MARGIN, groupByPlayer, hintsFor, initialTicks, rejectKey } from './suggestions';

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
// A: 1 красный (0–40) и 4 синий (100–160) назначены; открыты 2 красный (50–90), 3 синий (0–30, виден вместе с 1),
// 5 синий (200–230), 6 без признака; 8 красный (300–340), 9 и 10 красные, видны одновременно (400–440, 410–450).
const run = {
  id: 'run',
  match_id: 'match',
  context: {
    teams: { home: { id: 't1', name: 'Север' }, away: { id: 't2', name: 'Юг' } },
    rosters: [
      { player_id: 'p1', side: 'home', display_name: 'Север · игрок 1', shirt_number: '7' },
      { player_id: 'p2', side: 'home', display_name: 'Север · игрок 2', shirt_number: null },
      { player_id: 'p3', side: 'home', display_name: 'Север · игрок 3', shirt_number: null },
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
    track(5, 'A', 200, 230, BLUE),
    track(6, 'A', 170, 175, null),
    track(7, 'B', 0, 150, RED),
    track(8, 'A', 300, 340, RED),
    track(9, 'A', 400, 440, RED),
    track(10, 'A', 410, 450, RED),
  ],
  groups: [],
} as unknown as AnalysisRun;
const index = lookIndex(run);
const candidates = candidatesOf(run, baseGroups(run));
const home = ['p1', 'p2', 'p3'];
const base: AnalysisAssignment[] = [
  { track_id: 1, player_id: 'p1' },
  { track_id: 4, player_id: 'p2' },
];
const byKey = (h: ReturnType<typeof hintsFor>) => Object.fromEntries(h.hints.map((x) => [x.candidate.key, x]));
const cand = (key: string) => candidates.filter((c) => c.key === key)[0];

describe('hints for leftover fragments', () => {
  it('gives each open candidate the most similar player who is not on court at the same time', () => {
    const result = hintsFor(index, candidates, 'A', home, base, new Set());
    const h = byKey(result);
    expect(h['2'].playerId).toBe('p1');
    expect(h['5'].playerId).toBe('p2');
    // 3 виден вместе с фрагментом 1 игрока p1: остаётся только p2, отрыв — от нуля.
    expect(h['3'].playerId).toBe('p2');
    expect(h['3'].margin).toBeCloseTo(h['3'].score, 6);
    expect(result.players).toBe(2);
    expect(Object.keys(h)).not.toContain('1');
    expect(Object.keys(h)).not.toContain('7');
  });

  it('lists candidates without a look or without a fitting player separately', () => {
    const plain = hintsFor(index, candidates, 'A', home, base, new Set());
    expect(plain.unhinted).toEqual([{ candidate: cand('6'), reason: 'no_look' }]);
    const rejected = hintsFor(index, candidates, 'A', home, base, new Set([rejectKey('p2', cand('3'))]));
    expect(rejected.unhinted).toContainEqual({ candidate: cand('3'), reason: 'no_player' });
  });

  it('moves a rejected candidate to the next most similar player', () => {
    const h = byKey(hintsFor(index, candidates, 'A', home, base, new Set([rejectKey('p1', cand('2'))])));
    expect(h['2'].playerId).toBe('p2');
  });

  it('never suggests players without fragments and follows the current assignments', () => {
    const only = byKey(hintsFor(index, candidates, 'A', home, [{ track_id: 1, player_id: 'p1' }], new Set()));
    expect(only['5'].playerId).toBe('p1');
    expect(Object.values(only).some((x) => x.playerId === 'p3')).toBe(false);
    expect(byKey(hintsFor(index, candidates, 'A', home, base, new Set()))['5'].playerId).toBe('p2');
    expect(hintsFor(index, candidates, 'A', home, [], new Set()).players).toBe(0);
  });

  it('calls a hint confident only when the best player leads by the margin', () => {
    const twins = [...base, { track_id: 8, player_id: 'p3' }];
    const result = hintsFor(index, candidates, 'A', home, twins, new Set());
    const h = byKey(result);
    // p1 и p3 одинаково красные: у красного 2 отрыв 0.
    expect(h['2'].margin).toBeCloseTo(0, 6);
    expect(h['2'].confident).toBe(false);
    expect(h['5'].confident).toBe(true);
    for (const x of result.hints) expect(x.confident).toBe(x.margin >= CONFIDENT_MARGIN);
  });

  it('pre-ticks only one of two confident candidates seen at the same time', () => {
    const result = hintsFor(index, candidates, 'A', home, base, new Set());
    const [group] = groupByPlayer(result.hints).filter((g) => g.playerId === 'p1');
    expect(group.hints.map((x) => x.candidate.key).sort()).toEqual(['10', '2', '8', '9']);
    const ticks = initialTicks(index, group.hints);
    expect(['9', '10'].filter((k) => ticks.has(k))).toHaveLength(1);
    expect(ticks.has('2') && ticks.has('8')).toBe(true);
  });

  it('orders groups by the number of hints', () => {
    const groups = groupByPlayer(hintsFor(index, candidates, 'A', home, base, new Set()).hints);
    expect(groups.map((g) => [g.playerId, g.hints.length])).toEqual([
      ['p1', 4],
      ['p2', 2],
    ]);
  });
});
