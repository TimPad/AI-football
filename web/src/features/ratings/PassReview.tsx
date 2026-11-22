import { type KeyboardEvent, useEffect, useRef, useState } from 'react';
import { api } from '../../api/client';
import { PassMap } from '../../components/pitch/PassMap';
import { Loading, useLoad } from '../../components/ui';
import { useDraft } from '../protocol/drafts';
import { CommandStatus, useRatingCommand } from './commands';
import type { Action, ActionDoc, Actions, ActionsVersion } from './types';
import './pass-review.css';

type Review = 'auto' | 'checked';
type Draft = { revision: number; matchRevision: number; document: ActionDoc };
type Person = { player_id: string; display_name: string; side: string; shirt_number?: string | number | null };
type Filter = 'unchecked' | 'all' | 'failure';

function validDraft(v: unknown): v is Draft {
  const d = v as Draft;
  return (
    !!d &&
    Number.isInteger(d.revision) &&
    Number.isInteger(d.matchRevision) &&
    !!d.document &&
    Array.isArray(d.document.actions) &&
    d.document.actions.every((a) => a && typeof a.id === 'string' && typeof a.kind === 'string')
  );
}

// У автоматической версии, сохранённой до поля проверки, передачи считаются непроверенными.
const reviewOf = (a: Action, auto: boolean): Review | null =>
  (a.review as Review | null | undefined) ?? (auto && a.kind === 'pass' ? 'auto' : null);

const clock = (ms: number | null | undefined, video: boolean) => {
  if (ms == null) return '—';
  if (!video) return `${Math.floor(ms / 60000) + 1}'`;
  const s = Math.floor(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
};
const outcomeText = (a: Action) =>
  a.success === true ? 'точная' : a.success === false ? 'неточная' : 'исход неизвестен';
const statusText = (a: Action) =>
  a.review === 'auto' ? 'не проверена' : a.decision === 'rejected' ? 'не передача' : 'проверена';

// Проверка передач из видео: каждая передача — «верно», «неточная/точная», другой игрок или «не передача».
// Запись матча открывается с компьютера (на сервер не уходит): время передач из видео — время этого файла.
export function PassReview({ matchId, actorId, onSaved }: { matchId: string; actorId: string; onSaved?: () => void }) {
  const state = useLoad(() => api<Actions>(`/matches/${matchId}/performance-actions`), matchId);
  if (!state.data) return <Loading error={state.error} retry={state.reload} />;
  const current = state.data.current;
  const auto = !!current?.auto;
  if (!current || !current.document.actions.some((a) => a.kind === 'pass' && reviewOf(a, auto) !== null)) return null;
  return (
    <PassReviewForm
      key={current.revision}
      value={state.data}
      actorId={actorId}
      onSaved={() => {
        state.reload();
        onSaved?.();
      }}
    />
  );
}

function PassReviewForm({ value, actorId, onSaved }: { value: Actions; actorId: string; onSaved: () => void }) {
  const current = value.current!;
  const auto = !!current.auto;
  const draft = useDraft<Draft>(
    `aifootball:pass-review:${actorId}:${value.match_id}`,
    {
      revision: value.revision,
      matchRevision: value.match_revision,
      document: {
        ...current.document,
        actions: current.document.actions.map((a) => ({ ...a, review: reviewOf(a, auto) })),
      },
    },
    validDraft,
  );
  const command = useRatingCommand<ActionsVersion>(
    `aifootball:pass-review-command:${actorId}:${value.match_id}`,
    () => {
      draft.clear();
      onSaved();
    },
  );
  const doc = draft.value.document;
  const stale = draft.value.revision !== value.revision || draft.value.matchRevision !== value.match_revision;
  const locked = command.locked || draft.corrupt || stale;
  const video = doc.clock_basis === 'video';
  const lineup = value.lineup as Person[];
  const person = (id: string | null | undefined) => lineup.find((p) => p.player_id === id);
  const name = (id: string | null | undefined) => (id ? (person(id)?.display_name ?? 'Игрок') : null);
  const passes = doc.actions
    .filter((a) => a.kind === 'pass' && a.review != null)
    .sort((a, b) => (a.start_ms ?? 0) - (b.start_ms ?? 0));
  const checked = passes.filter((a) => a.review === 'checked').length;
  const [filter, setFilter] = useState<Filter>('unchecked');
  const [selected, setSelected] = useState<string | null>(
    () => passes.find((a) => a.review === 'auto')?.id ?? passes[0]?.id ?? null,
  );
  const shown = passes.filter((a) =>
    filter === 'unchecked'
      ? a.review === 'auto' || a.id === selected
      : filter === 'failure'
        ? a.success === false
        : true,
  );
  const pass = passes.find((a) => a.id === selected) ?? null;
  const side = pass?.side ?? null;
  const mates = lineup.filter((p) => p.side === side);

  function change(id: string, patch: Partial<Action>) {
    draft.change({
      ...draft.value,
      document: {
        ...doc,
        actions: doc.actions.map((a) => (a.id === id ? { ...a, ...patch, review: 'checked' } : a)),
      },
    });
  }
  // Следующая непроверенная после текущей, иначе просто следующая.
  function next(from = selected) {
    const at = passes.findIndex((a) => a.id === from);
    const later = [...passes.slice(at + 1), ...passes.slice(0, Math.max(0, at))];
    const target = later.find((a) => a.review === 'auto' && a.id !== from) ?? passes[at + 1] ?? null;
    if (target) setSelected(target.id);
  }
  function step(delta: number) {
    const at = passes.findIndex((a) => a.id === selected);
    const target = passes[at + delta];
    if (target) setSelected(target.id);
  }
  const accept = () => {
    if (!pass) return;
    change(pass.id, { decision: 'accepted' });
    next();
  };
  const reject = () => {
    if (!pass) return;
    change(pass.id, { decision: 'rejected' });
    next();
  };
  const toggle = () => {
    if (!pass) return;
    const ok = pass.success !== true;
    change(pass.id, {
      decision: 'accepted',
      success: ok,
      outcome: ok ? 'success' : 'failure',
      recipient_id: ok ? pass.recipient_id : null,
    });
  };
  function onKey(e: KeyboardEvent<HTMLDivElement>) {
    const tag = (e.target as HTMLElement).tagName;
    if (locked || ['INPUT', 'SELECT', 'TEXTAREA', 'VIDEO', 'BUTTON'].includes(tag)) return;
    const key = e.key.toLowerCase();
    const actions: Record<string, () => void> = {
      enter: accept,
      x: reject,
      ч: reject,
      t: toggle,
      е: toggle,
      arrowright: () => step(1),
      arrowleft: () => step(-1),
    };
    if (actions[key]) {
      e.preventDefault();
      actions[key]();
    }
  }
  function save(status: 'review' | 'confirmed') {
    void command.execute(
      `/matches/${value.match_id}/performance-actions`,
      {
        expected_revision: draft.value.revision,
        expected_match_revision: draft.value.matchRevision,
        status,
        document: doc,
      },
      'PUT',
    );
  }
  const pitch = value.pitch as { length_m: number; width_m: number } | null;
  return (
    <section className="surface pass-review" aria-label="Проверка передач">
      <div className="panel-head">
        <div>
          <h2>Проверка передач</h2>
          <p className="muted">
            Передачи найдены по видео: около двух третей, и неточные среди них часто ошибочны. Проверенные передачи в
            статистике идут без пометки «≈».
          </p>
        </div>
        <div className="pass-review-progress" role="status" aria-label="Проверено передач">
          <b className="num">
            {checked} / {passes.length}
          </b>
          <span className="muted small">проверено</span>
          <span className="pass-bar" aria-hidden="true">
            <span className="ok home" style={{ width: `${(100 * checked) / Math.max(1, passes.length)}%` }} />
          </span>
        </div>
      </div>
      {stale && (
        <div className="warning">
          <p>Версия действий изменилась, пока шла проверка. Начните проверку заново с новой версии.</p>
          <button type="button" onClick={() => draft.clear()}>
            Отбросить черновик проверки
          </button>
        </div>
      )}
      {/* biome-ignore lint/a11y/noStaticElementInteractions: горячие клавиши проверки — для всей области, кнопки дублируют их */}
      <div className="pass-review-grid" onKeyDown={onKey} tabIndex={-1}>
        <div className="pass-review-main">
          <ClipPlayer
            clip={
              pass && video && pass.start_ms != null
                ? { from: pass.start_ms / 1000 - 2, to: (pass.end_ms ?? pass.start_ms) / 1000 + 1.5, id: pass.id }
                : null
            }
            video={video}
          />
          {passes.length > 0 && checked === passes.length && (
            <p className="pass-review-done" role="note">
              Все передачи проверены — сохраните проверку.
            </p>
          )}
          {pass ? (
            <div className="pass-review-card">
              <p className="pass-review-title">
                <i className={`side-dot ${side}`} aria-hidden="true" />{' '}
                <b className="num">{clock(pass.start_ms, video)}</b> · {name(pass.player_id) ?? 'игрок не определён'}
                {pass.recipient_id ? ` → ${name(pass.recipient_id)}` : ''} · {outcomeText(pass)} ·{' '}
                <span className={`pass-status ${pass.review === 'auto' ? 'open' : pass.decision}`}>
                  {statusText(pass)}
                </span>
              </p>
              <div className="pass-review-actions">
                <button type="button" className="primary" disabled={locked} onClick={accept}>
                  Верно <kbd>Enter</kbd>
                </button>
                <button type="button" disabled={locked} onClick={toggle}>
                  {pass.success === true ? 'Неточная' : 'Точная'} <kbd>T</kbd>
                </button>
                <button type="button" disabled={locked} onClick={reject}>
                  Не передача <kbd>X</kbd>
                </button>
                <button type="button" disabled={locked} onClick={() => step(-1)} aria-label="Предыдущая передача">
                  ←
                </button>
                <button type="button" disabled={locked} onClick={() => step(1)} aria-label="Следующая передача">
                  →
                </button>
              </div>
              <div className="pass-review-people">
                <label>
                  <span className="muted small">Отдал</span>
                  <select
                    disabled={locked}
                    value={pass.player_id ?? ''}
                    onChange={(e) => change(pass.id, { decision: 'accepted', player_id: e.target.value || null })}
                  >
                    <option value="">Игрок не определён</option>
                    {mates.map((p) => (
                      <option key={p.player_id} value={p.player_id}>
                        {p.shirt_number ? `${p.shirt_number} · ` : ''}
                        {p.display_name}
                      </option>
                    ))}
                  </select>
                </label>
                {pass.success === true && (
                  <label>
                    <span className="muted small">Принял</span>
                    <select
                      disabled={locked}
                      value={pass.recipient_id ?? ''}
                      onChange={(e) => change(pass.id, { decision: 'accepted', recipient_id: e.target.value || null })}
                    >
                      <option value="">Игрок не определён</option>
                      {mates
                        .filter((p) => p.player_id !== pass.player_id)
                        .map((p) => (
                          <option key={p.player_id} value={p.player_id}>
                            {p.shirt_number ? `${p.shirt_number} · ` : ''}
                            {p.display_name}
                          </option>
                        ))}
                    </select>
                  </label>
                )}
              </div>
              {pitch && pass.start_xy && pass.end_xy && (
                <PassMap
                  passes={[
                    {
                      id: pass.id,
                      side: (side ?? 'home') as 'home' | 'away',
                      x1: pass.start_xy[0],
                      y1: pass.start_xy[1],
                      x2: pass.end_xy[0],
                      y2: pass.end_xy[1],
                      length: Math.hypot(pass.end_xy[0] - pass.start_xy[0], pass.end_xy[1] - pass.start_xy[1]),
                      success: pass.success ?? null,
                      player: name(pass.player_id),
                      recipient: name(pass.recipient_id),
                      time: clock(pass.start_ms, video),
                    },
                  ]}
                  lengthM={pitch.length_m}
                  widthM={pitch.width_m}
                  homeName="Хозяева"
                  awayName="Гости"
                  note="Как на видео: точки передачи и приёма по обработчику."
                  compact
                />
              )}
              <p className="muted small">
                Клавиши: Enter — верно, T — сменить исход, X — не передача, ← → — соседние передачи.
              </p>
            </div>
          ) : (
            <p className="muted">Все передачи проверены.</p>
          )}
        </div>
        <div className="pass-review-list">
          <div className="segmented" role="group" aria-label="Какие передачи показать">
            {(
              [
                ['unchecked', `Не проверены · ${passes.length - checked}`],
                ['failure', 'Неточные'],
                ['all', `Все · ${passes.length}`],
              ] as const
            ).map(([f, label]) => (
              <button
                key={f}
                type="button"
                className={filter === f ? 'active' : ''}
                aria-pressed={filter === f}
                onClick={() => setFilter(f)}
              >
                {label}
              </button>
            ))}
          </div>
          <ol className="pass-review-items" aria-label="Передачи">
            {shown.map((a) => (
              <li key={a.id} aria-current={a.id === selected ? 'true' : undefined}>
                <button type="button" className="link-button" onClick={() => setSelected(a.id)}>
                  <span className="num">{clock(a.start_ms, video)}</span> <i className={`side-dot ${a.side}`} />{' '}
                  {name(a.player_id) ?? 'игрок?'}
                  {a.recipient_id ? ` → ${name(a.recipient_id)}` : ''}
                </button>
                <span className={`pass-outcome ${a.success === false ? 'failure' : ''}`}>{outcomeText(a)}</span>
                <span className={`pass-status ${a.review === 'auto' ? 'open' : a.decision}`}>{statusText(a)}</span>
              </li>
            ))}
          </ol>
        </div>
      </div>
      <CommandStatus command={command} />
      <div className="team-save-bar">
        <button type="button" className="primary" disabled={locked || !checked} onClick={() => save('confirmed')}>
          Сохранить и подтвердить проверку
        </button>
        <button type="button" disabled={locked || !checked} onClick={() => save('review')}>
          Сохранить как черновик версии
        </button>
      </div>
      <p className="muted small">
        Сохранение создаёт новую версию действий: проверенные передачи, отклонённые не идут в статистику, непроверенные
        остаются с пометкой «≈». Зрителям статистика видна после публикации действий матча.
      </p>
    </section>
  );
}

// Запись матча с компьютера: при выборе передачи — переход за 2 с до неё и остановка через 1,5 с после приёма.
function ClipPlayer({ clip, video }: { clip: { from: number; to: number; id: string } | null; video: boolean }) {
  const [url, setUrl] = useState<string | null>(null);
  const ref = useRef<HTMLVideoElement>(null);
  const stopAt = useRef<number | null>(null);
  useEffect(() => () => void (url && URL.revokeObjectURL(url)), [url]);
  const play = () => {
    const v = ref.current;
    if (!v || !clip) return;
    v.currentTime = Math.max(0, clip.from);
    stopAt.current = clip.to;
    try {
      const started = v.play();
      if (started && typeof started.catch === 'function') started.catch(() => undefined);
    } catch {
      /* браузер без воспроизведения — остаётся перемотка */
    }
  };
  // biome-ignore lint/correctness/useExhaustiveDependencies: перематываем при смене передачи или файла
  useEffect(play, [clip?.id, url]);
  if (!video)
    return (
      <p className="muted small">
        Время передач — игровое: момент в записи неизвестен. Проверяйте по своей записи матча вручную.
      </p>
    );
  return (
    <div className="pass-clip">
      {url ? (
        <video
          ref={ref}
          src={url}
          controls
          muted
          playsInline
          aria-label="Запись матча"
          onTimeUpdate={(e) => {
            if (stopAt.current != null && e.currentTarget.currentTime >= stopAt.current) {
              e.currentTarget.pause();
              stopAt.current = null;
            }
          }}
        />
      ) : (
        <p className="muted small">
          Откройте ту же запись, что обрабатывалась: по выбранной передаче видео перейдёт к её моменту. Файл остаётся на
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
        {url && clip && (
          <button type="button" onClick={play}>
            Повторить момент
          </button>
        )}
      </div>
    </div>
  );
}
