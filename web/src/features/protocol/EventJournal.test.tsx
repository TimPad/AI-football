import { expect, it } from 'vitest';
import { byMatchTime } from './EventJournal';

it('orders events by half and time, untimed events at the end of their half', () => {
  const e = (id: string, period: number | null, elapsed_ms: number | null) => ({ id, period, elapsed_ms });
  const sorted = byMatchTime([
    e('foul-2', 2, null),
    e('goal-1b', 1, 600000),
    e('shootout', null, null),
    e('goal-2', 2, 60000),
    e('card-1', 1, null),
    e('goal-1a', 1, 120000),
  ]);
  expect(sorted.map((x) => x.id)).toEqual(['goal-1a', 'goal-1b', 'card-1', 'goal-2', 'foul-2', 'shootout']);
});
