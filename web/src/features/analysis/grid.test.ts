import { describe, expect, it } from 'vitest';
import { baseGroups, candidatesOf } from './candidates';
import { applyClass, gridOrder, rangeKeys } from './grid';
import { base, wideRun as run } from './identityFixtures';
import type { MatchModel } from './matchModel';
import { lookIndex } from './similar';

const index = lookIndex(run);
const candidates = candidatesOf(run, baseGroups(run));
const cand = (key: string) => candidates.filter((c) => c.key === key)[0];

describe('identity grid', () => {
  it('filters by class and sorts by time or by similarity to a player', () => {
    expect(gridOrder(index, candidates, 'A', base, 'open', null)).toEqual(['3', '2', '6', '5', '8', '9', '10']);
    expect(gridOrder(index, candidates, 'A', base, 'p1', null)).toEqual(['1']);
    expect(
      gridOrder(
        index,
        candidates,
        'A',
        [...base, { track_id: 6, excluded_reason: 'Не игрок матча' }],
        'excluded',
        null,
      ),
    ).toEqual(['6']);
    // Похожие на синего p2: синие 3 и 5, затем красные по времени, без признака — в конце.
    expect(gridOrder(index, candidates, 'A', base, 'open', 'p2')).toEqual(['3', '5', '2', '8', '9', '10', '6']);
  });

  it('gives a class to the picked fragments, skipping ones seen together', () => {
    const one = applyClass(index, base, [cand('3'), cand('2')], 'p1');
    expect(one.skipped).toEqual(['3']);
    expect(one.blockedBy).toEqual({ 3: 1 });
    expect(one.next).toContainEqual({ track_id: 2, player_id: 'p1' });
    const pair = applyClass(index, base, [cand('9'), cand('10')], 'p2');
    expect(pair.skipped).toEqual(['10']);
    expect(pair.blockedBy).toEqual({ 10: 9 });
    expect(applyClass(index, base, [cand('6')], 'exclude').next).toContainEqual({
      track_id: 6,
      excluded_reason: 'Не игрок матча',
    });
    expect(applyClass(index, base, [cand('1')], '').next).toEqual([{ track_id: 4, player_id: 'p2' }]);
  });

  it('selects a range between two tiles in either direction', () => {
    const order = ['3', '2', '6', '5'];
    expect(rangeKeys(order, '3', '6')).toEqual(['3', '2', '6']);
    expect(rangeKeys(order, '6', '3')).toEqual(['3', '2', '6']);
    expect(rangeKeys(order, 'x', '5')).toEqual(['5']);
  });
});

it('orders by the model probability of the chosen player', () => {
  const model: MatchModel = {
    classes: ['p1', 'p2'],
    w: [1, 3].map((h) => Float64Array.from({ length: 768 + 156 }, (_, j) => (j === h ? 40 : 0))),
    b: new Float64Array(2),
    mu: new Float64Array(768 + 156),
    sd: new Float64Array(768 + 156).fill(1),
  };
  // Похожие на p1 по модели: 2, 9, 10 (признак «первый»), затем остальные по времени; 6 без признака — в конце.
  expect(gridOrder(index, candidates, 'A', base, 'open', 'p1', model).slice(0, 3)).toEqual(['2', '9', '10']);
  expect(gridOrder(index, candidates, 'A', base, 'open', 'p1', model).slice(-1)).toEqual(['6']);
});
