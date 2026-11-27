import { useMemo, useState } from 'react';
import type { AnalysisAssignment, AnalysisRun } from '../../api/domain';
import { CandidateThumb } from './CandidateThumb';
import { baseGroups, candidatesOf, clock } from './candidates';
import { lookIndex } from './similar';

type Player = AnalysisRun['context']['rosters'][number];
const shirt = (p: Player) =>
  p.shirt_number && Number.isFinite(Number(p.shirt_number)) ? Number(p.shirt_number) : Number.POSITIVE_INFINITY;

// Игроки матча: участие и исправления. Выключенное участие снимает назначения игрока (фрагменты вернутся в
// очередь) и убирает его из кнопок; протокол матча (ручной учёт) не меняется.
export function PlayersPanel({
  run,
  assignments,
  absent,
  disabled,
  onChange,
}: {
  run: AnalysisRun;
  assignments: AnalysisAssignment[];
  absent: string[];
  disabled: boolean;
  onChange: (assignments: AnalysisAssignment[], absent: string[]) => void;
}) {
  const index = useMemo(() => lookIndex(run), [run]);
  const candidates = useMemo(() => candidatesOf(run, baseGroups(run)), [run]);
  const [chosen, setChosen] = useState<string | null>(null);
  const rows = [...run.context.rosters].sort(
    (a, b) =>
      (a.side === 'home' ? 0 : 1) - (b.side === 'home' ? 0 : 1) ||
      shirt(a) - shirt(b) ||
      a.display_name.localeCompare(b.display_name, 'ru'),
  );
  const ownOf = (id: string) => assignments.filter((a) => a.player_id === id);
  const minutes = (id: string) =>
    ownOf(id).reduce(
      (s, a) => s + (index.tracks.get(a.track_id)?.intervals.reduce((x, [from, to]) => x + to - from, 0) ?? 0),
      0,
    ) / 60;
  const label = (p: Player) => `${p.shirt_number ? `№${p.shirt_number} ` : ''}${p.display_name}`;
  function toggle(p: Player, on: boolean) {
    if (on) {
      onChange(
        assignments,
        absent.filter((id) => id !== p.player_id),
      );
      return;
    }
    const own = ownOf(p.player_id);
    if (own.length && !window.confirm(`У игрока ${p.display_name} фрагментов: ${own.length} — вернуть их в очередь?`))
      return;
    onChange(
      assignments.filter((a) => a.player_id !== p.player_id),
      [...absent, p.player_id],
    );
  }
  const player = rows.find((p) => p.player_id === chosen);
  // Кандидаты, где у игрока есть хоть один фрагмент: решения, поставленные на часть склейки, тоже видны
  // (иначе они незаметно мешают назначению по одновременности). «Убрать» снимает только фрагменты этого игрока.
  const ownIn = (ids: number[]) =>
    player ? ids.filter((id) => assignments.some((a) => a.track_id === id && a.player_id === player.player_id)) : [];
  const mine = player ? candidates.filter((c) => ownIn(c.trackIds).length > 0) : [];
  return (
    <section className="players-panel" aria-label="Игроки матча">
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Игрок</th>
              <th>Команда</th>
              <th>Фрагментов</th>
              <th>Минут</th>
              <th>Участвовал</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => {
              const off = absent.includes(p.player_id);
              return (
                <tr key={p.player_id} className={off ? 'muted' : undefined}>
                  <td>
                    <button type="button" aria-pressed={chosen === p.player_id} onClick={() => setChosen(p.player_id)}>
                      {label(p)}
                    </button>
                  </td>
                  <td>{p.side === 'home' ? run.context.teams.home.name : run.context.teams.away.name}</td>
                  <td className="num">{ownOf(p.player_id).length}</td>
                  <td className="num">{minutes(p.player_id).toFixed(1)}</td>
                  <td>
                    <input
                      type="checkbox"
                      aria-label={`Участвовал в матче: ${p.display_name}`}
                      checked={!off}
                      disabled={disabled}
                      onChange={(e) => toggle(p, e.target.checked)}
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {player && (
        <section aria-label="Фрагменты игрока">
          <h3>
            {label(player)} — фрагментов: {mine.length}
          </h3>
          <ul className="grid-tiles">
            {mine.map((c) => (
              <li key={c.key} className="grid-tile">
                <CandidateThumb run={run} index={index} candidate={c} className="tile" />
                <span className="muted small num">
                  {clock(c.span[0])}–{clock(c.span[1])}
                  {ownIn(c.trackIds).length < c.trackIds.length ? ' · часть склейки' : ''}
                </span>
                <button
                  type="button"
                  aria-label={`Убрать ${clock(c.span[0])}–${clock(c.span[1])}`}
                  disabled={disabled}
                  onClick={() => {
                    const ids = ownIn(c.trackIds);
                    onChange(
                      assignments.filter((a) => !ids.includes(a.track_id)),
                      absent,
                    );
                  }}
                >
                  Убрать
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </section>
  );
}
