import { Radio } from 'lucide-react';
import type { ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import type { PublicMatch } from '../../api/domain';
import { statuses } from '../../api/domain';
import { matchTime } from '../../features/matches/timezone';
import { publicForward } from '../../features/navigation/publicContext';
import { TeamCrest } from './MatchHeader';

export const ZONE = 'Europe/Moscow';
export type RowMatch = Pick<
  PublicMatch,
  | 'id'
  | 'scheduled_at'
  | 'venue_label'
  | 'hall'
  | 'home_name'
  | 'away_name'
  | 'status'
  | 'score'
  | 'broadcast_url'
  | 'broadcast_embed_url'
> & { home_logo_id?: string | null; away_logo_id?: string | null; tournament?: { name: string } };

export function Score({ match }: { match: Pick<RowMatch, 'score'> }) {
  const known = match.score.home != null && match.score.away != null;
  return (
    <span
      className="spectator-score"
      aria-label={known ? `Счёт ${match.score.home} : ${match.score.away}` : 'Результат не опубликован'}
    >
      {known ? `${match.score.home} : ${match.score.away}` : '— : —'}
    </span>
  );
}
const shortDate = (utc: string, zone: string) =>
  new Intl.DateTimeFormat('ru-RU', { timeZone: zone, day: 'numeric', month: 'short' }).format(new Date(utc));

// Одна строка матча на весь сайт: календарь, турнир, команда и кабинет.
// Вся строка открывает матч (растянутая ссылка), команды открываются со страницы матча.
// extra — отметка справа, например публикация в кабинете; её ссылки лежат поверх строки.
export function MatchRow({
  match: m,
  href,
  state,
  timezone = ZONE,
  withDate = false,
  withTournament = false,
  extra,
  onOpen,
}: {
  match: RowMatch;
  href?: string;
  state?: unknown;
  timezone?: string;
  withDate?: boolean;
  withTournament?: boolean;
  extra?: ReactNode;
  onOpen?: () => void;
}) {
  const location = useLocation();
  const forward = state ?? publicForward(location.state, 'calendar', location.pathname + location.search);
  const known = m.score.home != null && m.score.away != null;
  const status = m.status === 'scheduled' ? null : statuses[m.status];
  const place = m.hall?.name || m.venue_label;
  const video = !!(m.broadcast_url || m.broadcast_embed_url);
  const tournament = withTournament ? m.tournament?.name : null;
  return (
    <article className={`center-match ${m.status}`}>
      <span className="center-match-time">
        {withDate ? (
          <>
            <b>{shortDate(m.scheduled_at, timezone)}</b>
            <small>{matchTime(m.scheduled_at, timezone)}</small>
          </>
        ) : (
          <b>{matchTime(m.scheduled_at, timezone)}</b>
        )}
        {status && <small className="center-match-status">{status}</small>}
      </span>
      <span className="center-match-teams">
        <span>
          <TeamCrest name={m.home_name} logoId={m.home_logo_id} side="home" size="sm" />
          <b>{m.home_name}</b>
        </span>
        <span>
          <TeamCrest name={m.away_name} logoId={m.away_logo_id} side="away" size="sm" />
          <b>{m.away_name}</b>
        </span>
      </span>
      <span className="center-match-score">
        <Score match={m} />
        {m.status === 'live' && <small>Опубликованный счёт</small>}
      </span>
      {(tournament || place || video || extra) && (
        <span className="center-match-meta">
          {tournament && <span>{tournament}</span>}
          {place && <span>{place}</span>}
          {video && <Radio aria-label="Есть видео" />}
          {extra && <span className="center-match-extra">{extra}</span>}
        </span>
      )}
      <Link
        className="center-match-open"
        aria-label={`Открыть матч ${m.home_name} — ${m.away_name}${known ? `, ${m.score.home} : ${m.score.away}` : ''}`}
        state={forward}
        onClick={onOpen}
        to={href ?? `/watch/matches/${m.id}`}
      />
    </article>
  );
}
