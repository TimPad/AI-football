import { useEffect, useMemo, useState } from 'react';
import type { AnalysisAssignment, AnalysisRun } from '../../api/domain';
import { CandidateThumb } from './CandidateThumb';
import { assignGroup, baseGroups, candidatesOf, clock, decisionOf } from './candidates';
import { available, confidentHint, queueOrder, queuePlayers } from './queue';
import { lookIndex } from './similar';
import { useMatchModel } from './useMatchModel';

type Step = { key: string; before: AnalysisAssignment[] };
const EXCLUDE_KEYS = ['x', 'X', 'ч', 'Ч'];

// Очередь разметки: один неназначенный фрагмент команды за раз, кнопки игроков в постоянном порядке. Порядок —
// снимок по времени: после решения ничего не перестраивается, пропущенные проходят в конце отдельным кругом.
export function IdentityQueue({
  run,
  assignments,
  sideMap,
  absent,
  disabled,
  onChange,
}: {
  run: AnalysisRun;
  assignments: AnalysisAssignment[];
  sideMap: AnalysisRun['side_map'];
  absent: string[];
  disabled: boolean;
  onChange: (next: AnalysisAssignment[]) => void;
}) {
  const index = useMemo(() => lookIndex(run), [run]);
  const candidates = useMemo(() => candidatesOf(run, baseGroups(run)), [run]);
  const byKey = useMemo(() => new Map(candidates.map((c) => [c.key, c])), [candidates]);
  const [team, setTeam] = useState<'A' | 'B'>('A');
  const [order, setOrder] = useState(() => queueOrder(candidates, 'A', assignments));
  const [pos, setPos] = useState(0);
  const [skipped, setSkipped] = useState<string[]>([]);
  const [history, setHistory] = useState<Step[]>([]);
  const open = (key: string) => decisionOf(assignments, byKey.get(key)?.trackIds ?? []).kind === 'none';
  const at = order.findIndex((k, i) => i >= pos && open(k) && !skipped.includes(k));
  const current = at >= 0 ? byKey.get(order[at]) : undefined;
  const players = queuePlayers(index, run.context.rosters, sideMap[team], absent, assignments);
  const model = useMatchModel(
    index,
    candidates,
    team,
    players.map((p) => p.id),
    assignments,
  );
  const hint = current ? confidentHint(index, players, current, model) : null;
  const left = order.filter(open).length;

  function restart(nextTeam: 'A' | 'B', keys?: string[]) {
    setTeam(nextTeam);
    setOrder(keys ?? queueOrder(candidates, nextTeam, assignments));
    setPos(0);
    setSkipped([]);
    setHistory([]);
  }
  function decide(value: string) {
    if (!current || disabled) return;
    setHistory((h) => [...h, { key: current.key, before: assignments }]);
    setPos(at + 1);
    onChange(assignGroup(assignments, current.trackIds, value));
  }
  function skip() {
    if (!current) return;
    setSkipped((s) => [...s, current.key]);
    setPos(at + 1);
  }
  function undo() {
    const step = history[history.length - 1];
    if (!step || disabled) return;
    setHistory((h) => h.slice(0, -1));
    setPos(Math.max(0, order.indexOf(step.key)));
    // Не участвовавшему после решения фрагменты не возвращаются: сервер такую разметку не примет.
    onChange(step.before.filter((a) => !a.player_id || !absent.includes(a.player_id)));
  }
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.target instanceof HTMLElement && ['INPUT', 'SELECT', 'TEXTAREA'].includes(e.target.tagName)) return;
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const player = players.find((p) => p.key && p.key === e.key);
      if (player) {
        e.preventDefault();
        if (current && available(index, player, current)) decide(player.id);
      } else if (EXCLUDE_KEYS.includes(e.key)) {
        e.preventDefault();
        decide('exclude');
      } else if (e.key === ' ') {
        e.preventDefault();
        skip();
      } else if (e.key === 'Backspace') {
        e.preventDefault();
        undo();
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  return (
    <section className="identity-queue" aria-label="Очередь разметки">
      <div className="similar-head">
        <div className="segmented review-mode" role="group" aria-label="Команда">
          {(['A', 'B'] as const).map((t) => (
            <button type="button" key={t} aria-pressed={team === t} onClick={() => restart(t)}>
              {run.context.teams[sideMap[t]].name}
            </button>
          ))}
        </div>
        <span className="muted small num" role="status" aria-label="Прогресс очереди">
          {current ? `фрагмент ${at + 1} из ${order.length} · ` : ''}осталось {left}
        </span>
      </div>
      {current ? (
        <div className="queue-body">
          <CandidateThumb run={run} index={index} candidate={current} className="queue" />
          <div className="queue-side">
            <p className="queue-title num">
              {clock(current.span[0])}–{clock(current.span[1])} · {Math.round(current.seconds)} с
              {current.goalkeeper ? ' · вратарь' : ''}
            </p>
            <p className="muted small">
              {hint ? `похож на ${players.find((p) => p.id === hint)?.label} (уверенно)` : 'подсказки нет'}
            </p>
            <div className="queue-players" role="group" aria-label="Игрок фрагмента">
              {players.map((p) => {
                const free = available(index, p, current);
                return (
                  <button
                    type="button"
                    key={p.id}
                    className={`queue-player${p.id === hint ? ' hinted' : ''}`}
                    disabled={disabled || !free}
                    title={free ? undefined : 'На площадке в это время'}
                    onClick={() => decide(p.id)}
                  >
                    {p.key ? `${p.key} · ` : ''}
                    {p.label}
                  </button>
                );
              })}
            </div>
            <div className="row wrap">
              <button type="button" disabled={disabled} onClick={() => decide('exclude')}>
                X · Не игрок матча
              </button>
              <button type="button" onClick={skip}>
                Пробел · Пропустить
              </button>
              <button type="button" disabled={disabled || !history.length} onClick={undo}>
                Назад
              </button>
            </div>
          </div>
        </div>
      ) : (
        <div className="row wrap">
          <p className="muted">
            Все фрагменты команды в очереди размечены{skipped.length ? `, пропущено: ${skipped.length}` : ''}.
          </p>
          {skipped.length > 0 && (
            <button type="button" onClick={() => restart(team, skipped.filter(open))}>
              Пройти пропущенные
            </button>
          )}
          <button type="button" disabled={disabled || !history.length} onClick={undo}>
            Назад
          </button>
        </div>
      )}
    </section>
  );
}
