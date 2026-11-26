import { useMemo, useState } from 'react';
import type { AnalysisAssignment, AnalysisRun } from '../../api/domain';
import { CandidateThumb } from './CandidateThumb';
import { assignGroup, baseGroups, candidatesOf, clock } from './candidates';
import { clash, lookIndex } from './similar';
import { groupByPlayer, type Hint, hintsFor, initialTicks, rejectKey, type Unhinted } from './suggestions';

const REASONS = { no_look: 'нет признака цвета', no_player: 'ни один игрок не подходит по времени' } as const;

// Подсказки: каждому неназначенному кандидату команды — лучший по цвету формы игрок из уже размеченных; уверенные
// отмечены сразу. Назначает человек: снимает отметки с ошибок, «Не он» отдаёт кандидата следующему игроку.
// Как и в других режимах, меняются назначения черновика; на сервер их отправляет «Сохранить сопоставление».
export function SuggestionPicker({
  run,
  assignments,
  sideMap,
  disabled,
  onChange,
  onOpenSimilar,
}: {
  run: AnalysisRun;
  assignments: AnalysisAssignment[];
  sideMap: AnalysisRun['side_map'];
  disabled: boolean;
  onChange: (next: AnalysisAssignment[]) => void;
  onOpenSimilar: () => void;
}) {
  const index = useMemo(() => lookIndex(run), [run]);
  const candidates = useMemo(() => candidatesOf(run, baseGroups(run)), [run]);
  const [team, setTeam] = useState<'A' | 'B'>('A');
  const [rejected, setRejected] = useState<Set<string>>(() => new Set());
  const [marks, setMarks] = useState<Record<string, boolean>>({});
  const roster = run.context.rosters.filter((p) => p.side === sideMap[team]);
  const result = hintsFor(
    index,
    candidates,
    team,
    roster.map((p) => p.player_id),
    assignments,
    rejected,
  );
  const groups = groupByPlayer(result.hints);
  const name = (id: string) => {
    const p = roster.find((x) => x.player_id === id);
    return p ? `${p.shirt_number ? `${p.shirt_number} · ` : ''}${p.display_name}` : id;
  };
  const forget = (keys: string[]) =>
    setMarks((m) => {
      const next = { ...m };
      for (const k of keys) delete next[k];
      return next;
    });
  function reject(h: Hint) {
    setRejected((r) => new Set(r).add(rejectKey(h.playerId, h.candidate)));
    forget([h.candidate.key]);
  }
  const counts = new Map<Unhinted['reason'], number>();
  for (const u of result.unhinted) counts.set(u.reason, (counts.get(u.reason) ?? 0) + 1);
  const reasons = [...counts].map(([reason, n]) => `${REASONS[reason]}: ${n}`).join('; ');
  return (
    <section className="suggestion-picker" aria-label="Подсказки игроков">
      <div className="similar-head">
        <div className="segmented review-mode" role="group" aria-label="Команда">
          {(['A', 'B'] as const).map((t) => (
            <button type="button" key={t} aria-pressed={team === t} onClick={() => setTeam(t)}>
              {run.context.teams[sideMap[t]].name}
            </button>
          ))}
        </div>
      </div>
      {!result.players ? (
        <div className="row wrap">
          <p className="muted">
            Сначала назначьте каждому игроку хотя бы один фрагмент в «Подборе» — подсказки строятся по ним.
          </p>
          <button type="button" onClick={onOpenSimilar}>
            Открыть «Подбор»
          </button>
        </div>
      ) : groups.length ? (
        groups.map((g) => {
          const defaults = initialTicks(index, g.hints);
          const ticked = (h: Hint) => marks[h.candidate.key] ?? defaults.has(h.candidate.key);
          const chosen = g.hints.filter(ticked);
          const chosenIds = chosen.flatMap((h) => h.candidate.trackIds);
          function assign() {
            let next = assignments;
            for (const h of chosen) next = assignGroup(next, h.candidate.trackIds, g.playerId);
            forget(g.hints.map((h) => h.candidate.key));
            onChange(next);
          }
          // Все сразу: «да» — всем, кроме видных одновременно с уже отмеченными; «нет» — снять отметки.
          const tickAll = (on: boolean) => {
            const all = on ? initialTicks(index, g.hints, false) : new Set<string>();
            setMarks((m) => ({
              ...m,
              ...Object.fromEntries(g.hints.map((h) => [h.candidate.key, all.has(h.candidate.key)])),
            }));
          };
          const unticked = g.hints.filter((h) => !ticked(h));
          function rejectUnticked() {
            setRejected((r) => new Set([...r, ...unticked.map((h) => rejectKey(h.playerId, h.candidate))]));
            forget(unticked.map((h) => h.candidate.key));
          }
          return (
            <section className="hint-group" key={g.playerId} aria-label={`Подсказки игроку ${name(g.playerId)}`}>
              <h3>
                {name(g.playerId)} — подсказок: {g.hints.length}
              </h3>
              <ul className="similar-grid">
                {g.hints.map((h) => {
                  const c = h.candidate;
                  const on = ticked(h);
                  const blocked = !on && chosenIds.length > 0 && clash(index, chosenIds, c.trackIds);
                  return (
                    <li
                      key={c.key}
                      className={`similar-card${on ? ' yes' : ''}`}
                      aria-label={`Фрагмент ${clock(c.span[0])}–${clock(c.span[1])}`}
                    >
                      <CandidateThumb run={run} index={index} candidate={c} className="similar" />
                      <span className="small num">
                        похож {h.score.toFixed(2)} · {clock(c.seconds)}
                      </span>
                      <span className="muted small num">
                        {clock(c.span[0])}–{clock(c.span[1])}
                        {c.goalkeeper ? ' · вратарь' : ''}
                      </span>
                      <span className={`hint-confidence ${h.confident ? 'sure' : 'unsure'}`}>
                        {h.confident ? 'уверенно' : 'сомнительно'}
                      </span>
                      <div className="similar-actions">
                        <label className="check" title={blocked ? 'Виден одновременно с уже отмеченным' : undefined}>
                          <input
                            type="checkbox"
                            checked={on}
                            disabled={disabled || blocked}
                            onChange={() => setMarks((m) => ({ ...m, [c.key]: !on }))}
                          />
                          Назначить
                        </label>
                        <button type="button" disabled={disabled} onClick={() => reject(h)}>
                          Не он
                        </button>
                      </div>
                    </li>
                  );
                })}
              </ul>
              <div className="row wrap">
                <button type="button" className="primary" disabled={disabled || !chosen.length} onClick={assign}>
                  Назначить отмеченных ({chosen.length})
                </button>
                <button type="button" disabled={disabled} onClick={() => tickAll(true)}>
                  Отметить все
                </button>
                <button type="button" disabled={disabled || !chosen.length} onClick={() => tickAll(false)}>
                  Снять все
                </button>
                <button type="button" disabled={disabled || !unticked.length} onClick={rejectUnticked}>
                  Не он — неотмеченным ({unticked.length})
                </button>
              </div>
            </section>
          );
        })
      ) : (
        <p className="muted">Подсказок нет: все фрагменты команды с признаком цвета назначены.</p>
      )}
      {result.unhinted.length > 0 && (
        <p className="muted small" role="status" aria-label="Без подсказки">
          Без подсказки: {result.unhinted.length} — {reasons}. Их назначают в «По фрагментам».
        </p>
      )}
    </section>
  );
}
