import { type MatchModel, type Sample, trainModel } from './matchModel';

// Обучение модели матча в фоне: на полном матче (≈ 400 решений) оно занимает до 2–3 с и не должно задерживать
// ввод клавишами в очереди.
type Job = { id: number; samples: Sample[]; prev: MatchModel | null };
const scope = self as unknown as {
  onmessage: ((e: MessageEvent<Job>) => void) | null;
  postMessage: (message: { id: number; model: MatchModel | null }) => void;
};
scope.onmessage = (e) => scope.postMessage({ id: e.data.id, model: trainModel(e.data.samples, e.data.prev) });
