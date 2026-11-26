import type { PublicAnalysis, PublicProtocol, TeamActionStats } from '../../api/domain';
import { boardGoals } from './board';

// Ход матча по минутам: давление (доля времени полевых игроков в чужой трети, из видеоанализа),
// передачи команд из видео и голы из протокола (без голов в протоколе — с табло трансляции).
// Минута — от начала своего тайма.
export type Side = 'home' | 'away';
export type FlowMinute = {
  half: number;
  minute: number;
  pressure: number | null; // хозяева минус гости, от −1 до 1
  passes: { home: number; away: number };
  goals: Side[];
};
type FlowBin = {
  half: number;
  minute: number;
  start_s: number;
  A: { attack_share: number | null };
  B: { attack_share: number | null };
};
type Period = { key: string; spans?: number[][]; flow?: { bins: FlowBin[] } | null };

export function matchFlow(
  cv: PublicAnalysis | null,
  actions: TeamActionStats | null,
  protocol: PublicProtocol | null,
): FlowMinute[] {
  const period = (cv?.periods as Period[] | undefined)?.find((p) => p.key === cv?.primary_period_key);
  const bins = period?.flow?.bins ?? [];
  if (!cv || !bins.length) return [];
  const sideOf = (team: 'A' | 'B') => cv.side_map[team] as Side;
  const minutes: FlowMinute[] = bins.map((b) => {
    const share = (team: 'A' | 'B') => b[team].attack_share;
    const home = sideOf('A') === 'home' ? share('A') : share('B');
    const away = sideOf('A') === 'home' ? share('B') : share('A');
    return {
      half: b.half,
      minute: b.minute,
      pressure: home == null || away == null ? null : home - away,
      passes: { home: 0, away: 0 },
      goals: [],
    };
  });
  const at = (half: number, minute: number) => minutes.find((m) => m.half === half && m.minute === minute);
  const spans = period?.spans ?? [];
  // Передачи из видео — по времени записи внутри интервалов таймов; ручные — по часам матча и номеру тайма.
  for (const p of actions?.passes ?? []) {
    if (p.start_ms == null) continue;
    if (actions?.source.clock_basis === 'video') {
      const t = p.start_ms / 1000;
      const half = spans.findIndex(([a, b]) => a <= t && t < b);
      if (half >= 0) {
        const m = at(half + 1, Math.floor((t - spans[half][0]) / 60));
        if (m) m.passes[p.side as Side]++;
      }
    } else if (p.period && /^\d+$/.test(p.period)) {
      const m = at(Number(p.period), Math.floor(p.start_ms / 60000));
      if (m) m.passes[p.side as Side]++;
    }
  }
  for (const e of protocol?.protocol.events ?? []) {
    if (e.kind !== 'goal' || e.period == null || e.elapsed_ms == null) continue;
    const m = at(e.period, Math.floor(e.elapsed_ms / 60000));
    if (m) m.goals.push(e.side as Side);
  }
  for (const g of boardGoals(cv, protocol) ?? []) at(g.period, Math.floor(g.elapsedMs / 60000))?.goals.push(g.side);
  return minutes;
}
