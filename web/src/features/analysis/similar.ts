import type { AnalysisRun } from '../../api/domain';
import { intervalsClash } from './candidates';

// Подбор похожих фрагментов игроку. Похожесть — косинус признаков цвета одежды и обуви из пакета
// (perception.appearance: 156 байт 0..255 в base64). Сборка людей по ней не прошла проверку
// (docs/2026-11-23-people-clustering.md), поэтому она только упорядочивает подсказки — решает человек.

type Track = AnalysisRun['tracks'][number];
export type Look = Float64Array;

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

// Признак SigLIP 2 из пакета: 768 байт со знаком (−127…127) в base64, обратно в нормированный вектор.
export function decodeEmbedding(text: string): Look {
  const bin = atob(text);
  const v = new Float64Array(bin.length);
  let norm = 0;
  for (let i = 0; i < bin.length; i++) {
    const b = bin.charCodeAt(i);
    v[i] = (b > 127 ? b - 256 : b) / 127;
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
  const embeds = new Map<number, Look>();
  for (const t of run.tracks) {
    if (t.appearance) looks.set(t.track_id, decodeLook(t.appearance));
    if (t.embedding) embeds.set(t.track_id, decodeEmbedding(t.embedding));
  }
  return { tracks, looks, embeds };
}
export type LookIndex = ReturnType<typeof lookIndex>;

// Средний признак фрагментов с весом по времени на площадке; без признаков — null.
function meanOf(index: LookIndex, ids: number[], source: Map<number, Look>): Look | null {
  let out: Look | null = null;
  let total = 0;
  for (const id of ids) {
    const v = source.get(id);
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
export const meanLook = (index: LookIndex, ids: number[]) => meanOf(index, ids, index.looks);
export const meanEmbed = (index: LookIndex, ids: number[]) => meanOf(index, ids, index.embeds);

// Одновременно видны — разные люди (правило сервера, candidates.intervalsClash).
export function clash(index: LookIndex, a: number[], b: number[]): boolean {
  const spans = (ids: number[]) => ids.flatMap((id) => index.tracks.get(id)?.intervals ?? []);
  return intervalsClash(spans(a), spans(b));
}

// Фрагмент игрока, из-за которого кандидат ему недоступен (первый по номеру), и отрезок фрагмента на записи.
export function blocker(index: LookIndex, own: number[], ids: number[]): number | null {
  return [...own].sort((a, b) => a - b).find((t) => clash(index, [t], ids)) ?? null;
}
export function trackSpan(index: LookIndex, id: number): [number, number] | null {
  const iv = index.tracks.get(id)?.intervals ?? [];
  return iv.length ? [Math.min(...iv.map((x) => x[0])), Math.max(...iv.map((x) => x[1]))] : null;
}
