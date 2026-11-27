import type { AnalysisAssignment, AnalysisRun } from '../../api/domain';
import { type Candidate, decisionOf } from './candidates';
import { candidateFeature, type MatchModel, MODEL_CONFIDENCE, predict } from './matchModel';
import { clash, cosine, type LookIndex, meanLook } from './similar';

// Уверенная подсказка: лучший доступный игрок обходит второго по цвету формы не меньше чем на 0,05. Замер ВШЭ Ю —
// JWH (513 фрагментов, по одному вне выборки): такая подсказка у 20% фрагментов и верна в 97%; остальные без неё.
export const QUEUE_MARGIN = 0.05;
const KEYS = '1234567890';

type Roster = AnalysisRun['context']['rosters'];
export type QueuePlayer = { id: string; label: string; key: string; own: number[]; mean: ReturnType<typeof meanLook> };

const shirt = (value: string | null | undefined) =>
  value && Number.isFinite(Number(value)) ? Number(value) : Number.POSITIVE_INFINITY;

// Игроки стороны в постоянном порядке — по номеру, без номера по имени в конце; клавиши 1–9 и 0 по этому порядку.
// Не участвовавшие в матче не показываются.
export function queuePlayers(
  index: LookIndex,
  roster: Roster,
  side: string,
  absent: string[],
  assignments: AnalysisAssignment[],
): QueuePlayer[] {
  return roster
    .filter((p) => p.side === side && !absent.includes(p.player_id))
    .sort((a, b) => shirt(a.shirt_number) - shirt(b.shirt_number) || a.display_name.localeCompare(b.display_name, 'ru'))
    .map((p, i) => {
      const own = assignments.filter((x) => x.player_id === p.player_id).map((x) => x.track_id);
      return {
        id: p.player_id,
        label: `${p.shirt_number ? `№${p.shirt_number} ` : ''}${p.display_name}`,
        key: KEYS[i] ?? '',
        own,
        mean: own.length ? meanLook(index, own) : null,
      };
    });
}

// Снимок очереди: неназначенные кандидаты команды по времени начала. Порядок не меняется до нового снимка.
export function queueOrder(candidates: Candidate[], team: 'A' | 'B', assignments: AnalysisAssignment[]): string[] {
  return candidates
    .filter((c) => c.team === team && decisionOf(assignments, c.trackIds).kind === 'none')
    .sort((a, b) => a.span[0] - b.span[0] || a.key.localeCompare(b.key))
    .map((c) => c.key);
}

// Игрок недоступен, если по разметке он на площадке одновременно с кандидатом (правило сервера, больше 1 с).
export const available = (index: LookIndex, player: QueuePlayer, candidate: Candidate) =>
  !player.own.length || !clash(index, player.own, candidate.trackIds);

export function confidentHint(
  index: LookIndex,
  players: QueuePlayer[],
  candidate: Candidate,
  model?: MatchModel | null,
): string | null {
  // Модель матча, если она есть и у кандидата есть признак SigLIP; иначе — отрыв по цвету.
  const x = model ? candidateFeature(index, candidate) : null;
  if (model && x) {
    const free = players.filter((p) => available(index, p, candidate)).map((p) => p.id);
    const r = predict(model, x, free);
    return r && r.p >= MODEL_CONFIDENCE ? r.playerId : null;
  }
  const look = meanLook(index, candidate.trackIds);
  if (!look) return null;
  const scored = players
    .flatMap((p) => (p.mean && available(index, p, candidate) ? [{ id: p.id, score: cosine(p.mean, look) }] : []))
    .sort((a, b) => b.score - a.score);
  if (!scored.length) return null;
  return scored[0].score - (scored[1]?.score ?? 0) >= QUEUE_MARGIN ? scored[0].id : null;
}
