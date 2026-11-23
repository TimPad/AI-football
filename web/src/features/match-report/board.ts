import type { PublicAnalysis, PublicProtocol } from '../../api/domain';

// Голы с табло трансляции из видеоанализа. Протокол — официальный источник: табло показывается, только
// пока в протоколе нет ни одного гола, а итог плашек совпал с его счётом (так же определяется, какая плашка
// — хозяева). Авторов на табло нет; минуту табло меняют с задержкой после гола.
export type Side = 'home' | 'away';
export type BoardGoal = {
  key: string;
  side: Side;
  period: number;
  elapsedMs: number;
  score: { home: number; away: number };
};
export const BOARD_NOTE = 'по табло трансляции';
export const BOARD_HINT =
  'Голы и минуты — по табло трансляции: его обновляют с задержкой, минута может быть на одну позже. Авторов голов в протоколе нет.';

export function boardGoals(cv: PublicAnalysis | null, protocol: PublicProtocol | null): BoardGoal[] | null {
  const board = cv?.scoreboard;
  if (!board || !protocol || !board.goals.length) return null;
  if (protocol.protocol.events.some((e) => e.kind === 'goal')) return null;
  const { home, away } = protocol.projection.effective_score;
  const left = board.final.left ?? 0,
    right = board.final.right ?? 0;
  const leftSide: Side | null =
    home === left && away === right ? 'home' : home === right && away === left ? 'away' : null;
  // При ничьей счёт плашки не различает: левая — хозяева, как принято в трансляциях.
  if (!leftSide) return null;
  const score = { home: 0, away: 0 };
  return board.goals.map((g, i) => {
    const side: Side = g.side === 'left' ? leftSide : leftSide === 'home' ? 'away' : 'home';
    score[side]++;
    return {
      key: `board:${i}`,
      side,
      period: g.period,
      elapsedMs: Math.round(g.elapsed_s * 1000),
      score: { ...score },
    };
  });
}

// Минута матча как у протокола: смещение тайма по регламенту + прошедшее время, «23'».
export function boardMinute(protocol: PublicProtocol, g: BoardGoal): string {
  const offset = protocol.regulation.rules.periods_s.slice(0, g.period - 1).reduce((a, b) => a + b, 0);
  return `${Math.floor(offset / 60) + Math.floor(g.elapsedMs / 60000) + 1}'`;
}

// Шапка матча: у каждой команды строка минут голов по табло, без авторов.
export function boardScorers(protocol: PublicProtocol, goals: BoardGoal[]) {
  const line = (side: Side) => {
    const minutes = goals.filter((g) => g.side === side).map((g) => boardMinute(protocol, g));
    return minutes.length ? [{ key: `board:${side}`, name: '', minute: minutes.join(' '), note: null }] : [];
  };
  return { home: line('home'), away: line('away') };
}
