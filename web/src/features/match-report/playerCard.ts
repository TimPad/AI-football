import type { PublicAnalysis, TeamActionStats } from '../../api/domain';
import type { Shot } from '../../components/pitch/ShotMap';

// Цифры карточки игрока в матче: физика по видео, удары из размеченных действий, центр тепловой карты.
type Metrics = PublicAnalysis['players'][number]['metrics'];
export type Tile = { label: string; value: string; hint?: string };

const whole = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 });
const tenth = new Intl.NumberFormat('ru-RU', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const DASH = '—';

export function clock(seconds: number): string {
  const s = Math.round(seconds);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

const value = (x: number | null | undefined, format: Intl.NumberFormat, unit: string) =>
  x == null ? DASH : `${format.format(x)}${unit}`;

// HSR — дистанция быстрее 4 м/с (analytics.report_data.HSR_MS).
export function videoTiles(m: Metrics | null | undefined): Tile[] | null {
  if (!m) return null;
  return [
    {
      label: 'В кадре',
      value: m.observed_s == null ? DASH : clock(m.observed_s),
      hint: 'Сколько видео наблюдало игрока. Камера видит не всё поле — это не минуты на площадке.',
    },
    { label: 'Дистанция', value: value(m.distance_m, whole, ' м') },
    { label: 'Темп', value: value(m.m_per_min, whole, ' м/мин') },
    { label: 'Быстрый бег', value: value(m.hsr_m, whole, ' м'), hint: 'Дистанция на скорости выше 4 м/с' },
    { label: 'Спринты', value: m.sprints == null ? DASH : String(m.sprints) },
    { label: 'Макс. скорость', value: value(m.vmax_ms, tenth, ' м/с') },
  ];
}

export function playerShots(stats: TeamActionStats | null, playerId: string, name: string | null): Shot[] {
  return (stats?.shots ?? []).filter((s) => s.player_id === playerId).map((s) => ({ ...s, player: name }));
}

// Удары размечаются в действиях матча: без категории ударов в сводке — данных нет (а не «0 ударов»).
export function hasShotData(stats: TeamActionStats | null): boolean {
  return !!stats?.rows.some((r) => r.category === 'shots');
}

// Средняя позиция игрока — центр его тепловой карты (секунды по клеткам), в метрах тех же координат площадки.
export function heatmapCenter(cells: number[][] | null | undefined, cellM = 1): [number, number] | null {
  let total = 0,
    x = 0,
    y = 0;
  const grid = cells ?? [];
  for (let i = 0; i < grid.length; i++)
    for (let j = 0; j < grid[i].length; j++) {
      const s = grid[i][j];
      if (s > 0) {
        total += s;
        x += (i + 0.5) * cellM * s;
        y += (j + 0.5) * cellM * s;
      }
    }
  return total > 0 ? [x / total, y / total] : null;
}
