import { useEffect, useRef, useState } from 'react';
import type { AnalysisAssignment } from '../../api/domain';
import type { Candidate } from './candidates';
import { type MatchModel, modelSamples, type Sample, trainModel } from './matchModel';
import type { LookIndex } from './similar';

const DELAY_MS = 600;

type Trainer = (samples: Sample[], prev: MatchModel | null) => Promise<MatchModel | null>;

// Фоновый поток браузера; где его нет (тесты в jsdom) — обучение в основном потоке.
function makeTrainer(): { train: Trainer; stop: () => void } {
  if (typeof Worker === 'undefined')
    return { train: async (samples, prev) => trainModel(samples, prev), stop: () => {} };
  const worker = new Worker(new URL('./matchModel.worker.ts', import.meta.url), { type: 'module' });
  const waiting = new Map<number, (model: MatchModel | null) => void>();
  let next = 0;
  worker.onmessage = (e: MessageEvent<{ id: number; model: MatchModel | null }>) => {
    waiting.get(e.data.id)?.(e.data.model);
    waiting.delete(e.data.id);
  };
  return {
    train: (samples, prev) =>
      new Promise((resolve) => {
        const id = ++next;
        waiting.set(id, resolve);
        worker.postMessage({ id, samples, prev });
      }),
    stop: () => worker.terminate(),
  };
}

// Модель матча для команды: переобучается через 0,6 с после последнего решения (тёплый старт) в фоновом потоке,
// чтобы ввод клавишами не ждал обучения; до первого обучения и без признаков SigLIP — null (подсветка по цвету).
export function useMatchModel(
  index: LookIndex,
  candidates: Candidate[],
  team: 'A' | 'B',
  playerIds: string[],
  assignments: AnalysisAssignment[],
): MatchModel | null {
  // Модель другой команды (сразу после переключения) не используется: до обучения — подсветка по цвету.
  const [state, setState] = useState<{ team: 'A' | 'B'; model: MatchModel | null } | null>(null);
  const prev = useRef<MatchModel | null>(null);
  const trained = useRef('');
  const latest = useRef(0);
  const trainer = useRef<ReturnType<typeof makeTrainer> | null>(null);
  const args = useRef({ index, candidates, team, playerIds, assignments });
  args.current = { index, candidates, team, playerIds, assignments };
  const key = `${team}|${playerIds.join(',')}|${assignments
    .filter((a) => a.player_id)
    .map((a) => `${a.track_id}:${a.player_id}`)
    .sort()
    .join(',')}`;
  useEffect(
    () => () => {
      trainer.current?.stop();
      trainer.current = null;
    },
    [],
  );
  useEffect(() => {
    if (key === trained.current) return;
    const timer = setTimeout(() => {
      trained.current = key;
      const a = args.current;
      const samples = modelSamples(a.index, a.candidates, a.team, a.playerIds, a.assignments);
      const id = ++latest.current;
      // Меньше двух игроков с признаком SigLIP (в том числе старые пакеты без него) — модели нет.
      if (new Set(samples.map((s) => s.y)).size < 2) {
        prev.current = null;
        setState(null);
        return;
      }
      trainer.current ??= makeTrainer();
      void trainer.current.train(samples, prev.current).then((next) => {
        if (id !== latest.current) return;
        prev.current = next;
        setState({ team: a.team, model: next });
      });
    }, DELAY_MS);
    return () => clearTimeout(timer);
  }, [key]);
  return state?.team === team ? state.model : null;
}
