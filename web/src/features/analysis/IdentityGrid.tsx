import { useEffect, useMemo, useState } from 'react';
import type { AnalysisAssignment, AnalysisRun } from '../../api/domain';
import { CandidateThumb } from './CandidateThumb';
import { baseGroups, type Candidate, candidatesOf, clock, decisionOf } from './candidates';
import { applyClass, gridOrder, PAGE_TILES, rangeKeys } from './grid';
import { queuePlayers } from './queue';
import { lookIndex, trackSpan } from './similar';
import { useMatchModel } from './useMatchModel';

const EXCLUDE_KEYS = ['x', 'X', 'ч', 'Ч'];
type Click = { ctrlKey: boolean; metaKey: boolean; shiftKey: boolean };

// Сетка: кадры выбранного класса, кисть класса (щелчок присваивает, повторный снимает) и массовый выбор
// (Ctrl/⌘, Shift, «выделить все»). Плитка — снимок: после присвоения кадр остаётся на месте до «Обновить».
export function IdentityGrid({
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
  const names = useMemo(
    () =>
      new Map(run.context.rosters.map((p) => [p.player_id, p.shirt_number ? `№${p.shirt_number}` : p.display_name])),
    [run],
  );
  const [team, setTeam] = useState<'A' | 'B'>('A');
  const [show, setShow] = useState('open');
  const [similarTo, setSimilarTo] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const [tiles, setTiles] = useState(() => gridOrder(index, candidates, 'A', assignments, 'open', null));
  const [brush, setBrush] = useState<string | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [anchor, setAnchor] = useState<string | null>(null);
  const [clashed, setClashed] = useState<string[]>([]);
  const [blockedBy, setBlockedBy] = useState<Record<string, number>>({});
  // Отрезок фрагмента, который мешает назначению: человек видит, с чем именно одновременность.
  const blockText = (key: string) => {
    const span = blockedBy[key] != null ? trackSpan(index, blockedBy[key]) : null;
    return span ? `мешает фрагмент ${clock(span[0])}–${clock(span[1])} этого игрока` : 'игрок на площадке в это время';
  };
  const players = queuePlayers(index, run.context.rosters, sideMap[team], absent, assignments);
  const model = useMatchModel(
    index,
    candidates,
    team,
    players.map((p) => p.id),
    assignments,
  );
  const pages = Math.max(1, Math.ceil(tiles.length / PAGE_TILES));
  const visible = tiles.slice(page * PAGE_TILES, (page + 1) * PAGE_TILES);

  function refresh(next: { team?: 'A' | 'B'; show?: string; similarTo?: string | null } = {}) {
    const t = next.team ?? team;
    const s = next.show ?? show;
    const sim = next.similarTo === undefined ? similarTo : next.similarTo;
    // Кисть — игрок одной команды: на кадрах другой она назначила бы игрока чужой стороне.
    if (t !== team) setBrush(null);
    setTeam(t);
    setShow(s);
    setSimilarTo(sim);
    setPage(0);
    setSelected([]);
    setAnchor(null);
    setClashed([]);
    setTiles(gridOrder(index, candidates, t, assignments, s, sim, model));
  }
  function apply(keys: string[], value: string) {
    const picked = keys.flatMap((k) => {
      const c = byKey.get(k);
      return c ? [c] : [];
    });
    const { next, skipped, blockedBy: by } = applyClass(index, assignments, picked, value);
    setClashed(skipped);
    setBlockedBy(by);
    if (next !== assignments) onChange(next);
  }
  // Кнопка или клавиша класса: меняет кисть; при выделении — присваивает класс всем выделенным.
  function choose(value: string) {
    if (disabled) return;
    setBrush(value);
    if (!selected.length) return;
    apply(selected, value);
    setSelected([]);
    setAnchor(null);
  }
  function click(key: string, e: Click) {
    if (e.shiftKey && anchor) {
      setSelected((s) => [...new Set([...s, ...rangeKeys(tiles, anchor, key)])]);
      return;
    }
    if (e.ctrlKey || e.metaKey) {
      setSelected((s) => (s.includes(key) ? s.filter((k) => k !== key) : [...s, key]));
      setAnchor(key);
      return;
    }
    const c = byKey.get(key);
    if (disabled || brush === null || !c) return;
    const d = decisionOf(assignments, c.trackIds);
    const same = (brush === 'exclude' && d.kind === 'excluded') || (d.kind === 'player' && d.playerId === brush);
    apply([key], same ? '' : brush);
  }
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.target instanceof HTMLElement && ['INPUT', 'SELECT', 'TEXTAREA'].includes(e.target.tagName)) return;
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const player = players.find((p) => p.key && p.key === e.key);
      if (player) choose(player.id);
      else if (EXCLUDE_KEYS.includes(e.key)) choose('exclude');
      else if (e.key === 'Delete') choose('');
      else if (e.key === 'Escape') setSelected([]);
      else return;
      e.preventDefault();
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });
  const label = (c: Candidate) => {
    const d = decisionOf(assignments, c.trackIds);
    if (d.kind === 'player') return names.get(d.playerId ?? '') ?? '';
    if (d.kind === 'excluded') return 'не игрок';
    return d.kind === 'mixed' ? 'разные' : '';
  };

  return (
    <section className="identity-grid" aria-label="Сетка разметки">
      <div className="similar-head">
        <div className="segmented review-mode" role="group" aria-label="Команда">
          {(['A', 'B'] as const).map((t) => (
            <button type="button" key={t} aria-pressed={team === t} onClick={() => refresh({ team: t })}>
              {run.context.teams[sideMap[t]].name}
            </button>
          ))}
        </div>
        <label className="field">
          <span>Показать</span>
          <select aria-label="Показать" value={show} onChange={(e) => refresh({ show: e.target.value })}>
            <option value="open">Неназначенные</option>
            {players.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
            <option value="excluded">Не игроки матча</option>
            <option value="all">Все</option>
          </select>
        </label>
        <label className="field">
          <span>Порядок</span>
          <select
            aria-label="Порядок"
            value={similarTo ?? ''}
            onChange={(e) => refresh({ similarTo: e.target.value || null })}
          >
            <option value="">По времени</option>
            {players
              .filter((p) => p.mean)
              .map((p) => (
                <option key={p.id} value={p.id}>
                  Похожие на {p.label}
                </option>
              ))}
          </select>
        </label>
        <button type="button" onClick={() => refresh()}>
          Обновить
        </button>
      </div>
      <div className="grid-brush" role="group" aria-label="Кисть">
        {players.map((p) => (
          <button
            type="button"
            key={p.id}
            aria-pressed={brush === p.id}
            disabled={disabled}
            onClick={() => choose(p.id)}
          >
            {p.key ? `${p.key} · ` : ''}
            {p.label}
          </button>
        ))}
        <button type="button" aria-pressed={brush === 'exclude'} disabled={disabled} onClick={() => choose('exclude')}>
          X · Не игрок матча
        </button>
        <button type="button" aria-pressed={brush === ''} disabled={disabled} onClick={() => choose('')}>
          Delete · Снять
        </button>
      </div>
      <div className="row wrap">
        <span className="muted small num" role="status" aria-label="Выделение">
          выделено: {selected.length}
        </span>
        <button type="button" disabled={!visible.length} onClick={() => setSelected(visible)}>
          Выделить все на странице
        </button>
        <button type="button" disabled={!selected.length} onClick={() => setSelected([])}>
          Снять выделение
        </button>
      </div>
      {visible.length ? (
        <ul className="grid-tiles">
          {visible.map((key) => {
            const c = byKey.get(key);
            if (!c) return null;
            const on = selected.includes(key);
            const bad = clashed.includes(key);
            return (
              <li key={key}>
                <button
                  type="button"
                  className={`grid-tile${on ? ' selected' : ''}${bad ? ' clash' : ''}`}
                  aria-label={`Фрагмент ${clock(c.span[0])}–${clock(c.span[1])}`}
                  aria-pressed={on}
                  title={bad ? blockText(key) : undefined}
                  onClick={(e) => click(key, e)}
                >
                  <CandidateThumb run={run} index={index} candidate={c} className="tile" />
                  <span className="grid-label">{label(c) || '—'}</span>
                  <span className="muted small num">
                    {clock(c.span[0])}–{clock(c.span[1])}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="muted">Кадров этого класса нет.</p>
      )}
      {clashed.length > 0 && (
        <p className="warning small" role="status" aria-label="Не назначено">
          Не назначено из-за одновременности: {clashed.length}
          {clashed.slice(0, 3).map((key) => {
            const c = byKey.get(key);
            return c ? ` · ${clock(c.span[0])}–${clock(c.span[1])}: ${blockText(key)}` : '';
          })}
          {clashed.length > 3 ? ' · …' : ''}
        </p>
      )}
      {pages > 1 && (
        <div className="row">
          <button type="button" disabled={page === 0} onClick={() => setPage(page - 1)}>
            Назад
          </button>
          <span className="muted small num">
            {page + 1} из {pages}
          </span>
          <button type="button" disabled={page >= pages - 1} onClick={() => setPage(page + 1)}>
            Дальше
          </button>
        </div>
      )}
    </section>
  );
}
