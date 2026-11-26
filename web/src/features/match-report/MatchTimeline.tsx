import { CircleDot, Target, Timer } from 'lucide-react';
import type { ReactElement } from 'react';
import type { PublicProtocol } from '../../api/domain';
import { BOARD_HINT, BOARD_NOTE, type BoardGoal, boardMinute } from './board';

type Event = PublicProtocol['protocol']['events'][number];
type Side = 'home' | 'away';
export type Scorer = { key: string; name: string; minute: string; note: string | null };

// Минута матча по чистому времени: смещение тайма + прошедшее время, как «23'».
export function eventMinute(p: PublicProtocol, e: Event): string {
  if (e.period == null) return '—';
  if (e.elapsed_ms == null) return `${e.period}-й т.`;
  const periods = p.regulation.rules.periods_s;
  const offset = periods.slice(0, e.period - 1).reduce((a, b) => a + b, 0);
  return `${Math.floor(offset / 60) + Math.floor(e.elapsed_ms / 60000) + 1}'`;
}
const order = (e: Event) => [e.period ?? 99, e.elapsed_ms ?? Number.MAX_SAFE_INTEGER];
const sorted = (events: Event[]) =>
  [...events].sort((a, b) => {
    const x = order(a),
      y = order(b);
    return x[0] - y[0] || x[1] - y[1];
  });
const scoringSide = (e: Event): Side | null =>
  e.kind !== 'goal' || !e.side ? null : 'own_goal' in e && e.own_goal ? (e.side === 'home' ? 'away' : 'home') : e.side;
const playerName = (p: PublicProtocol, id: string | null | undefined) =>
  id ? (p.lineup.find((l) => l.player_id === id)?.display_name ?? 'Игрок') : null;

// Авторы голов под счётом: по стороне, получившей гол. Голы одного автора — одной строкой минут, голы без
// автора — одной строкой минут без подписи (как в FotMob), а не строкой «Автор не указан» на каждый гол.
export function goalScorers(p: PublicProtocol): Record<Side, Scorer[]> {
  const out: Record<Side, Scorer[]> = { home: [], away: [] };
  for (const e of sorted(p.protocol.events)) {
    const side = scoringSide(e);
    if (!side) continue;
    const own = 'own_goal' in e && e.own_goal;
    const pen = 'from_penalty' in e && e.from_penalty;
    const author = 'player_id' in e ? (e.player_id ?? null) : null;
    const note = own ? 'автогол' : pen ? 'пен.' : null;
    const key = `${author ?? ''}|${note ?? ''}`;
    const same = out[side].find((s) => s.key === key);
    if (same) same.minute = `${same.minute} ${eventMinute(p, e)}`;
    else
      out[side].push({ key, name: author ? (playerName(p, author) ?? 'Игрок') : '', minute: eventMinute(p, e), note });
  }
  return out;
}

const CARD = { yellow: 'Жёлтая карточка', second_yellow: 'Вторая жёлтая', red: 'Красная карточка' } as const;
const SHOWN = new Set(['goal', 'card', 'timeout', 'penalty_awarded', 'penalty_attempt']);

function Line({ p, e, score }: { p: PublicProtocol; e: Event; score: string | null }) {
  const name = playerName(p, 'player_id' in e ? e.player_id : null);
  let icon: ReactElement;
  let title: string;
  let detail: string | null = name;
  if (e.kind === 'goal') {
    icon = <CircleDot className="ev-icon goal" />;
    title = `Гол${score ? ` · ${score}` : ''}`;
    const assist = 'assist_id' in e && e.assist_known ? playerName(p, e.assist_id) : null;
    detail = [
      name ?? 'Автор не указан',
      'own_goal' in e && e.own_goal ? 'автогол' : null,
      'from_penalty' in e && e.from_penalty ? 'с пенальти' : null,
      assist ? `пас: ${assist}` : null,
    ]
      .filter(Boolean)
      .join(' · ');
  } else if (e.kind === 'card') {
    const c = 'card' in e ? e.card : 'yellow';
    icon = <i className={`ev-card ${c === 'yellow' ? 'yellow' : 'red'}`} />;
    title = CARD[c as keyof typeof CARD];
  } else if (e.kind === 'timeout') {
    icon = <Timer className="ev-icon" />;
    title = 'Тайм-аут';
    detail = null;
  } else {
    icon = <Target className="ev-icon" />;
    title =
      e.kind === 'penalty_awarded'
        ? 'Назначен пенальти'
        : `Пенальти: ${({ goal: 'гол', saved: 'сейв', off_target: 'мимо', unknown: 'исход неизвестен' } as Record<string, string>)['outcome' in e ? e.outcome : 'unknown']}`;
  }
  const content = (
    <span className="ev-body">
      {icon}
      <span>
        <b>{title}</b>
        {detail && <small>{detail}</small>}
      </span>
    </span>
  );
  return (
    <li className={`ev-row ${e.side ?? 'none'}`}>
      <span className="ev-side home">{e.side === 'home' && content}</span>
      <span className="ev-minute">{eventMinute(p, e)}</span>
      <span className="ev-side away">{e.side === 'away' && content}</span>
    </li>
  );
}

// Гол с табло трансляции: без автора, со счётом после него.
function BoardLine({ p, g }: { p: PublicProtocol; g: BoardGoal }) {
  const content = (
    <span className="ev-body">
      <CircleDot className="ev-icon goal" />
      <span>
        <b>{`Гол · ${g.score.home} : ${g.score.away}`}</b>
        <small>{BOARD_NOTE}</small>
      </span>
    </span>
  );
  return (
    <li className={`ev-row ${g.side}`}>
      <span className="ev-side home">{g.side === 'home' && content}</span>
      <span className="ev-minute">{boardMinute(p, g)}</span>
      <span className="ev-side away">{g.side === 'away' && content}</span>
    </li>
  );
}

// Лента в две стороны по минутам, разделители таймов со счётом после тайма. Голы табло трансляции
// (board) идут вместе с событиями протокола, когда своих голов в протоколе нет.
export function MatchTimeline({
  value: p,
  keyOnly = false,
  board = null,
}: {
  value: PublicProtocol;
  keyOnly?: boolean;
  board?: BoardGoal[] | null;
}) {
  const kinds = keyOnly ? new Set(['goal', 'card']) : SHOWN;
  type Item = { period: number | null | undefined; at: number; event?: Event; goal?: BoardGoal };
  const all: Item[] = [
    ...sorted(p.protocol.events.filter((e) => kinds.has(e.kind))).map((e) => ({
      period: e.period,
      at: e.elapsed_ms ?? Number.MAX_SAFE_INTEGER,
      event: e,
    })),
    ...(board ?? []).map((g) => ({ period: g.period, at: g.elapsedMs, goal: g })),
  ].sort((a, b) => (a.period ?? 99) - (b.period ?? 99) || a.at - b.at);
  if (!all.length)
    return (
      <p className="muted">
        {keyOnly ? 'Голов и карточек в опубликованном протоколе нет.' : 'Событий в опубликованном протоколе нет.'}
      </p>
    );
  const score = { home: 0, away: 0 };
  const items: ReactElement[] = [];
  let period: number | null | undefined;
  for (const item of all) {
    if (item.period !== period) {
      if (period !== undefined)
        items.push(
          <li key={`break:${period}`} className="ev-break">
            {period == null ? 'Без времени' : `Конец ${period}-го тайма`} · {score.home} : {score.away}
          </li>,
        );
      period = item.period;
    }
    if (item.goal) {
      score[item.goal.side]++;
      items.push(<BoardLine key={item.goal.key} p={p} g={item.goal} />);
      continue;
    }
    const e = item.event!;
    const side = scoringSide(e);
    if (side) score[side]++;
    items.push(<Line key={e.id} p={p} e={e} score={side ? `${score.home} : ${score.away}` : null} />);
  }
  return (
    <>
      <ol className="timeline" aria-label="Лента матча">
        {items}
      </ol>
      {board && board.length > 0 && <p className="muted small">{BOARD_HINT}</p>}
    </>
  );
}
