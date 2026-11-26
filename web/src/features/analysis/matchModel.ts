import type { AnalysisAssignment } from '../../api/domain';
import { type Candidate, decisionOf } from './candidates';
import { type LookIndex, meanEmbed, meanLook } from './similar';

// Модель матча: многоклассовая логистическая регрессия на признаке SigLIP 2 и цвете фрагмента по решениям этого
// матча (стандартизация, L2 с C = 1, Adam). Замер ВШЭ Ю — JWH: при вероятности ≥ 0,9 уверенных 72–84% фрагментов
// при точности 94–96%, у цвета — 21–28% (docs/superpowers/specs/2026-11-26-identity-queue-design.md).
export const MODEL_CONFIDENCE = 0.9;
const C = 1;
const STEPS = 200;
const WARM_STEPS = 60;
const RATE = 0.05;

export type MatchModel = { classes: string[]; w: Float64Array[]; b: Float64Array; mu: Float64Array; sd: Float64Array };
export type Sample = { x: Float64Array; y: string };

// Признак кандидата: средние SigLIP 2 и цвет его фрагментов; без любого из них — null.
export function candidateFeature(index: LookIndex, candidate: Candidate): Float64Array | null {
  const e = meanEmbed(index, candidate.trackIds);
  const l = meanLook(index, candidate.trackIds);
  if (!e || !l) return null;
  const x = new Float64Array(e.length + l.length);
  x.set(e);
  x.set(l, e.length);
  return x;
}

// Примеры для обучения: кандидаты команды с решением «игрок» среди данных игроков.
export function modelSamples(
  index: LookIndex,
  candidates: Candidate[],
  team: 'A' | 'B',
  playerIds: string[],
  assignments: AnalysisAssignment[],
): Sample[] {
  return candidates.flatMap((c) => {
    if (c.team !== team) return [];
    const d = decisionOf(assignments, c.trackIds);
    const x = d.kind === 'player' && d.playerId && playerIds.includes(d.playerId) ? candidateFeature(index, c) : null;
    return x && d.playerId ? [{ x, y: d.playerId }] : [];
  });
}

function softmax(model: Pick<MatchModel, 'w' | 'b'>, z: Float64Array): Float64Array {
  const logits = model.w.map((row, c) => {
    let s = model.b[c];
    for (let j = 0; j < z.length; j++) s += row[j] * z[j];
    return s;
  });
  const top = Math.max(...logits);
  const e = logits.map((v) => Math.exp(v - top));
  const sum = e.reduce((a, v) => a + v, 0);
  return Float64Array.from(e.map((v) => v / sum));
}

const standardize = (model: MatchModel, x: Float64Array) => x.map((v, j) => (v - model.mu[j]) / model.sd[j]);

// Обучение; prev с теми же игроками — тёплый старт (меньше шагов). Меньше двух игроков — модели нет.
export function trainModel(samples: Sample[], prev?: MatchModel | null): MatchModel | null {
  const classes = [...new Set(samples.map((s) => s.y))].sort();
  if (classes.length < 2) return null;
  const n = samples.length;
  const d = samples[0].x.length;
  const k = classes.length;
  const mu = new Float64Array(d);
  const sd = new Float64Array(d);
  for (const s of samples) for (let j = 0; j < d; j++) mu[j] += s.x[j] / n;
  for (const s of samples) for (let j = 0; j < d; j++) sd[j] += (s.x[j] - mu[j]) ** 2 / n;
  for (let j = 0; j < d; j++) sd[j] = sd[j] > 1e-12 ? Math.sqrt(sd[j]) : 1;
  const X = samples.map((s) => s.x.map((v, j) => (v - mu[j]) / sd[j]));
  const y = samples.map((s) => classes.indexOf(s.y));
  const warm = !!prev && prev.classes.join('|') === classes.join('|') && prev.w[0]?.length === d;
  const w = warm && prev ? prev.w.map((r) => Float64Array.from(r)) : classes.map(() => new Float64Array(d));
  const b = warm && prev ? Float64Array.from(prev.b) : new Float64Array(k);
  const mW = classes.map(() => new Float64Array(d));
  const vW = classes.map(() => new Float64Array(d));
  const mB = new Float64Array(k);
  const vB = new Float64Array(k);
  const lambda = 1 / (C * n);
  const steps = warm ? WARM_STEPS : STEPS;
  for (let step = 1; step <= steps; step++) {
    const gW = classes.map(() => new Float64Array(d));
    const gB = new Float64Array(k);
    for (let i = 0; i < n; i++) {
      const p = softmax({ w, b }, X[i]);
      for (let c = 0; c < k; c++) {
        const g = (p[c] - (y[i] === c ? 1 : 0)) / n;
        gB[c] += g;
        const row = gW[c];
        const xi = X[i];
        for (let j = 0; j < d; j++) row[j] += g * xi[j];
      }
    }
    const c1 = 1 - 0.9 ** step;
    const c2 = 1 - 0.999 ** step;
    for (let c = 0; c < k; c++) {
      for (let j = 0; j < d; j++) {
        const g = gW[c][j] + lambda * w[c][j];
        mW[c][j] = 0.9 * mW[c][j] + 0.1 * g;
        vW[c][j] = 0.999 * vW[c][j] + 0.001 * g * g;
        w[c][j] -= (RATE * (mW[c][j] / c1)) / (Math.sqrt(vW[c][j] / c2) + 1e-8);
      }
      mB[c] = 0.9 * mB[c] + 0.1 * gB[c];
      vB[c] = 0.999 * vB[c] + 0.001 * gB[c] * gB[c];
      b[c] -= (RATE * (mB[c] / c1)) / (Math.sqrt(vB[c] / c2) + 1e-8);
    }
  }
  return { classes, w, b, mu, sd };
}

// Лучший из доступных игроков и его вероятность, нормированная по доступным; никого нет — null.
export function predict(model: MatchModel, x: Float64Array, allowed: string[]): { playerId: string; p: number } | null {
  const p = softmax(model, standardize(model, x));
  const keep = model.classes.flatMap((c, i) => (allowed.includes(c) ? [i] : []));
  if (!keep.length) return null;
  const total = keep.reduce((s, i) => s + p[i], 0) || 1;
  const best = keep.reduce((a, i) => (p[i] > p[a] ? i : a), keep[0]);
  return { playerId: model.classes[best], p: p[best] / total };
}

// Вероятность одного игрока среди всех игроков модели (порядок «Похожие на …» в сетке).
export function probabilityOf(model: MatchModel, x: Float64Array, playerId: string): number {
  const i = model.classes.indexOf(playerId);
  return i < 0 ? 0 : softmax(model, standardize(model, x))[i];
}
