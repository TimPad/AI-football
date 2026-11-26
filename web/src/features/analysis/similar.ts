import type { AnalysisAssignment, AnalysisRun } from '../../api/domain';
import { type Candidate, decisionOf, intervalsClash } from './candidates';

// Подбор похожих фрагментов игроку. Похожесть — косинус признаков цвета одежды и обуви из пакета
// (perception.appearance: 156 байт 0..255 в base64). Сборка людей по ней не прошла проверку
// (docs/2026-11-23-people-clustering.md), поэтому она только упорядочивает подсказки — решает человек.

type Track = AnalysisRun['tracks'][number];
export type Look = Float64Array;
export type Suggestion = { candidate: Candidate; score: number | null };

const seconds = (t: Track) => t.intervals.reduce((s, [a, b]) => s + b - a, 0);

export function decodeLook(text: string): Look {
  const bin = atob(text);
  const v = new Float64Array(bin.length);
  let norm = 0;
  for (let i = 0; i < bin.length; i++) {
    v[i] = bin.charCodeAt(i) / 255;
    norm += v[i] * v[i];
  }
  norm = Math.sqrt(norm) || 1;
  return v.map((x) => x / norm);
}

export function cosine(a: Look, b: Look): number {
  let s = 0;
  for (let i = 0; i < a.length; i++) s += a[i] * b[i];
  return s;
}

// Индекс прогона для подбора: фрагменты по номеру и раскодированные признаки (считаются один раз).
export function lookIndex(run: AnalysisRun) {
  const tracks = new Map(run.tracks.map((t) => [t.track_id, t]));
  const looks = new Map<number, Look>();
  for (const t of run.tracks) if (t.appearance) looks.set(t.track_id, decodeLook(t.appearance));
  return { tracks, looks };
}
export type LookIndex = ReturnType<typeof lookIndex>;

// Средний признак фрагментов с весом по времени на площадке; без признаков — null.
export function meanLook(index: LookIndex, ids: number[]): Look | null {
  let out: Look | null = null;
  let total = 0;
  for (const id of ids) {
    const v = index.looks.get(id);
    const t = index.tracks.get(id);
    if (!v || !t) continue;
    const w = seconds(t);
    if (!out) out = new Float64Array(v.length);
    for (let i = 0; i < v.length; i++) out[i] += v[i] * w;
    total += w;
  }
  if (!out || total <= 0) return null;
  const norm = Math.sqrt(cosine(out, out)) || 1;
  return out.map((x) => x / norm);
}

// Одновременно видны — разные люди (правило сервера, candidates.intervalsClash).
export function clash(index: LookIndex, a: number[], b: number[]): boolean {
  const spans = (ids: number[]) => ids.flatMap((id) => index.tracks.get(id)?.intervals ?? []);
  return intervalsClash(spans(a), spans(b));
}

// Подсказки игроку: неназначенные кандидаты его команды, не видные одновременно с его фрагментами и не отклонённые
// для него, по убыванию похожести. Без фрагментов у игрока — самые длинные неназначенные: с них начинается подбор.
export function suggest(
  index: LookIndex,
  candidates: Candidate[],
  team: 'A' | 'B',
  own: number[],
  assignments: AnalysisAssignment[],
  rejected: Set<string>,
  limit: number,
): Suggestion[] {
  const open = candidates.filter(
    (c) => c.team === team && !rejected.has(c.key) && decisionOf(assignments, c.trackIds).kind === 'none',
  );
  const byTime = (a: Suggestion, b: Suggestion) => b.candidate.seconds - a.candidate.seconds;
  if (!own.length)
    return open
      .map((candidate) => ({ candidate, score: null }))
      .sort(byTime)
      .slice(0, limit);
  const mine = meanLook(index, own);
  return open
    .filter((c) => !clash(index, own, c.trackIds))
    .map((candidate) => {
      const look = meanLook(index, candidate.trackIds);
      return { candidate, score: mine && look ? cosine(mine, look) : null };
    })
    .sort((a, b) => (b.score ?? -1) - (a.score ?? -1) || byTime(a, b))
    .slice(0, limit);
}

// Доля игрового времени команды, уже отданная игрокам.
export function assignedShare(candidates: Candidate[], team: 'A' | 'B', assignments: AnalysisAssignment[]): number {
  const mine = candidates.filter((c) => c.team === team);
  const total = mine.reduce((s, c) => s + c.seconds, 0);
  const done = mine
    .filter((c) => decisionOf(assignments, c.trackIds).kind === 'player')
    .reduce((s, c) => s + c.seconds, 0);
  return total ? done / total : 0;
}
