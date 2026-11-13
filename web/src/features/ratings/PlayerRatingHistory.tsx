import { useEffect, useState } from 'react';
import { all, api } from '../../api/client';
import type { Tournament } from '../../api/domain';
import { Field, Loading, useLoad } from '../../components/ui';
import { MatchRating } from './MatchRating';
import { RankingTable } from './TournamentRatings';
import { type PlayerRatings, roles } from './types';
// tournamentIds — турниры, где игрок есть в опубликованных составах: в выборе только они, а единственный открывается сам.
export function PlayerRatingHistory({
  playerId,
  initialTournament = '',
  initialSnapshot = '',
  publicView = false,
  tournamentIds,
  onContext,
  onName,
}: {
  playerId: string;
  initialTournament?: string;
  initialSnapshot?: string;
  publicView?: boolean;
  tournamentIds?: string[];
  onContext?: (tid: string, snapshot: string) => void;
  onName?: (name: string | null) => void;
}) {
  const tournaments = useLoad(
    () => all<Tournament>(`${publicView ? '/public' : ''}/tournaments`),
    `${playerId}:${publicView}`,
  );
  const [tid, setTid] = useState(initialTournament);
  const [snapshot, setSnapshot] = useState(initialSnapshot);
  useEffect(() => {
    onContext?.(tid, snapshot);
  }, [tid, snapshot]);
  const own = tournamentIds && new Set(tournamentIds);
  const options = tournaments.data?.filter((t) => !own || own.has(t.id) || t.id === tid);
  useEffect(() => {
    if (!tid && own?.size === 1) setTid([...own][0]);
  }, [tournamentIds?.join()]);
  return (
    <section className="surface">
      <h2>Оценки</h2>
      <Field label="Турнир">
        <select
          value={tid}
          onChange={(e) => {
            setTid(e.target.value);
            setSnapshot('');
          }}
        >
          <option value="">Выберите турнир</option>
          {options?.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name} · {t.season}
            </option>
          ))}
        </select>
      </Field>
      {snapshot && (
        <>
          <p className="muted">Показана прежняя версия рейтинга.</p>
          <button onClick={() => setSnapshot('')}>Открыть текущую версию</button>
        </>
      )}
      {tid && (
        <History
          key={`${tid}:${playerId}:${snapshot}`}
          tid={tid}
          playerId={playerId}
          snapshotId={snapshot}
          publicView={publicView}
          onName={onName}
        />
      )}
    </section>
  );
}
function History({
  tid,
  playerId,
  snapshotId,
  publicView,
  onName,
}: {
  tid: string;
  playerId: string;
  snapshotId: string;
  publicView: boolean;
  onName?: (name: string | null) => void;
}) {
  const state = useLoad(
    () =>
      api<PlayerRatings>(
        `${publicView ? '/public' : ''}/players/${playerId}/ratings?tournament_id=${encodeURIComponent(tid)}${snapshotId ? `&snapshot_id=${encodeURIComponent(snapshotId)}` : ''}`,
      ),
    `${tid}:${playerId}:${snapshotId}`,
  );
  // Имя — из опубликованных строк выбранного издания, не из каталога.
  useEffect(() => {
    if (state.data)
      onName?.(
        state.data.matches[0]?.display_name ??
          state.data.summary.find((r) => r.player_id === playerId)?.display_name ??
          null,
      );
  }, [state.data]);
  if (!state.data) return <Loading error={state.error} retry={state.reload} />;
  const d = state.data;
  const byEdition = new Map<string, typeof d.matches>();
  for (const m of d.matches) {
    const key = `${m.model_version} · ${m.reference_version} · ${m.profile_id} · ${m.time_basis} · ${m.role}`;
    byEdition.set(key, [...(byEdition.get(key) ?? []), m]);
  }
  // Разные расчёты не смешиваются в одной динамике; подпись — амплуа, номер расчёта только при повторе.
  const seen = new Map<string, number>();
  const title = (rows: typeof d.matches) => {
    const role = roles[rows[0].role as keyof typeof roles] ?? rows[0].role;
    const n = (seen.get(role) ?? 0) + 1;
    seen.set(role, n);
    return byEdition.size > 1 ? `Динамика оценок · ${role}${n > 1 ? ` · расчёт ${n}` : ''}` : 'Динамика оценок';
  };
  const when = (iso: string) =>
    new Date(iso).toLocaleString('ru-RU', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  return (
    <>
      {!d.snapshot_id ? (
        <p>Рейтинг в этом турнире пока не доступен.</p>
      ) : (
        <>
          <RankingTable
            rows={d.summary}
            publicView={publicView}
            tournamentId={tid}
            snapshotId={d.snapshot_id ?? undefined}
          />
          {[...byEdition].map(([key, rows]) => (
            <div key={key}>
              <h3>{title(rows)}</h3>
              <svg
                className="rating-trend"
                viewBox="0 0 600 125"
                role="img"
                aria-label="Матчевые оценки: пропуски не соединяются и не заменяются нулём"
              >
                <path d="M20 10V105H580" fill="none" style={{ stroke: 'var(--border)' }} />
                {rows.map((m, i) => {
                  if (m.score === null) return null;
                  const x = rows.length === 1 ? 300 : 30 + (i * 540) / (rows.length - 1),
                    y = 105 - m.score * 0.9;
                  return (
                    <g key={`${m.match_id}:${m.role}`}>
                      <circle cx={x} cy={y} r="5" style={{ fill: 'var(--accent-line)' }} />
                      <text x={x} y={y - 10} textAnchor="middle" fontSize="12" style={{ fill: 'var(--text)' }}>
                        {m.display_rating?.toFixed(1)}
                      </text>
                    </g>
                  );
                })}
              </svg>
              <div className="rating-cards">
                {rows.map((m) => (
                  <div key={`${m.match_id}:${m.role}`}>
                    <p>
                      {when(m.scheduled_at)} · {m.team_name}
                    </p>
                    <MatchRating value={m} publicView={publicView} />
                  </div>
                ))}
              </div>
            </div>
          ))}
        </>
      )}
    </>
  );
}
