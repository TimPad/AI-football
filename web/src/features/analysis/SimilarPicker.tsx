import { useMemo, useState } from 'react';
import type { AnalysisAssignment, AnalysisRun } from '../../api/domain';
import { CandidateThumb } from './CandidateThumb';
import { assignGroup, baseGroups, candidatesOf, clock, decisionOf } from './candidates';
import { assignedShare, clash, lookIndex, suggest } from './similar';

const STEP = 12;
type Mark = 'yes' | 'no';

// Подбор фрагментов игроку: выбран игрок, ниже — самые похожие неназначенные фрагменты его команды, не видные
// одновременно с его фрагментами. Человек отмечает «он» / «не он» и добавляет отмеченных; подсказки после этого
// пересчитываются по всем фрагментам игрока. Сохраняются, как и в других режимах, назначения фрагментов.
export function SimilarPicker({
  run,
  assignments,
  sideMap,
  disabled,
  onChange,
}: {
  run: AnalysisRun;
  assignments: AnalysisAssignment[];
  sideMap: AnalysisRun['side_map'];
  disabled: boolean;
  onChange: (next: AnalysisAssignment[]) => void;
}) {
  const index = useMemo(() => lookIndex(run), [run]);
  const candidates = useMemo(() => candidatesOf(run, baseGroups(run)), [run]);
  const [team, setTeam] = useState<'A' | 'B'>('A');
  const [chosen, setChosen] = useState<Partial<Record<'A' | 'B', string>>>({});
  const [marks, setMarks] = useState<Record<string, Mark>>({});
  const [rejected, setRejected] = useState<Record<string, string[]>>({});
  const [limit, setLimit] = useState(STEP);
  const roster = run.context.rosters.filter((p) => p.side === sideMap[team]);
  const own = (id: string) => assignments.filter((a) => a.player_id === id).map((a) => a.track_id);
  const player =
    roster.find((p) => p.player_id === chosen[team]) ?? roster.find((p) => !own(p.player_id).length) ?? roster[0];
  const reset = () => {
    setMarks({});
    setLimit(STEP);
  };
  if (!player) return <p className="muted">В составе этой стороны нет игроков.</p>;
  const mine = own(player.player_id);
  const list = suggest(index, candidates, team, mine, assignments, new Set(rejected[player.player_id]), limit);
  const yes = list.filter((s) => marks[s.candidate.key] === 'yes');
  const yesIds = yes.flatMap((s) => s.candidate.trackIds);
  const placed = candidates.filter((c) => {
    const d = decisionOf(assignments, c.trackIds);
    return d.kind === 'player' && d.playerId === player.player_id;
  });
  const placedSeconds = placed.reduce((s, c) => s + c.seconds, 0);
  const share = assignedShare(candidates, team, assignments);
  const label = (p: (typeof roster)[number]) =>
    `${p.shirt_number ? `${p.shirt_number} · ` : ''}${p.display_name}${own(p.player_id).length ? ` · фрагментов ${own(p.player_id).length}` : ''}`;
  function pick(id: string) {
    setChosen((c) => ({ ...c, [team]: id }));
    reset();
  }
  function mark(key: string, value: Mark) {
    setMarks((m) => {
      const next = { ...m };
      if (next[key] === value) delete next[key];
      else next[key] = value;
      return next;
    });
  }
  function add() {
    let next = assignments;
    for (const s of yes) next = assignGroup(next, s.candidate.trackIds, player.player_id);
    const no = list.filter((s) => marks[s.candidate.key] === 'no').map((s) => s.candidate.key);
    if (no.length) setRejected((r) => ({ ...r, [player.player_id]: [...(r[player.player_id] ?? []), ...no] }));
    // Игрок остаётся выбранным: иначе после первых фрагментов выбор ушёл бы к следующему без фрагментов.
    setChosen((c) => ({ ...c, [team]: player.player_id }));
    reset();
    onChange(next);
  }
  const nextFree = roster.find((p) => p.player_id !== player.player_id && !own(p.player_id).length);
  return (
    <section className="similar-picker" aria-label="Подбор похожих фрагментов">
      <div className="similar-head">
        <div className="segmented review-mode" role="group" aria-label="Команда">
          {(['A', 'B'] as const).map((t) => (
            <button
              key={t}
              aria-pressed={team === t}
              onClick={() => {
                setTeam(t);
                reset();
              }}
            >
              {run.context.teams[sideMap[t]].name}
            </button>
          ))}
        </div>
        <label className="field">
          <span>Игрок</span>
          <select aria-label="Игрок" value={player.player_id} onChange={(e) => pick(e.target.value)}>
            {roster.map((p) => (
              <option key={p.player_id} value={p.player_id}>
                {label(p)}
              </option>
            ))}
          </select>
        </label>
        <span className="muted small num" role="status" aria-label="Назначено времени команды">
          назначено {Math.round(share * 100)}% игрового времени команды
        </span>
      </div>
      <div className="similar-player">
        <p className="candidate-meta">
          <b>{player.display_name}</b>
          <span className="muted num">
            · фрагментов {mine.length} · {clock(placedSeconds)} на площадке
          </span>
        </p>
        {placed.length ? (
          <ul className="similar-own" aria-label="Фрагменты игрока">
            {placed.map((c) => (
              <li key={c.key}>
                <CandidateThumb run={run} index={index} candidate={c} className="small" />
                <button
                  aria-label={`Убрать фрагмент ${clock(c.span[0])}–${clock(c.span[1])}`}
                  title="Убрать у игрока"
                  disabled={disabled}
                  onClick={() => onChange(assignGroup(assignments, c.trackIds, ''))}
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted small">
            Фрагментов пока нет — отметьте этого игрока среди самых длинных фрагментов команды.
          </p>
        )}
      </div>
      <p className="muted small">
        {mine.length
          ? 'Похожие и не видные одновременно с ним — отметьте, кто из них он.'
          : 'Самые длинные неназначенные фрагменты команды.'}
      </p>
      {list.length ? (
        <ul className="similar-grid">
          {list.map(({ candidate: c, score }) => {
            const m = marks[c.key];
            const blocked = m !== 'yes' && yesIds.length > 0 && clash(index, yesIds, c.trackIds);
            return (
              <li
                key={c.key}
                className={`similar-card${m ? ` ${m}` : ''}`}
                aria-label={`Фрагмент ${clock(c.span[0])}–${clock(c.span[1])}`}
              >
                <CandidateThumb run={run} index={index} candidate={c} className="similar" />
                <span className="small num">
                  {score != null ? `похож ${score.toFixed(2)} · ` : ''}
                  {clock(c.seconds)}
                </span>
                <span className="muted small num">
                  {clock(c.span[0])}–{clock(c.span[1])}
                  {c.goalkeeper ? ' · вратарь' : ''}
                </span>
                <div className="similar-actions">
                  <button
                    aria-pressed={m === 'yes'}
                    disabled={disabled || blocked}
                    title={blocked ? 'Виден одновременно с уже отмеченным' : undefined}
                    onClick={() => mark(c.key, 'yes')}
                  >
                    Он
                  </button>
                  <button aria-pressed={m === 'no'} disabled={disabled} onClick={() => mark(c.key, 'no')}>
                    Не он
                  </button>
                  <button disabled={disabled} onClick={() => onChange(assignGroup(assignments, c.trackIds, 'exclude'))}>
                    Не игрок
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="muted">Подсказок нет: все фрагменты команды назначены или видны одновременно с этим игроком.</p>
      )}
      <div className="row wrap">
        <button className="primary" disabled={disabled || !yes.length} onClick={add}>
          Добавить отмеченных ({yes.length})
        </button>
        <button disabled={list.length < limit} onClick={() => setLimit((l) => l + STEP)}>
          Ещё похожие
        </button>
        <button disabled={!nextFree} onClick={() => nextFree && pick(nextFree.player_id)}>
          Следующий игрок
        </button>
      </div>
    </section>
  );
}
