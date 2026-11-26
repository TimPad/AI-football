import type { AnalysisAssignment } from '../../api/domain';
import { type Candidate, decisionOf } from './candidates';
import { clash, cosine, type Look, type LookIndex, meanLook } from './similar';

// Подсказки для оставшихся фрагментов: каждому неназначенному кандидату команды — самый похожий по цвету формы
// игрок из тех, у кого уже есть фрагменты и кто не виден одновременно с кандидатом. Замер 26.11.2026 на матче
// ВШЭ Ю — JWH (docs/superpowers/specs/2026-11-26-identity-suggestions-design.md): верно 83%, при отрыве лучшего
// игрока от второго ≥ 0,03 — 93%. Решает человек: подсказка только отмечает и упорядочивает.

export const CONFIDENT_MARGIN = 0.03;

export type Hint = { candidate: Candidate; playerId: string; score: number; margin: number; confident: boolean };
export type Unhinted = { candidate: Candidate; reason: 'no_look' | 'no_player' };
export type Hints = { hints: Hint[]; unhinted: Unhinted[]; players: number };

// Отклонение «Не он» — пара игрок и кандидат.
export const rejectKey = (playerId: string, candidate: Candidate) => `${playerId}|${candidate.key}`;

export function hintsFor(
  index: LookIndex,
  candidates: Candidate[],
  team: 'A' | 'B',
  playerIds: string[],
  assignments: AnalysisAssignment[],
  rejected: Set<string>,
): Hints {
  // Игроки с фрагментами и признаком цвета: по ним строится средний признак.
  const players: { id: string; own: number[]; mean: Look }[] = [];
  for (const id of playerIds) {
    const own = assignments.filter((a) => a.player_id === id).map((a) => a.track_id);
    const mean = own.length ? meanLook(index, own) : null;
    if (mean) players.push({ id, own, mean });
  }
  const hints: Hint[] = [];
  const unhinted: Unhinted[] = [];
  if (!players.length) return { hints, unhinted, players: 0 };
  for (const candidate of candidates) {
    if (candidate.team !== team || decisionOf(assignments, candidate.trackIds).kind !== 'none') continue;
    const look = meanLook(index, candidate.trackIds);
    if (!look) {
      unhinted.push({ candidate, reason: 'no_look' });
      continue;
    }
    const scored = players
      .filter((p) => !rejected.has(rejectKey(p.id, candidate)) && !clash(index, p.own, candidate.trackIds))
      .map((p) => ({ id: p.id, score: cosine(p.mean, look) }))
      .sort((a, b) => b.score - a.score);
    if (!scored.length) {
      unhinted.push({ candidate, reason: 'no_player' });
      continue;
    }
    const margin = scored[0].score - (scored[1]?.score ?? 0);
    hints.push({
      candidate,
      playerId: scored[0].id,
      score: scored[0].score,
      margin,
      confident: margin >= CONFIDENT_MARGIN,
    });
  }
  return { hints, unhinted, players: players.length };
}

// Группы подсказок по игроку: больше подсказок — выше; внутри — по убыванию похожести.
export function groupByPlayer(hints: Hint[]): { playerId: string; hints: Hint[] }[] {
  const groups = new Map<string, Hint[]>();
  for (const h of hints) groups.set(h.playerId, [...(groups.get(h.playerId) ?? []), h]);
  return [...groups.entries()]
    .map(([playerId, list]) => ({ playerId, hints: [...list].sort((a, b) => b.score - a.score) }))
    .sort((a, b) => b.hints.length - a.hints.length || a.playerId.localeCompare(b.playerId));
}

// Отмеченные сразу: уверенные подсказки игрока по убыванию похожести, кроме видных одновременно с уже отмеченными.
// «Отметить все» берёт и сомнительные (onlyConfident = false) — с тем же запретом одновременных.
export function initialTicks(index: LookIndex, hints: Hint[], onlyConfident = true): Set<string> {
  const keys = new Set<string>();
  const ticked: number[] = [];
  for (const h of [...hints].sort((a, b) => b.score - a.score)) {
    if ((onlyConfident && !h.confident) || (ticked.length && clash(index, ticked, h.candidate.trackIds))) continue;
    keys.add(h.candidate.key);
    ticked.push(...h.candidate.trackIds);
  }
  return keys;
}
