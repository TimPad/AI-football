import { type KeyboardEvent, type MouseEvent, useEffect, useRef, useState } from 'react';
import { api, errorText } from '../../api/client';
import type { Match } from '../../api/domain';
import type { components } from '../../api/types';
import { PitchLines } from '../../components/pitch/PitchMap';
import { Loading, useLoad } from '../../components/ui';
import { useDraft } from '../protocol/drafts';
import { CommandStatus, useRatingCommand } from './commands';
import {
  buildDoc,
  matchClock,
  type ProtocolGoal,
  protocolGoals,
  SHOT_TAGS,
  type Side,
  TAG_KINDS,
  TAG_LABEL,
  type Tag,
  type TagKind,
  tagsFromDoc,
} from './tagging';
import type { Actions, ActionsVersion } from './types';
import './tagging.css';

type Moments = components['schemas']['RunMoments'];
type Person = { player_id: string; display_name: string; side: string; shirt_number?: string | number | null };
type Draft = { revision: number; tags: Tag[]; complete: boolean };
type Mark = { key: string; at: number; seek: number; label: string; side: Side | null; done: boolean };

const KINDS = new Set<string>(TAG_KINDS);
function validDraft(v: unknown): v is Draft {
  const d = v as Draft;
  return (
    !!d &&
    Number.isInteger(d.revision) &&
    typeof d.complete === 'boolean' &&
    Array.isArray(d.tags) &&
    d.tags.every(
      (t) =>
        t &&
        typeof t.id === 'string' &&
        KINDS.has(t.kind) &&
        (t.side === 'home' || t.side === 'away') &&
        Number.isFinite(t.ms),
    )
  );
}
const videoClock = (ms: number) => {
  const s = Math.floor(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
};
const newId = () => crypto.randomUUID();

// Разметка ударов и защиты по видео: запись открывается с компьютера (на сервер не уходит), отметка ставится
// кнопкой или клавишей в текущий момент записи. Закладки — голы по табло, повторы трансляции и удары,
// найденные обработчиком (находится треть ударов, верны две трети), — помогают не смотреть матч подряд.
export function VideoTagging({ match, actorId, onSaved }: { match: Match; actorId: string; onSaved?: () => void }) {
  const state = useLoad(() => api<Actions>(`/matches/${match.id}/performance-actions`), match.id);
  const doc = state.data?.current?.document;
  const runId = doc?.clock_basis === 'video' ? (doc.source_analysis_run_id ?? null) : null;
  const moments = useLoad(
    async () => (runId ? api<Moments>(`/matches/${match.id}/analysis/runs/${runId}/moments`) : undefined),
    runId ?? '',
  );
  if (!state.data) return <Loading error={state.error} retry={state.reload} />;
  if (!runId) return null;
  if (!moments.data) return <Loading error={moments.error} retry={moments.reload} />;
  return (
    <TaggingForm
      key={state.data.revision}
      value={state.data}
      moments={moments.data}
      match={match}
      actorId={actorId}
      onSaved={() => {
        state.reload();
        onSaved?.();
      }}
    />
  );
}

function TaggingForm({
  value,
  moments,
  match,
  actorId,
  onSaved,
}: {
  value: Actions;
  moments: Moments;
  match: Match;
  actorId: string;
  onSaved: () => void;
}) {
  const current = value.current!;
  const draft = useDraft<Draft>(
    `aifootball:video-tagging:${actorId}:${value.match_id}`,
    { revision: value.revision, tags: tagsFromDoc(current.document), complete: false },
    validDraft,
  );
  const command = useRatingCommand<ActionsVersion>(
    `aifootball:video-tagging-command:${actorId}:${value.match_id}`,
    () => {
      draft.clear();
      onSaved();
    },
  );
  const [selected, setSelected] = useState<string | null>(null);
  const [placing, setPlacing] = useState(false);
  const [pushing, setPushing] = useState<string | null>(null);
  const video = useRef<HTMLVideoElement>(null);
  const [url, setUrl] = useState<string | null>(null);
  const [now, setNow] = useState(0);
  const [rate, setRate] = useState(1);
  useEffect(() => () => void (url && URL.revokeObjectURL(url)), [url]);
  const tags = draft.value.tags;
  const locked = command.locked || draft.corrupt;
  const periods = ((value.rules as { periods_s?: number[] }).periods_s ?? []).map(Number);
  const halves = moments.halves;
  const clock = (ms: number) => matchClock(halves, periods, ms);
  const lineup = value.lineup as Person[];
  const name = (id: string | null) => (id ? (lineup.find((p) => p.player_id === id)?.display_name ?? 'Игрок') : null);
  const team = (side: Side) => (side === 'home' ? match.home.team.name : match.away.team.name);
  const pitch = value.pitch as { length_m: number; width_m: number } | null;
  const tag = tags.find((t) => t.id === selected) ?? null;
  // Плашка табло — команда по счёту протокола, как на странице матча.
  const score = match.projection.effective_score as { home: number | null; away: number | null };
  const board = moments.board_final;
  const leftSide: Side | null =
    board && score.home === board.left && score.away === board.right
      ? 'home'
      : board && score.home === board.right && score.away === board.left
        ? 'away'
        : null;
  const plateSide = (plate: 'left' | 'right'): Side | null =>
    leftSide ? (plate === 'left' ? leftSide : leftSide === 'home' ? 'away' : 'home') : null;

  function setTags(next: Tag[], complete = draft.value.complete) {
    draft.change({ ...draft.value, tags: [...next].sort((a, b) => a.ms - b.ms), complete });
  }
  function change(id: string, patch: Partial<Tag>) {
    setTags(tags.map((t) => (t.id === id ? { ...t, ...patch } : t)));
  }
  function add(kind: TagKind, side: Side) {
    const v = video.current;
    if (!url || !v || locked) return;
    const t: Tag = { id: newId(), kind, side, ms: Math.round(v.currentTime * 1000), playerId: null, xy: null };
    setTags([...tags, t]);
    setSelected(t.id);
    setPlacing(SHOT_TAGS.has(kind) && !!pitch);
  }
  function remove(id: string) {
    setTags(tags.filter((t) => t.id !== id));
    if (selected === id) setSelected(null);
  }
  function seek(s: number) {
    const v = video.current;
    if (!v) return;
    v.currentTime = Math.max(0, s);
  }
  function toggle() {
    const v = video.current;
    if (!v) return;
    if (v.paused) {
      const started = v.play();
      if (started && typeof started.catch === 'function') started.catch(() => undefined);
    } else v.pause();
  }
  function onKey(e: KeyboardEvent<HTMLDivElement>) {
    const target = (e.target as HTMLElement).tagName;
    if (locked || ['INPUT', 'SELECT', 'TEXTAREA'].includes(target)) return;
    const digit = /^(?:Digit|Numpad)([1-6])$/.exec(e.code);
    if (digit) {
      e.preventDefault();
      add(TAG_KINDS[Number(digit[1]) - 1], e.shiftKey ? 'away' : 'home');
    } else if (e.code === 'Space' && target !== 'VIDEO' && target !== 'BUTTON') {
      e.preventDefault();
      toggle();
    } else if ((e.code === 'ArrowLeft' || e.code === 'ArrowRight') && target !== 'VIDEO') {
      e.preventDefault();
      seek(now / 1000 + (e.code === 'ArrowLeft' ? -1 : 1) * (e.shiftKey ? 1 : 5));
    } else if ((e.code === 'Backspace' || e.code === 'Delete') && selected) {
      e.preventDefault();
      remove(selected);
    }
  }
  function place(e: MouseEvent<SVGSVGElement>) {
    if (!tag || !pitch || !placing || locked) return;
    const box = e.currentTarget.getBoundingClientRect();
    const x = ((e.clientX - box.left) / box.width) * pitch.length_m;
    const y = ((e.clientY - box.top) / box.height) * pitch.width_m;
    const clamp = (v: number, hi: number) => Math.round(Math.min(Math.max(v, 0), hi) * 10) / 10;
    change(tag.id, { xy: [clamp(x, pitch.length_m), clamp(y, pitch.width_m)] });
    setPlacing(false);
  }
  const near = (from: number, to: number, kinds?: (k: TagKind) => boolean) =>
    tags.some((t) => t.ms / 1000 >= from && t.ms / 1000 <= to && (!kinds || kinds(t.kind)));
  const marks: Mark[] = [
    ...moments.board_goals.map((g, i) => ({
      key: `goal:${i}`,
      at: g.t_s,
      seek: g.t_s - 25,
      label: `Гол по табло${plateSide(g.plate) ? ` · ${team(plateSide(g.plate)!)}` : ''}`,
      side: plateSide(g.plate),
      // Табло меняют после гола (до ~15 с) — гол ищется до смены счёта.
      done: near(g.t_s - 45, g.t_s + 2, (k) => k === 'goal'),
    })),
    ...moments.replays.map(([a, b], i) => ({
      key: `replay:${i}`,
      at: a,
      seek: a - 20,
      label: 'Повтор трансляции — опасный момент',
      side: null,
      done: near(a - 45, b),
    })),
    ...moments.shots.map((s, i) => ({
      key: `shot:${i}`,
      at: s.t_s,
      seek: s.t_s - 4,
      label: `Удар? по видео${s.on_target ? ', в створ' : ''} · ${team(s.side)}`,
      side: s.side,
      done: near(s.t_s - 4, s.t_s + 4, (k) => SHOT_TAGS.has(k)),
    })),
  ].sort((a, b) => a.at - b.at);
  const counts = (side: Side, kinds: TagKind[]) => tags.filter((t) => t.side === side && kinds.includes(t.kind)).length;
  const goalsInProtocol: ProtocolGoal[] = (current.canonical_actions as Record<string, unknown>[])
    .filter((r) => r.kind === 'goal' && (r.side === 'home' || r.side === 'away'))
    .map((r) => ({
      id: String(r.id),
      side: r.side as Side,
      period: (r.period as number | null) ?? null,
      elapsed_ms: (r.elapsed_ms as number | null) ?? null,
    }));
  const taggedGoals = tags.filter((t) => t.kind === 'goal');
  const protocolHasGoals = (match.protocol.events ?? []).some((e) => e.kind === 'goal');

  function save() {
    const { doc } = buildDoc(current.document, tags, goalsInProtocol, draft.value.complete, newId);
    void command.execute(
      `/matches/${value.match_id}/performance-actions`,
      {
        expected_revision: value.revision,
        expected_match_revision: value.match_revision,
        status: 'confirmed',
        document: doc,
      },
      'PUT',
    );
  }
  // Голы разметки — в черновик протокола: тайм, время от начала тайма, автор. Подтверждает протокол организатор.
  async function pushGoals() {
    setPushing('Вношу голы в протокол…');
    try {
      let revision = (await api<Match>(`/matches/${match.id}`)).revision;
      const send = async (kind: string, payload: unknown) => {
        const m = await api<Match>(`/matches/${match.id}/commands`, {
          method: 'POST',
          body: JSON.stringify({ request_id: newId(), expected_revision: revision, kind, payload }),
        });
        revision = m.revision;
      };
      if (!match.protocol.draft) await send('reopen', {});
      for (const goal of protocolGoals(tags, halves, periods, newId)) await send('add_event', { event: goal });
      setPushing(
        'Голы внесены в черновик протокола. Подтвердите и опубликуйте протокол в разделе «Протокол → События», затем сохраните разметку снова — голы свяжутся с протоколом.',
      );
    } catch (e) {
      setPushing(`Голы не внесены: ${errorText(e)}`);
    }
  }

  return (
    <section className="surface video-tagging" aria-label="Разметка ударов и защиты">
      <div className="panel-head">
        <div>
          <h2>Разметка ударов и защиты</h2>
          <p className="muted">
            Отметьте удары, голы, отборы и перехваты по записи. Закладки — голы по табло, повторы трансляции и удары,
            найденные по видео. Сохранённая разметка видна зрителям опубликованного видеоанализа.
          </p>
        </div>
      </div>
      {/* biome-ignore lint/a11y/noStaticElementInteractions: горячие клавиши разметки — для всей области, кнопки дублируют их */}
      <div className="tagging-grid" onKeyDown={onKey} tabIndex={-1}>
        <div className="tagging-main">
          <div className="pass-clip">
            {url ? (
              <video
                ref={video}
                src={url}
                controls
                muted
                playsInline
                aria-label="Запись матча"
                onTimeUpdate={(e) => setNow(Math.round(e.currentTarget.currentTime * 1000))}
              />
            ) : (
              <p className="muted small">
                Откройте ту же запись, что обрабатывалась: время отметок — время этого файла. Файл остаётся на
                компьютере.
              </p>
            )}
            <div className="row wrap">
              <label className="button">
                {url ? 'Открыть другую запись' : 'Открыть запись матча'}
                <input
                  type="file"
                  accept="video/*"
                  hidden
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) setUrl(URL.createObjectURL(f));
                    e.target.value = '';
                  }}
                />
              </label>
              {url && (
                <>
                  <span className="num muted">
                    {videoClock(now)} · {clock(now).minute}
                    {clock(now).inside ? ` · ${clock(now).period}-й тайм` : ' · вне таймов'}
                  </span>
                  <div className="segmented" role="group" aria-label="Скорость">
                    {[1, 1.5, 2].map((r) => (
                      <button
                        key={r}
                        type="button"
                        className={rate === r ? 'active' : ''}
                        aria-pressed={rate === r}
                        onClick={() => {
                          setRate(r);
                          if (video.current) video.current.playbackRate = r;
                        }}
                      >
                        {r}×
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>
          </div>
          <div className="tag-buttons">
            {(['home', 'away'] as const).map((side) => (
              <div key={side} className="tag-row" role="group" aria-label={`Отметки: ${team(side)}`}>
                <span className="tag-team">
                  <i className={`side-dot ${side}`} /> {team(side)}
                </span>
                {TAG_KINDS.map((kind, i) => (
                  <button key={kind} type="button" disabled={!url || locked} onClick={() => add(kind, side)}>
                    {TAG_LABEL[kind]}{' '}
                    <kbd>
                      {side === 'away' ? '⇧' : ''}
                      {i + 1}
                    </kbd>
                  </button>
                ))}
              </div>
            ))}
            <p className="muted small">
              Цифры 1–6 — хозяева, с Shift — гости. Пробел — пауза, ← → — 5 с назад и вперёд (с Shift — 1 с), Backspace
              — удалить выбранную отметку. Удар в створ без гола — сейв соперника, заблокированный — блок соперника,
              отбор — выигранное единоборство.
            </p>
          </div>
          {pitch && (
            <figure className="tagging-pitch pitch-map">
              <svg
                viewBox={`0 0 ${pitch.length_m} ${pitch.width_m}`}
                role="img"
                aria-label="Поле: точки ударов"
                className={placing ? 'placing' : ''}
                onClick={place}
              >
                <rect className="pitch-surface" x="0" y="0" width={pitch.length_m} height={pitch.width_m} />
                <PitchLines lengthM={pitch.length_m} widthM={pitch.width_m} />
                {tags
                  .filter((t) => t.xy)
                  .map((t) => (
                    <circle
                      key={t.id}
                      className={`tag-point ${t.side}${t.id === selected ? ' selected' : ''}${t.kind === 'goal' ? ' goal' : ''}`}
                      cx={t.xy![0]}
                      cy={t.xy![1]}
                      r={t.id === selected ? 0.8 : 0.55}
                    />
                  ))}
              </svg>
              <figcaption className="muted small">
                {placing && tag
                  ? `Нажмите на поле — откуда удар (${TAG_LABEL[tag.kind].toLowerCase()}, ${videoClock(tag.ms)}). Поле — как на записи.`
                  : 'Точка удара — по кнопке «Точка» у отметки; нужна для карты ударов.'}
              </figcaption>
            </figure>
          )}
        </div>
        <div className="tagging-side">
          <h3>Отметки · {tags.length}</h3>
          <div className="table-scroll">
            <table className="tag-summary">
              <thead>
                <tr>
                  <th />
                  <th>Удары</th>
                  <th>В створ</th>
                  <th>Голы</th>
                  <th>Отборы</th>
                  <th>Перехваты</th>
                </tr>
              </thead>
              <tbody>
                {(['home', 'away'] as const).map((side) => (
                  <tr key={side}>
                    <th scope="row">{team(side)}</th>
                    <td className="num">{counts(side, ['on_target', 'off_target', 'blocked', 'goal'])}</td>
                    <td className="num">{counts(side, ['on_target', 'goal'])}</td>
                    <td className="num">{counts(side, ['goal'])}</td>
                    <td className="num">{counts(side, ['tackle'])}</td>
                    <td className="num">{counts(side, ['interception'])}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ol className="tag-items" aria-label="Отметки">
            {tags.map((t) => (
              <li key={t.id} aria-current={t.id === selected ? 'true' : undefined}>
                <button
                  type="button"
                  className="link-button"
                  onClick={() => (setSelected(t.id), seek(t.ms / 1000 - 3))}
                >
                  <span className="num">{clock(t.ms).minute}</span> <i className={`side-dot ${t.side}`} />{' '}
                  {TAG_LABEL[t.kind]}
                </button>
                <select
                  aria-label="Игрок"
                  disabled={locked}
                  value={t.playerId ?? ''}
                  onChange={(e) => change(t.id, { playerId: e.target.value || null })}
                >
                  <option value="">Игрок не указан</option>
                  {lineup
                    .filter((p) => p.side === t.side)
                    .map((p) => (
                      <option key={p.player_id} value={p.player_id}>
                        {p.shirt_number ? `${p.shirt_number} · ` : ''}
                        {p.display_name}
                      </option>
                    ))}
                </select>
                {SHOT_TAGS.has(t.kind) && pitch && (
                  <button
                    type="button"
                    disabled={locked}
                    aria-pressed={placing && t.id === selected}
                    onClick={() => (setSelected(t.id), setPlacing(true))}
                  >
                    {t.xy ? 'Точка ✓' : 'Точка'}
                  </button>
                )}
                <button
                  type="button"
                  disabled={locked}
                  aria-label={`Удалить: ${TAG_LABEL[t.kind]}`}
                  onClick={() => remove(t.id)}
                >
                  ×
                </button>
                {name(t.playerId) && <span className="muted small">{name(t.playerId)}</span>}
              </li>
            ))}
          </ol>
          <h3>
            Закладки · {marks.filter((m) => m.done).length} из {marks.length}
          </h3>
          <ol className="tag-marks" aria-label="Закладки">
            {marks.map((m) => (
              <li key={m.key} className={m.done ? 'done' : ''}>
                <button type="button" className="link-button" disabled={!url} onClick={() => seek(m.seek)}>
                  <span className="num">{clock(m.at * 1000).minute}</span>{' '}
                  {m.side && <i className={`side-dot ${m.side}`} />} {m.label}
                </button>
                {m.done && <span className="muted small">отмечено</span>}
              </li>
            ))}
          </ol>
        </div>
      </div>
      <CommandStatus command={command} />
      <label className="check">
        <input
          type="checkbox"
          disabled={locked}
          checked={draft.value.complete}
          onChange={(e) => setTags(tags, e.target.checked)}
        />{' '}
        Весь матч просмотрен — разметка полная (иначе показатели помечаются как неполные)
      </label>
      <div className="team-save-bar">
        <button type="button" className="primary" disabled={locked || !tags.length} onClick={save}>
          Сохранить разметку
        </button>
        {taggedGoals.length > 0 && !protocolHasGoals && (
          <button type="button" disabled={locked || !!pushing?.endsWith('…')} onClick={() => void pushGoals()}>
            Внести голы в протокол ({taggedGoals.length})
          </button>
        )}
      </div>
      {pushing && <p role="status">{pushing}</p>}
      <p className="muted small">
        Сохранение создаёт новую версию действий: передачи и их проверка сохраняются. Голы — факты протокола: в разметке
        они связываются с голами протокола по порядку; пока голов в протоколе нет, они не входят в удары.
      </p>
    </section>
  );
}
