import type { AnalysisAssignment } from '../../api/domain';
import { assignGroup, type Candidate, decisionOf } from './candidates';
import { candidateFeature, type MatchModel, probabilityOf } from './matchModel';
import { clash, cosine, type LookIndex, meanLook } from './similar';

export const PAGE_TILES = 60;

// Плитка сетки: кандидаты команды выбранного класса — 'open' (неназначенные), 'excluded', 'all' или id игрока;
// по времени или по похожести на игрока (similarTo). Снимок — порядок меняется только по действию человека.
export function gridOrder(
  index: LookIndex,
  candidates: Candidate[],
  team: 'A' | 'B',
  assignments: AnalysisAssignment[],
  show: string,
  similarTo: string | null,
  model?: MatchModel | null,
): string[] {
  const keep = candidates.filter((c) => {
    if (c.team !== team) return false;
    const d = decisionOf(assignments, c.trackIds);
    if (show === 'open') return d.kind === 'none';
    if (show === 'excluded') return d.kind === 'excluded';
    if (show === 'all') return true;
    return d.kind === 'player' && d.playerId === show;
  });
  const byTime = (a: Candidate, b: Candidate) => a.span[0] - b.span[0] || a.key.localeCompare(b.key);
  if (!similarTo) return [...keep].sort(byTime).map((c) => c.key);
  const own = assignments.filter((a) => a.player_id === similarTo).map((a) => a.track_id);
  const mean = own.length ? meanLook(index, own) : null;
  const target = similarTo;
  const score = (c: Candidate) => {
    const x = model ? candidateFeature(index, c) : null;
    if (model && x && model.classes.includes(target)) return probabilityOf(model, x, target);
    const look = meanLook(index, c.trackIds);
    return mean && look ? cosine(mean, look) : -2;
  };
  return [...keep].sort((a, b) => score(b) - score(a) || byTime(a, b)).map((c) => c.key);
}

// Присвоить класс: id игрока, 'exclude' или '' (снять). Класс игрока не получают кадры, видные одновременно с его
// остальными фрагментами или с более ранним кадром той же операции (правило сервера, больше 1 с).
export function applyClass(
  index: LookIndex,
  assignments: AnalysisAssignment[],
  picked: Candidate[],
  value: string,
): { next: AnalysisAssignment[]; skipped: string[] } {
  const player = value !== '' && value !== 'exclude';
  const pickedIds = new Set(picked.flatMap((c) => c.trackIds));
  const taken = player
    ? assignments.filter((a) => a.player_id === value && !pickedIds.has(a.track_id)).map((a) => a.track_id)
    : [];
  let next = assignments;
  const skipped: string[] = [];
  for (const c of picked) {
    if (player && taken.length && clash(index, taken, c.trackIds)) {
      skipped.push(c.key);
      continue;
    }
    if (player) taken.push(...c.trackIds);
    next = assignGroup(next, c.trackIds, value);
  }
  return { next, skipped };
}

// Диапазон выделения Shift + щелчок: от якоря до кадра включительно, в любую сторону.
export function rangeKeys(order: string[], from: string, to: string): string[] {
  const i = order.indexOf(from);
  const j = order.indexOf(to);
  if (i < 0 || j < 0) return [to];
  return order.slice(Math.min(i, j), Math.max(i, j) + 1);
}
