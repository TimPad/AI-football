import { useState } from 'react';
import type { TeamActionStats } from '../../api/domain';
import { PassMap } from '../../components/pitch/PassMap';
import { PassNetwork } from '../../components/pitch/PassNetwork';
import {
  ALL_PASSES,
  accuracy,
  defaultThreshold,
  filterPasses,
  formatAccuracy,
  GENERAL_BALL_CAVEAT,
  MIN_PASSES_FOR_PERCENT,
  type NetworkEdge,
  ORIENTATION_NOTE,
  orientPasses,
  type PassFilter,
  type PassPlayer,
  passNetwork,
  REVIEWED_ACCURACY_HINT,
  type Side,
  teamAccuracy,
  toArrows,
  VIDEO_PASS_CHECK,
  VIDEO_RED_HINT,
  videoAccuracyHint,
} from './passes';

type Name = (id: string | null | undefined) => string | null;
// «≈» — пока есть передачи из видео без проверки человеком и у проверки, не опубликованной как действия матча:
// найдено не каждое касание, и разбор не завершён. Опубликованная ручная разметка точна по тому, что размечено.
const reviewedPasses = (stats: TeamActionStats) =>
  stats.rows.some((r) => r.category === 'passes' && r.source === 'cv_reviewed');
const autoPasses = (stats: TeamActionStats) =>
  reviewedPasses(stats) || stats.pass_players.some((p) => p.verified < p.total);
// Сколько передач проверено, когда проверка начата, но не закончена.
function reviewProgress(stats: TeamActionStats) {
  const total = stats.pass_players.reduce((s, p) => s + p.total, 0);
  const verified = stats.pass_players.reduce((s, p) => s + p.verified, 0);
  return verified > 0 && verified < total ? `Проверено ${verified} из ${total} передач.` : null;
}
const metres = (v: number | null) => (v == null ? '—' : v.toLocaleString('ru-RU', { maximumFractionDigits: 1 }));

// Доли точных, неточных и с неизвестным исходом — полосой; подпись «точных / с исходом · %».
function AccuracyBar({ side, total, accurate, known }: { side: Side; total: number; accurate: number; known: number }) {
  if (!total) return null;
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
  // Есть передачи из видео без проверки — к ним относится замеренная погрешность.
  const unchecked = stats.pass_players.some((p) => p.verified < p.total);
  // Мяч искал общий детектор (запись трансляции): замер журналов к этим передачам не относится.
  const general = stats.video_ball === 'general';
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
              <b
                className="num pass-percent"
                title={approx ? (unchecked ? videoAccuracyHint(stats) : REVIEWED_ACCURACY_HINT) : undefined}
              >
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
          unchecked && !general && shown.some((p) => p.success === false && !p.verified) ? VIDEO_RED_HINT : null,
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
      {reviewProgress(stats) && <p className="muted small">{reviewProgress(stats)}</p>}
      {approx && reviewedPasses(stats) && <p className="muted small pass-caveat">{REVIEWED_ACCURACY_HINT}</p>}
      {approx && unchecked && general && <p className="muted small pass-caveat">{GENERAL_BALL_CAVEAT}</p>}
      {approx && unchecked && !general && (
        <p className="muted small pass-caveat">
          ≈ — передачи из видео: находится около двух третей, процент точности расходится с ручным журналом до{' '}
          {VIDEO_PASS_CHECK.maxErrorPp} п.п., а из неточных по видео верны {VIDEO_PASS_CHECK.redTrue} из{' '}
          {VIDEO_PASS_CHECK.redTotal} (замер на {VIDEO_PASS_CHECK.journals} журналах, {VIDEO_PASS_CHECK.passes}{' '}
          передачи). Процент игрока — от {MIN_PASSES_FOR_PERCENT} передач с известным исходом.
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
      {approx && (
        <p className="muted small">
          {stats.pass_players.some((p) => p.verified < p.total) ? videoAccuracyHint(stats) : REVIEWED_ACCURACY_HINT}
        </p>
      )}
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

// Сеть передач команды, как у аналитических сайтов: узлы — средние позиции, толщина — число точных передач.
export function PassNetworkStats({
  stats,
  homeName,
  awayName,
  name,
  number,
}: {
  stats: TeamActionStats;
  homeName: string;
  awayName: string;
  name: Name;
  number: Name;
}) {
  // Сеть открывается на команде, у которой она есть: у хозяев может не быть назначенных игроков.
  const [side, setSide] = useState<Side>(() =>
    passNetwork(stats, 'home').nodes.length || !passNetwork(stats, 'away').nodes.length ? 'home' : 'away',
  );
  const network = passNetwork(stats, side);
  const [threshold, setThreshold] = useState<number | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  if (!stats.pitch) return null;
  const min = Math.min(threshold ?? defaultThreshold(network.maxCount), Math.max(1, network.maxCount));
  const links = network.edges.filter((e) => e.count >= min);
  const label = (id: string) => name(id) ?? 'Игрок';
  const dots = network.nodes
    .map((n) => ({
      id: n.playerId,
      x: n.x,
      y: n.y,
      touches: n.made + n.received,
      number: number(n.playerId),
      label: label(n.playerId),
    }))
    .sort((a, b) => b.touches - a.touches);
  const chosen = selected ? network.nodes.find((n) => n.playerId === selected) : undefined;
  const top = (list: NetworkEdge[]) => [...list].sort((a, b) => b.count - a.count)[0];
  const to = chosen && top(network.edges.filter((e) => e.from === chosen.playerId));
  const from = chosen && top(network.edges.filter((e) => e.to === chosen.playerId));
  const sideName = side === 'home' ? homeName : awayName;
  const switcher = (
    <div className="segmented" role="group" aria-label="Команда сети">
      {(['home', 'away'] as const).map((s) => (
        <button
          key={s}
          type="button"
          className={side === s ? 'active' : ''}
          aria-pressed={side === s}
          onClick={() => {
            setSide(s);
            setSelected(null);
            setThreshold(null);
          }}
        >
          {s === 'home' ? homeName : awayName}
        </button>
      ))}
    </div>
  );
  // Переключатель остаётся и без сети: у другой команды она может быть.
  if (!network.nodes.length)
    return (
      <div className="pass-stats">
        <div className="pass-filters">{switcher}</div>
        <p className="muted">Для сети нужны точные передачи с известным адресатом.</p>
      </div>
    );
  return (
    <div className="pass-stats">
      <div className="pass-filters">
        {switcher}
        {network.maxCount > 1 && (
          <label className="network-threshold">
            <span>
              Связки от <b className="num">{min}</b> {plural(min, 'передачи', 'передач', 'передач')}
            </span>
            <input
              type="range"
              min={1}
              max={network.maxCount}
              value={min}
              aria-label="Порог связки, передач"
              onChange={(e) => setThreshold(Number(e.target.value))}
            />
          </label>
        )}
      </div>
      {chosen && (
        <p className="pass-chosen" role="status">
          <b>{label(chosen.playerId)}</b>: передач {chosen.made}, точных приёмов {chosen.received}
          {to || from ? '; чаще всего: ' : ''}
          {[
            to ? `отдаёт → ${label(to.to)} (${to.count})` : null,
            from ? `получает ← ${label(from.from)} (${from.count})` : null,
          ]
            .filter(Boolean)
            .join(', ')}
        </p>
      )}
      <PassNetwork
        dots={dots}
        links={links}
        lengthM={stats.pitch.length_m}
        widthM={stats.pitch.width_m}
        side={side}
        selected={selected}
        onSelect={setSelected}
        label={`Сеть передач: ${sideName}, игроков ${dots.length}, связок ${links.length}`}
      />
      <p className="muted small network-note">
        {[
          network.attackRight ? `${sideName} атакует вправо →.` : ORIENTATION_NOTE[network.orientation],
          network.source === 'video'
            ? 'Узел — средняя позиция игрока по видео.'
            : 'Узел — средняя точка передач и приёмов игрока.',
          'Размер — передачи и приёмы, толщина стрелки — число точных передач.',
          network.withoutPosition ? `Без позиции на видео: ${network.withoutPosition}.` : null,
          autoPasses(stats) ? '≈ — передачи из видео: находится около двух третей.' : null,
        ]
          .filter(Boolean)
          .join(' ')}
      </p>
      <ol className="network-legend" aria-label="Игроки сети">
        {dots.map((d) => (
          <li key={d.id}>
            <button
              type="button"
              className="link-button"
              aria-pressed={d.id === selected}
              onClick={() => setSelected(d.id === selected ? null : d.id)}
            >
              <span className={`network-dot ${side}`}>{d.number ?? ''}</span>
              {d.label}
            </button>
            <span className="muted num"> · касаний {d.touches}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

function plural(n: number, one: string, few: string, many: string) {
  const mod10 = n % 10,
    mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
  return many;
}
