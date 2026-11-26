import { describe, expect, it } from 'vitest';
import type { TeamActionStats } from '../../api/domain';
import { clock, hasShotData, heatmapCenter, playerShots, videoTiles } from './playerCard';

const metrics = {
  distance_m: 3004.42,
  observed_s: 1498.5,
  m_per_min: 120.3,
  hsr_m: 778.61,
  sprints: 4,
  vmax_ms: 9.78,
  heatmap_s: null,
  metric_notes: {},
  missing_track_ids: [],
};

describe('player card figures', () => {
  it('formats video physics and keeps unknown values as a dash', () => {
    const tiles = videoTiles(metrics)!;
    expect(tiles.map((t) => [t.label, t.value])).toEqual([
      ['В кадре', '24:59'],
      ['Дистанция', '3 004 м'],
      ['Темп', '120 м/мин'],
      ['Быстрый бег', '779 м'],
      ['Спринты', '4'],
      ['Макс. скорость', '9,8 м/с'],
    ]);
    expect(tiles[0].hint).toMatch(/не минуты на площадке/);
    expect(videoTiles({ ...metrics, vmax_ms: null, m_per_min: null })!.map((t) => t.value)).toContain('—');
    expect(videoTiles(null)).toBeNull();
    expect(clock(59.6)).toBe('1:00');
  });

  it('puts the average position at the centre of the heatmap', () => {
    // 1 с в клетке (0, 0) и 3 с в клетке (2, 1), клетки по 1 м: центры клеток (0,5; 0,5) и (2,5; 1,5) → (2; 1,25).
    expect(
      heatmapCenter([
        [1, 0],
        [0, 0],
        [0, 3],
      ]),
    ).toEqual([2, 1.25]);
    expect(heatmapCenter([[0, 0]])).toBeNull();
    expect(heatmapCenter(null)).toBeNull();
  });

  it("takes the player's shots and tells missing shot data from zero shots", () => {
    const stats = {
      rows: [{ category: 'shots' }],
      shots: [
        {
          id: '1',
          side: 'home',
          player_id: 'p1',
          x: 30,
          y: 10,
          goal: true,
          on_target: true,
          blocked: false,
          outcome: 'goal',
          start_ms: 1,
        },
        {
          id: '2',
          side: 'home',
          player_id: 'p2',
          x: 25,
          y: 8,
          goal: false,
          on_target: false,
          blocked: false,
          outcome: 'off_target',
          start_ms: 2,
        },
      ],
    } as unknown as TeamActionStats;
    expect(playerShots(stats, 'p1', 'Иванов').map((s) => [s.id, s.player])).toEqual([['1', 'Иванов']]);
    expect(hasShotData(stats)).toBe(true);
    expect(hasShotData({ ...stats, rows: [] } as unknown as TeamActionStats)).toBe(false);
    expect(hasShotData(null)).toBe(false);
  });
});
