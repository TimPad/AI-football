import type { TeamActionStats } from '../../api/domain';
import type { PassArrow } from '../../components/pitch/PassMap';

export type PassPoint = TeamActionStats['passes'][number];
export type PassPlayer = TeamActionStats['pass_players'][number];
export type Side = 'home' | 'away';
// Процент точности игрока — от стольких передач с известным исходом: меньше — шум, а не точность.
export const MIN_PASSES_FOR_PERCENT = 5;

export type Orientation = 'attack' | 'halves' | 'camera';
export const ORIENTATION_NOTE: Record<Orientation, string> = {
  attack: 'Хозяева атакуют вправо, гости — влево.',
  halves: 'Направление атаки не размечено: второй тайм развёрнут, команды атакуют в ту же сторону, что в первом.',
  camera: 'Как на видео: направление атаки не размечено.',
};

const even = (period: string | null) => period !== null && /^\d+$/.test(period) && Number(period) % 2 === 0;

// Обработчик и разметка дают точки как на видео. Если направление атаки известно у каждой передачи
// (её или других передач той же стороны в том же тайме), карта разворачивается: хозяева — вправо.
// Иначе в чётных таймах поле поворачивается на 180°: в перерыве команды меняются воротами, и весь матч
// читается в направлении первого тайма.
export function orientPasses(
  passes: PassPoint[],
  lengthM: number,
  widthM: number,
): { passes: (PassPoint & { flipped: boolean })[]; orientation: Orientation } {
  const votes = new Map<string, { left: number; right: number }>();
  for (const p of passes)
    if (p.attacking_direction !== 'unknown') {
      const key = `${p.side}:${p.period}`;
      const v = votes.get(key) ?? { left: 0, right: 0 };
      v[p.attacking_direction] += 1;
      votes.set(key, v);
    }
  const direction = (p: PassPoint) => {
    if (p.attacking_direction !== 'unknown') return p.attacking_direction;
    const v = votes.get(`${p.side}:${p.period}`);
    return !v || v.left === v.right ? null : v.left > v.right ? 'left' : 'right';
  };
  const known = passes.length > 0 && passes.every((p) => direction(p) !== null);
  const orientation: Orientation = known ? 'attack' : passes.some((p) => p.period !== null) ? 'halves' : 'camera';
  const flip = (p: PassPoint) =>
    orientation === 'attack'
      ? (p.side === 'home') === (direction(p) === 'left')
      : orientation === 'halves' && even(p.period);
  return {
    orientation,
    passes: passes.map((p) => {
      const flipped = flip(p);
      const turn = ([x, y]: number[]) => (flipped ? [lengthM - x, widthM - y] : [x, y]);
      const [x1, y1] = turn(p.start_xy),
        [x2, y2] = turn(p.end_xy);
      return { ...p, start_xy: [x1, y1], end_xy: [x2, y2], flipped };
    }),
  };
}

const clock = (ms: number | null, video: boolean) => {
  if (ms == null) return null;
  if (!video) return `${Math.floor(ms / 60000) + 1}'`;
  const s = Math.floor(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')} видео`;
};

export function toArrows(
  passes: PassPoint[],
  name: (id: string | null | undefined) => string | null,
  videoClock: boolean,
): PassArrow[] {
  return passes.map((p) => ({
    id: p.id,
    side: p.side,
    x1: p.start_xy[0],
    y1: p.start_xy[1],
    x2: p.end_xy[0],
    y2: p.end_xy[1],
    length: p.length_m,
    success: p.success ?? null,
    player: name(p.player_id),
    recipient: name(p.recipient_id),
    time: clock(p.start_ms ?? null, videoClock),
  }));
}

export type PassFilter = { side: Side | 'all'; outcome: 'all' | 'success' | 'failure'; playerId: string };
export const ALL_PASSES: PassFilter = { side: 'all', outcome: 'all', playerId: '' };

export function filterPasses<T extends PassPoint>(passes: T[], f: PassFilter): T[] {
  return passes.filter(
    (p) =>
      (f.side === 'all' || p.side === f.side) &&
      (f.outcome === 'all' || (f.outcome === 'success' ? p.success === true : p.success === false)) &&
      (!f.playerId || p.player_id === f.playerId),
  );
}

export type Accuracy = { total: number; accurate: number; known: number; percent: number | null };
// Точность по известному исходу; без исхода передача считается, но в процент не входит.
export function accuracy(rows: { total: number; accurate: number; known: number }[], minKnown = 1): Accuracy {
  const total = rows.reduce((s, r) => s + r.total, 0),
    accurate = rows.reduce((s, r) => s + r.accurate, 0),
    known = rows.reduce((s, r) => s + r.known, 0);
  return { total, accurate, known, percent: known >= minKnown && known > 0 ? (100 * accurate) / known : null };
}

export const teamAccuracy = (players: PassPlayer[], side: Side) => accuracy(players.filter((p) => p.side === side));

export function formatAccuracy(a: Accuracy, approx: boolean) {
  if (!a.known) return a.total ? `${a.total} · исход неизвестен` : '—';
  const percent = a.percent == null ? '' : ` · ${approx ? '≈' : ''}${Math.round(a.percent)}%`;
  return `${a.accurate} / ${a.known}${percent}`;
}
