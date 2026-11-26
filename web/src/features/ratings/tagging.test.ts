import { describe, expect, it } from 'vitest';
import {
  blankAction,
  buildDoc,
  LINKED_NOTE,
  matchClock,
  protocolGoals,
  TAG_NOTE,
  type Tag,
  tagsFromDoc,
} from './tagging';
import type { ActionDoc } from './types';

const pass = { ...blankAction('p1', 'pass', 'home', 5000, ''), success: true, outcome: 'success' as const };
const base = {
  clock_basis: 'video',
  analysis_scope: 'full_match',
  duration_ms: 2_600_000,
  actions: [pass],
  links: [],
  completeness: { passes: [{ status: 'partial', intervals: null, player_ids: null }] },
  notes: '',
} as unknown as ActionDoc;
const tag = (id: string, kind: Tag['kind'], side: Tag['side'], ms: number, extra: Partial<Tag> = {}): Tag => ({
  id,
  kind,
  side,
  ms,
  playerId: null,
  xy: null,
  ...extra,
});
let n = 0;
const newId = () => `id-${++n}`;

describe('video tagging', () => {
  it('turns tags into actions with their counterparts and declares tagged categories', () => {
    const tags = [
      tag('a', 'on_target', 'home', 60_000, { xy: [30, 10], playerId: 'h7' }),
      tag('b', 'blocked', 'away', 90_000),
      tag('c', 'tackle', 'away', 120_000),
      tag('d', 'interception', 'home', 150_000),
      tag('e', 'off_target', 'home', 170_000),
    ];
    const { doc } = buildDoc(base, tags, [], true, newId);
    const brief = doc.actions!.map((a) => [a.kind, a.side, a.start_ms, a.success, a.outcome, a.notes === TAG_NOTE]);
    expect(brief).toEqual([
      ['pass', 'home', 5000, true, 'success', false], // передачи остаются
      ['shot', 'home', 60000, null, 'saved', true],
      ['save', 'away', 60000, true, 'success', false],
      ['shot', 'away', 90000, null, 'failure', true],
      ['shot_block', 'home', 90000, null, 'unknown', false],
      ['duel', 'away', 120000, true, 'success', true],
      ['duel', 'home', 120000, false, 'failure', false],
      ['recovery', 'away', 120000, null, 'unknown', false],
      ['recovery', 'home', 150000, null, 'unknown', true],
      ['shot', 'home', 170000, null, 'off_target', true],
    ]);
    const shot = doc.actions!.find((a) => a.id === 'a')!;
    expect([shot.on_target, shot.start_xy, shot.player_id]).toEqual([true, [30, 10], 'h7']);
    expect(doc.actions!.find((a) => a.kind === 'shot_block')!.shot_id).toBe('b');
    expect(Object.keys(doc.completeness!).sort()).toEqual(
      ['duels', 'passes', 'recoveries', 'saves', 'shot_blocks', 'shots'].sort(),
    );
    expect(doc.completeness!.shots![0].status).toBe('complete');
    // Сохранённую разметку можно открыть снова: отметки восстанавливаются, связанные действия — нет.
    expect(tagsFromDoc(doc)).toEqual(tags);
    expect(doc.actions!.filter((a) => a.notes === LINKED_NOTE)).toHaveLength(4);
  });

  it('replaces its own earlier actions and links goals to protocol goals by order', () => {
    const first = buildDoc(base, [tag('g1', 'goal', 'home', 70_000)], [], false, newId).doc;
    expect(first.actions!.find((a) => a.id === 'g1')!.kind).toBe('goal_candidate');
    expect(first.links).toEqual([]);
    const goals = [
      { id: 'pg2', side: 'home' as const, period: 2, elapsed_ms: 1000 },
      { id: 'pg1', side: 'home' as const, period: 1, elapsed_ms: 50_000 },
    ];
    const tags = [tag('g1', 'goal', 'home', 70_000, { playerId: 'h7' }), tag('g2', 'goal', 'home', 1_400_000)];
    const { doc, linkedGoals } = buildDoc(first, tags, goals, false, newId);
    expect(doc.actions!.filter((a) => a.kind === 'goal_candidate').map((a) => a.id)).toEqual(['g1', 'g2']);
    expect(doc.links!.map((l) => [l.source_event_id, l.canonical_event_id])).toEqual([
      ['g1', 'pg1'],
      ['g2', 'pg2'],
    ]);
    // Автор гола — из протокола.
    expect(doc.actions!.find((a) => a.id === 'g1')!.player_id).toBeNull();
    expect(linkedGoals).toBe(2);
    expect(doc.completeness!.shots![0].status).toBe('partial');
  });

  it('maps video time to half and match minute and builds protocol goals', () => {
    const halves = [
      [45, 1250],
      [1375, 2590],
    ];
    expect(matchClock(halves, [1200, 1200], 159_000)).toMatchObject({ period: 1, elapsedMs: 114_000, minute: "2'" });
    expect(matchClock(halves, [1200, 1200], 1_542_500)).toMatchObject({ period: 2, minute: "23'", inside: true });
    // В перерыве — конец первого тайма.
    expect(matchClock(halves, [1200, 1200], 1_300_000)).toMatchObject({ period: 1, inside: false });
    const goals = protocolGoals(
      [tag('x', 'goal', 'away', 1_542_500, { playerId: 'a9' }), tag('y', 'on_target', 'home', 1000)],
      halves,
      [1200, 1200],
      newId,
    );
    expect(goals.map((g) => [g.kind, g.side, g.period, g.elapsed_ms, g.player_id])).toEqual([
      ['goal', 'away', 2, 167_500, 'a9'],
    ]);
  });
});
