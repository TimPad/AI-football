import type { Action, ActionDoc } from './types';

// Разметка ударов и защиты по видео: отметка — момент записи, сторона и вид; из неё собираются действия версии.
// Удар в створ без гола — сейв соперника, заблокированный — блок соперника, отбор — выигранное единоборство,
// проигранное у соперника и возврат мяча, перехват — возврат мяча. Гол — официальный факт протокола: в разметке
// он «связь с официальным голом» и, если гол есть в протоколе, связывается с ним по порядку у своей стороны.
export type Side = 'home' | 'away';
export type TagKind = 'on_target' | 'off_target' | 'blocked' | 'goal' | 'tackle' | 'interception';
export type Tag = { id: string; kind: TagKind; side: Side; ms: number; playerId: string | null; xy: number[] | null };
export type Link = NonNullable<ActionDoc['links']>[number];
export type ProtocolGoal = { id: string; side: Side; period: number | null; elapsed_ms: number | null };

export const TAG_KINDS: TagKind[] = ['on_target', 'off_target', 'blocked', 'goal', 'tackle', 'interception'];
export const TAG_LABEL: Record<TagKind, string> = {
  on_target: 'Удар в створ',
  off_target: 'Удар мимо',
  blocked: 'Удар заблокирован',
  goal: 'Гол',
  tackle: 'Отбор',
  interception: 'Перехват',
};
export const SHOT_TAGS = new Set<TagKind>(['on_target', 'off_target', 'blocked', 'goal']);
export const TAGGED_CATEGORIES = ['shots', 'saves', 'shot_blocks', 'duels', 'recoveries'] as const;
// Метки в заметке действия: по ним разметка узнаёт свои действия в сохранённой версии.
export const TAG_NOTE = 'Разметка по видео';
export const LINKED_NOTE = 'Разметка по видео · связанное действие';

const other = (side: Side): Side => (side === 'home' ? 'away' : 'home');

export function blankAction(id: string, kind: Action['kind'], side: Side, ms: number, notes = TAG_NOTE): Action {
  return {
    id,
    kind,
    player_id: null,
    recipient_id: null,
    opponent_id: null,
    side,
    role: null,
    start_ms: ms,
    end_ms: ms,
    success: null,
    on_target: null,
    outcome: 'unknown',
    possession_id: null,
    start_xy: null,
    end_xy: null,
    attacking_direction: 'unknown',
    penalty_conceded: false,
    source_episode_id: null,
    source_video_ms: null,
    shot_id: null,
    decision: 'accepted',
    review: null,
    notes,
  };
}

// Отметки из сохранённой версии: главные действия разметки (связанные собираются заново при сохранении).
export function tagsFromDoc(doc: ActionDoc): Tag[] {
  const out: Tag[] = [];
  for (const a of doc.actions ?? []) {
    if (a.notes !== TAG_NOTE || a.start_ms == null || (a.side !== 'home' && a.side !== 'away')) continue;
    const kind: TagKind | null =
      a.kind === 'goal_candidate'
        ? 'goal'
        : a.kind === 'shot'
          ? a.outcome === 'saved'
            ? 'on_target'
            : a.outcome === 'off_target'
              ? 'off_target'
              : 'blocked'
          : a.kind === 'duel' && a.success
            ? 'tackle'
            : a.kind === 'recovery'
              ? 'interception'
              : null;
    if (kind) out.push({ id: a.id, kind, side: a.side, ms: a.start_ms, playerId: a.player_id, xy: a.start_xy });
  }
  return out.sort((a, b) => a.ms - b.ms);
}

const byClock = (a: ProtocolGoal, b: ProtocolGoal) =>
  (a.period ?? 99) - (b.period ?? 99) || (a.elapsed_ms ?? Number.MAX_SAFE_INTEGER) - (b.elapsed_ms ?? 0);

// Новый документ версии: прежние действия разметки заменяются, остальные (передачи, проверка) сохраняются.
export function buildDoc(
  base: ActionDoc,
  tags: Tag[],
  protocolGoals: ProtocolGoal[],
  complete: boolean,
  newId: () => string,
): { doc: ActionDoc; linkedGoals: number } {
  const mine = (a: Action) => a.notes === TAG_NOTE || a.notes === LINKED_NOTE;
  const removed = new Set((base.actions ?? []).filter(mine).map((a) => a.id));
  const actions = (base.actions ?? []).filter((a) => !mine(a));
  const links: Link[] = (base.links ?? []).filter((l) => !removed.has(l.source_event_id));
  const goals = { home: protocolGoals.filter((g) => g.side === 'home').sort(byClock), away: [] as ProtocolGoal[] };
  goals.away = protocolGoals.filter((g) => g.side === 'away').sort(byClock);
  const used = { home: 0, away: 0 };
  let linkedGoals = 0;
  for (const t of [...tags].sort((a, b) => a.ms - b.ms)) {
    const main = (kind: Action['kind']) => ({
      ...blankAction(t.id, kind, t.side, t.ms),
      player_id: t.playerId,
      start_xy: SHOT_TAGS.has(t.kind) ? t.xy : null,
    });
    const linked = (kind: Action['kind'], side: Side) => blankAction(newId(), kind, side, t.ms, LINKED_NOTE);
    if (t.kind === 'on_target') {
      actions.push({ ...main('shot'), on_target: true, outcome: 'saved' });
      actions.push({ ...linked('save', other(t.side)), success: true, outcome: 'success' });
    } else if (t.kind === 'off_target') {
      actions.push({ ...main('shot'), on_target: false, outcome: 'off_target' });
    } else if (t.kind === 'blocked') {
      actions.push({ ...main('shot'), outcome: 'failure' });
      actions.push({ ...linked('shot_block', other(t.side)), shot_id: t.id });
    } else if (t.kind === 'goal') {
      const target = goals[t.side][used[t.side]++];
      // Автор гола — из протокола: разметка его не переписывает.
      actions.push({ ...main('goal_candidate'), player_id: target ? null : t.playerId });
      if (target) {
        links.push({ kind: 'canonical', canonical_event_id: target.id, source_event_id: t.id });
        linkedGoals++;
      }
    } else if (t.kind === 'tackle') {
      actions.push({ ...main('duel'), success: true, outcome: 'success' });
      actions.push({ ...linked('duel', other(t.side)), success: false, outcome: 'failure' });
      actions.push(linked('recovery', t.side));
    } else {
      actions.push(main('recovery'));
    }
  }
  const coverage = [{ status: complete ? 'complete' : 'partial', intervals: null, player_ids: null }] as const;
  const completeness = { ...(base.completeness ?? {}) } as NonNullable<ActionDoc['completeness']>;
  for (const c of TAGGED_CATEGORIES) completeness[c] = coverage.map((x) => ({ ...x }));
  return { doc: { ...base, actions, links, completeness }, linkedGoals };
}

// Тайм и минута матча по времени записи: интервалы таймов на видео и длительности таймов регламента.
export function matchClock(halves: number[][], periodsS: number[], ms: number) {
  const s = ms / 1000;
  let index = halves.findIndex(([a, b]) => a <= s && s <= b);
  if (index < 0) index = Math.max(0, halves.filter(([a]) => a <= s).length - 1);
  const [start, end] = halves[index] ?? [0, Number.MAX_SAFE_INTEGER];
  const elapsedMs = Math.round(Math.max(0, Math.min(s, end) - start) * 1000);
  const offset = periodsS.slice(0, index).reduce((a, b) => a + b, 0);
  const inside = halves.some(([a, b]) => a <= s && s <= b);
  return {
    period: index + 1,
    elapsedMs,
    minute: `${Math.floor(offset / 60) + Math.floor(elapsedMs / 60000) + 1}'`,
    inside,
  };
}

// Голы разметки для черновика протокола: сторона, тайм, время от начала тайма и автор, если выбран.
export function protocolGoals(tags: Tag[], halves: number[][], periodsS: number[], newId: () => string) {
  return tags
    .filter((t) => t.kind === 'goal')
    .sort((a, b) => a.ms - b.ms)
    .map((t) => {
      const c = matchClock(halves, periodsS, t.ms);
      return {
        id: newId(),
        kind: 'goal' as const,
        side: t.side,
        period: c.period,
        elapsed_ms: Math.min(c.elapsedMs, (periodsS[c.period - 1] ?? 0) * 1000),
        player_id: t.playerId,
      };
    });
}
