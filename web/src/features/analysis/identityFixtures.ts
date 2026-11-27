import type { AnalysisAssignment, AnalysisRun } from '../../api/domain';

// Признак цвета из пакета: 156 байт в base64. «Красная» и «синяя» форма, косинус между ними ≈ 0,19.
const look = (hot: number) =>
  btoa(String.fromCharCode(...Array.from({ length: 156 }, (_, i) => (i === hot ? 255 : 8))));
export const RED = look(0);
export const BLUE = look(40);
// Признак SigLIP 2 из пакета: 768 байт со знаком, 127 в одной позиции.
const emb = (hot: number) => btoa(String.fromCharCode(...Array.from({ length: 768 }, (_, i) => (i === hot ? 127 : 0))));
const track = (id: number, team: string, from: number, to: number, appearance: string | null) => ({
  track_id: id,
  team,
  role: 'player',
  intervals: [[from, to]],
  thumb: `thumbs/${id}.jpg`,
  has_metrics: true,
  appearance,
});
const teams = { home: { id: 't1', name: 'Север' }, away: { id: 't2', name: 'Юг' } };
const p1 = { player_id: 'p1', side: 'home', display_name: 'Север · игрок 1', shirt_number: '7' };
const p2 = { player_id: 'p2', side: 'home', display_name: 'Север · игрок 2', shirt_number: null };
const p3 = { player_id: 'p3', side: 'home', display_name: 'Север · игрок 3', shirt_number: '3' };
const p9 = { player_id: 'p9', side: 'away', display_name: 'Юг · игрок 1', shirt_number: null };
// A: 1 красный (0:00–0:40) у p1, 4 синий (1:40–2:40) у p2; открыты по времени 3 синий (0:00–0:30, виден вместе с 1),
// 2 красный (0:50–1:30), 6 без признака (2:50–2:55), 5 синий (3:20–3:50). B: 7 (0–150).
const tracks = [
  track(1, 'A', 0, 40, RED),
  track(2, 'A', 50, 90, RED),
  track(3, 'A', 0, 30, BLUE),
  track(4, 'A', 100, 160, BLUE),
  track(5, 'A', 200, 230, BLUE),
  track(6, 'A', 170, 175, null),
  track(7, 'B', 0, 150, RED),
];
export const smallRun = {
  id: 'run',
  job_id: 'job',
  match_id: 'match',
  revision: 0,
  status: 'review',
  context: { teams, rosters: [p1, p2, p9] },
  side_map: { A: 'home', B: 'away' },
  assignments: [],
  tracks,
  groups: [],
} as unknown as AnalysisRun;
// Плюс игрок p3 (№3) без фрагментов и красные 8 (5:00–5:40), 9 и 10, видные одновременно (6:40–7:20, 6:50–7:30).
export const wideRun = {
  ...smallRun,
  context: { teams, rosters: [p1, p2, p3, p9] },
  tracks: [...tracks, track(8, 'A', 300, 340, RED), track(9, 'A', 400, 440, RED), track(10, 'A', 410, 450, RED)].map(
    (t) => ({
      ...t,
      embedding:
        { 1: emb(1), 2: emb(1), 8: emb(2), 9: emb(1), 10: emb(1), 3: emb(3), 4: emb(3), 5: emb(3) }[t.track_id] ?? null,
    }),
  ),
} as unknown as AnalysisRun;
export const sideMap = { A: 'home', B: 'away' } as AnalysisRun['side_map'];
export const base: AnalysisAssignment[] = [
  { track_id: 1, player_id: 'p1' },
  { track_id: 4, player_id: 'p2' },
];
