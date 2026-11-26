import { describe, expect, it } from 'vitest';
import { baseGroups, candidatesOf } from './candidates';
import { base, wideRun as run } from './identityFixtures';
import type { MatchModel } from './matchModel';
import { available, confidentHint, QUEUE_MARGIN, queueOrder, queuePlayers } from './queue';
import { lookIndex } from './similar';

const index = lookIndex(run);
const candidates = candidatesOf(run, baseGroups(run));
const rosters = run.context.rosters;
const cand = (key: string) => candidates.filter((c) => c.key === key)[0];

describe('identity queue', () => {
  it('takes open candidates of the team by start time', () => {
    expect(queueOrder(candidates, 'A', base)).toEqual(['3', '2', '6', '5', '8', '9', '10']);
  });

  it('lists players in a fixed order by shirt number, without the absent ones', () => {
    expect(queuePlayers(index, rosters, 'home', [], base).map((p) => p.id)).toEqual(['p3', 'p1', 'p2']);
    const players = queuePlayers(index, rosters, 'home', ['p3'], base);
    expect(players.map((p) => [p.key, p.label])).toEqual([
      ['1', '№7 Север · игрок 1'],
      ['2', 'Север · игрок 2'],
    ]);
  });

  it('marks a player seen together with the candidate as unavailable', () => {
    const [p1, p2] = queuePlayers(index, rosters, 'home', ['p3'], base);
    expect(available(index, p1, cand('3'))).toBe(false);
    expect(available(index, p2, cand('3'))).toBe(true);
  });

  it('gives only a confident colour hint', () => {
    const players = queuePlayers(index, rosters, 'home', [], base);
    expect(confidentHint(index, players, cand('5'))).toBe('p2');
    expect(confidentHint(index, players, cand('2'))).toBe('p1');
    expect(confidentHint(index, players, cand('6'))).toBeNull();
    // p1 и p3 одинаково красные: отрыв 0 — подсказки нет.
    const twins = queuePlayers(index, rosters, 'home', [], [...base, { track_id: 8, player_id: 'p3' }]);
    expect(confidentHint(index, twins, cand('2'))).toBeNull();
    expect(QUEUE_MARGIN).toBe(0.05);
  });
});

// Модель, которая узнаёт игрока по «своей» позиции признака SigLIP (первые 768 чисел признака кандидата).
const crafted = (classes: string[], hot: number[]): MatchModel => ({
  classes,
  w: hot.map((h) => Float64Array.from({ length: 768 + 156 }, (_, j) => (j === h ? 40 : 0))),
  b: new Float64Array(classes.length),
  mu: new Float64Array(768 + 156),
  sd: new Float64Array(768 + 156).fill(1),
});

describe('queue with a match model', () => {
  it('tells apart players of the same colour by the model', () => {
    const twins = [...base, { track_id: 8, player_id: 'p3' }];
    const players = queuePlayers(index, rosters, 'home', [], twins);
    expect(confidentHint(index, players, cand('2'))).toBeNull();
    expect(confidentHint(index, players, cand('2'), crafted(['p1', 'p3'], [1, 2]))).toBe('p1');
  });

  it('falls back to colour for a candidate without an embedding', () => {
    const players = queuePlayers(index, rosters, 'home', [], base);
    expect(confidentHint(index, players, cand('6'), crafted(['p1', 'p2'], [1, 3]))).toBeNull();
  });
});
