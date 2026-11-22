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

// Сеть передач команды: узел — игрок в средней позиции, связь — точные передачи от одного к другому.
export type NetworkNode = {
  playerId: string;
  x: number;
  y: number;
  made: number; // все передачи игрока за период, и без точек
  received: number; // точные передачи ему (по передачам с точками)
};
export type NetworkEdge = { from: string; to: string; count: number };
export type Network = {
  nodes: NetworkNode[];
  edges: NetworkEdge[];
  maxCount: number;
  source: 'video' | 'passes';
  orientation: Orientation;
  attackRight: boolean; // команда атакует вправо — направление известно
  withoutPosition: number; // игроки с передачами, но без позиции на видео
};

// Позиции — средние по видео, если они есть у команды; иначе — средняя точка касаний: начал своих передач
// и приёмов точных передач. Команда показывается атакующей вправо, когда направление известно.
export function passNetwork(stats: TeamActionStats, side: Side): Network {
  const pitch = stats.pitch ?? { length_m: 40, width_m: 20 };
  const L = pitch.length_m,
    W = pitch.width_m;
  const oriented = orientPasses(stats.passes, L, W);
  const own = oriented.passes.filter((p) => p.side === side);
  const counts = new Map<string, number>();
  const received = new Map<string, number>();
  for (const p of own)
    if (p.success === true && p.player_id && p.recipient_id && p.player_id !== p.recipient_id) {
      const key = `${p.player_id}>${p.recipient_id}`;
      counts.set(key, (counts.get(key) ?? 0) + 1);
      received.set(p.recipient_id, (received.get(p.recipient_id) ?? 0) + 1);
    }
  const made = new Map(
    stats.pass_players.filter((p) => p.side === side && p.player_id).map((p) => [p.player_id!, p.total]),
  );
  const video = stats.positions.filter((p) => p.side === side);
  const source: Network['source'] = video.length ? 'video' : 'passes';
  const orientation: Orientation = video.length ? (stats.positions_orientation ?? 'camera') : oriented.orientation;
  // Направление известно: хозяева атакуют вправо, гостей разворачиваем, чтобы и они атаковали вправо.
  const mirror = orientation === 'attack' && side === 'away';
  const place = (x: number, y: number) => (mirror ? [L - x, W - y] : [x, y]);
  const positions = new Map<string, [number, number]>();
  if (video.length) for (const p of video) positions.set(p.player_id, [p.x, p.y]);
  else {
    const touches = new Map<string, number[][]>();
    const add = (id: string, xy: number[]) => touches.set(id, [...(touches.get(id) ?? []), xy]);
    for (const p of own) {
      if (p.player_id) add(p.player_id, p.start_xy);
      if (p.success === true && p.recipient_id) add(p.recipient_id, p.end_xy);
    }
    for (const [id, xy] of touches)
      positions.set(id, [xy.reduce((s, v) => s + v[0], 0) / xy.length, xy.reduce((s, v) => s + v[1], 0) / xy.length]);
  }
  const players = new Set([...made.keys(), ...received.keys()]);
  const nodes: NetworkNode[] = [];
  for (const id of players) {
    const at = positions.get(id);
    if (!at) continue;
    const [x, y] = place(at[0], at[1]);
    nodes.push({ playerId: id, x, y, made: made.get(id) ?? 0, received: received.get(id) ?? 0 });
  }
  const placed = new Set(nodes.map((n) => n.playerId));
  const edges = [...counts]
    .map(([key, count]) => {
      const [from, to] = key.split('>');
      return { from, to, count };
    })
    .filter((e) => placed.has(e.from) && placed.has(e.to));
  return {
    nodes,
    edges,
    maxCount: edges.reduce((m, e) => Math.max(m, e.count), 0),
    source,
    orientation,
    attackRight: orientation === 'attack',
    withoutPosition: [...players].filter((id) => !placed.has(id)).length,
  };
}

// Порог связи по умолчанию: у референса «от 5 передач» за 69 минут 11 на 11; в футзале передач меньше,
// а по видео находится около двух третей — от 3, если такие связки есть, иначе самая частая.
export const defaultThreshold = (maxCount: number) => Math.max(1, Math.min(3, maxCount));
