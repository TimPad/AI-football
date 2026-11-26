import type { AnalysisRun } from '../../api/domain';
import type { Candidate } from './candidates';
import type { LookIndex } from './similar';

// Кадр кандидата — миниатюра его самого длинного фрагмента, у которого кадр есть.
export function CandidateThumb({
  run,
  index,
  candidate,
  className,
}: {
  run: AnalysisRun;
  index: LookIndex;
  candidate: Candidate;
  className: string;
}) {
  const seconds = (id: number) => index.tracks.get(id)?.intervals.reduce((s, [a, b]) => s + b - a, 0) ?? 0;
  const id = candidate.trackIds.filter((t) => index.tracks.get(t)?.thumb).sort((a, b) => seconds(b) - seconds(a))[0];
  return id != null ? (
    <img
      className={`track-thumb ${className}`}
      src={`/api/v1/matches/${run.match_id}/analysis/runs/${run.id}/thumbs/${id}`}
      alt={`Фрагмент ${id}`}
    />
  ) : (
    <span className={`thumb-missing ${className}`}>Кадр недоступен</span>
  );
}
