import { useState } from 'react';
import type { TeamActionStats } from '../../api/domain';
import { PassMap } from '../../components/pitch/PassMap';
import {
  ALL_PASSES,
  accuracy,
  filterPasses,
  formatAccuracy,
  MIN_PASSES_FOR_PERCENT,
  ORIENTATION_NOTE,
  orientPasses,
  type PassFilter,
  type PassPlayer,
  type Side,
  teamAccuracy,
  toArrows,
} from './passes';

type Name = (id: string | null | undefined) => string | null;
// «≈» — у передач, распознанных по видео; ручная разметка точна по тому, что размечено.
const autoPasses = (stats: TeamActionStats) =>
  stats.rows.some((r) => r.category === 'passes' && r.source === 'cv_auto');
const metres = (v: number | null) => (v == null ? '—' : v.toLocaleString('ru-RU', { maximumFractionDigits: 1 }));

// Доли точных, неточных и с неизвестным исходом — полосой; подпись «точных / с исходом · %».
function AccuracyBar({ side, total, accurate, known }: { side: Side; total: number; accurate: number; known: number }) {
  if (!total) return <span className="pass-bar empty" />;
  const pct = (v: number) => `${(100 * v) / total}%`;
  return (
    <span className="pass-bar" aria-hidden="true">
      <span className={`ok ${side}`} style={{ width: pct(accurate) }} />
      <span className="miss" style={{ width: pct(known - accurate) }} />
      <span className="unknown" style={{ width: pct(total - known) }} />
    </span>
  );
}

function PlayerRows({
  players,
  name,
  approx,
  selected,
  onPick,
}: {
  players: PassPlayer[];
  name: Name;
  approx: boolean;
  selected: string;
  onPick: (id: string) => void;
}) {
  return (
    <div className="table-scroll">
      <table className="stat-table pass-players" aria-label="Передачи игроков">
        <thead>
          <tr>
            <th>Игрок</th>
            <th>Передачи</th>
            <th>Точные</th>
            <th title="Средняя длина передачи">Длина, м</th>
          </tr>
        </thead>
        <tbody>
          {players.map((p) => {
            const a = accuracy([p], MIN_PASSES_FOR_PERCENT);
            const label = p.player_id ? (name(p.player_id) ?? 'Игрок') : 'Игрок не определён';
            return (
              <tr key={`${p.side}:${p.player_id}`} aria-selected={!!p.player_id && p.player_id === selected}>
                <td>
                  <i className={`side-dot ${p.side}`} aria-hidden="true" />{' '}
                  {p.player_id ? (
                    <button
                      className="link-button"
                      aria-pressed={p.player_id === selected}
                      onClick={() => onPick(p.player_id === selected ? '' : p.player_id!)}
                    >
                      {label}
                    </button>
                  ) : (
                    <span className="muted">{label}</span>
                  )}
                </td>
                <td className="num">{p.total}</td>
                <td className="num" title={a.known < MIN_PASSES_FOR_PERCENT ? 'Процент — от 5 передач с исходом' : ''}>
                  {formatAccuracy(a, approx)}
                  <AccuracyBar side={p.side} total={p.total} accurate={p.accurate} known={p.known} />
                </td>
                <td className="num">{metres(p.length_m)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// Карта передач и точность: по команде, по игроку и вместе. Автоматические передачи распознаются не все,
// поэтому процент помечен «≈», а у игрока считается только от 5 передач с известным исходом.
export function PassStats({
  stats,
  homeName,
  awayName,
  name,
}: {
  stats: TeamActionStats;
  homeName: string;
  awayName: string;
  name: Name;
}) {
  const [filter, setFilter] = useState<PassFilter>(ALL_PASSES);
  if (!stats.pitch) return null;
  const { length_m: L, width_m: W } = stats.pitch;
  const approx = autoPasses(stats);
  const oriented = orientPasses(stats.passes, L, W);
  const shown = filterPasses(oriented.passes, filter);
  const players = stats.pass_players.filter((p) => filter.side === 'all' || p.side === filter.side);
  const set = (patch: Partial<PassFilter>) => setFilter({ ...filter, ...patch });
  const sideName = (s: Side) => (s === 'home' ? homeName : awayName);
  const unplaced = stats.pass_players.reduce((s, p) => s + p.total, 0) - stats.passes.length;
  const chosen = filter.playerId ? stats.pass_players.find((p) => p.player_id === filter.playerId) : undefined;
  return (
    <div className="pass-stats">
      <div className="pass-teams" aria-label="Точность передач команд">
        {(['home', 'away'] as const).map((side) => {
          const a = teamAccuracy(stats.pass_players, side);
          return (
            <div key={side} className="pass-team">
              <span className="zone-name">
                <i className={`side-dot ${side}`} />
                {sideName(side)}
              </span>
              <b className="num pass-percent">
                {a.percent == null ? '—' : `${approx ? '≈' : ''}${Math.round(a.percent)}%`}
              </b>
              <span className="muted small num">
                точных {a.accurate} из {a.known}
                {a.total > a.known ? ` · без исхода ${a.total - a.known}` : ''}
              </span>
              <AccuracyBar side={side} total={a.total} accurate={a.accurate} known={a.known} />
            </div>
          );
        })}
      </div>
      <div className="pass-filters">
        <div className="segmented" role="group" aria-label="Команда">
          {(['all', 'home', 'away'] as const).map((s) => (
            <button
              key={s}
              type="button"
              className={filter.side === s ? 'active' : ''}
              aria-pressed={filter.side === s}
              onClick={() => set({ side: s, playerId: '' })}
            >
              {s === 'all' ? 'Обе команды' : sideName(s)}
            </button>
          ))}
        </div>
        <div className="segmented" role="group" aria-label="Исход передачи">
          {(
            [
              ['all', 'Все'],
              ['success', 'Точные'],
              ['failure', 'Неточные'],
            ] as const
          ).map(([o, label]) => (
            <button
              key={o}
              type="button"
              className={filter.outcome === o ? 'active' : ''}
              aria-pressed={filter.outcome === o}
              onClick={() => set({ outcome: o })}
            >
              {label}
            </button>
          ))}
        </div>
        <label className="pass-player-filter">
          <span className="muted small">Игрок</span>
          <select aria-label="Игрок" value={filter.playerId} onChange={(e) => set({ playerId: e.target.value })}>
            <option value="">Все игроки</option>
            {players
              .filter((p) => p.player_id)
              .map((p) => (
                <option key={p.player_id!} value={p.player_id!}>
                  {name(p.player_id) ?? 'Игрок'} · {sideName(p.side)}
                </option>
              ))}
          </select>
        </label>
      </div>
      {chosen && (
        <p className="pass-chosen" role="status">
          <b>{name(chosen.player_id) ?? 'Игрок'}</b>: передач {chosen.total}, точных{' '}
          {formatAccuracy(accuracy([chosen], MIN_PASSES_FOR_PERCENT), approx)}
          {chosen.length_m != null ? `, средняя длина ${metres(chosen.length_m)} м` : ''}
        </p>
      )}
      <PassMap
        passes={toArrows(shown, name, stats.source.clock_basis === 'video')}
        lengthM={L}
        widthM={W}
        homeName={homeName}
        awayName={awayName}
        note={[
          ORIENTATION_NOTE[oriented.orientation],
          unplaced > 0 ? `Без точек на поле и не на карте: ${unplaced}` : null,
        ]
          .filter(Boolean)
          .join(' ')}
      />
      <PlayerRows
        players={players}
        name={name}
        approx={approx}
        selected={filter.playerId}
        onPick={(playerId) => set({ playerId })}
      />
      {approx && (
        <p className="muted small">
          ≈ — передачи распознаны по видео не все: находится около двух третей, и неточные среди них бывают ложными.
          Процент игрока — от {MIN_PASSES_FOR_PERCENT} передач с известным исходом.
        </p>
      )}
    </div>
  );
}

// Передачи одного игрока: мини-карта и точность, для карточки игрока в отчёте.
export function PlayerPasses({
  stats,
  playerId,
  homeName,
  awayName,
  name,
}: {
  stats: TeamActionStats;
  playerId: string;
  homeName: string;
  awayName: string;
  name: Name;
}) {
  const row = stats.pass_players.find((p) => p.player_id === playerId);
  if (!row || !stats.pitch) return null;
  const approx = autoPasses(stats);
  const { length_m: L, width_m: W } = stats.pitch;
  const oriented = orientPasses(stats.passes, L, W);
  const own = filterPasses(oriented.passes, { ...ALL_PASSES, playerId });
  return (
    <section className="player-passes">
      <h3>Передачи</h3>
      <p className="num">
        {row.total} · точных {formatAccuracy(accuracy([row], MIN_PASSES_FOR_PERCENT), approx)}
        {row.length_m != null ? ` · средняя длина ${metres(row.length_m)} м` : ''}
      </p>
      <PassMap
        passes={toArrows(own, name, stats.source.clock_basis === 'video')}
        lengthM={L}
        widthM={W}
        homeName={homeName}
        awayName={awayName}
        note={ORIENTATION_NOTE[oriented.orientation]}
        compact
      />
    </section>
  );
}
