import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { TeamActionStats } from '../../api/domain';
import { PassNetworkStats, PassStats, PlayerPasses } from './PassStats';
import { accuracy, defaultThreshold, formatAccuracy, orientPasses, type PassPoint, passNetwork } from './passes';

const P1 = '11111111-1111-4111-8111-111111111111',
  P2 = '22222222-2222-4222-8222-222222222222',
  P3 = '33333333-3333-4333-8333-333333333333';
const NAMES: Record<string, string> = { [P1]: 'Иванов', [P2]: 'Петров', [P3]: 'Сидоров' };
const name = (id: string | null | undefined) => (id ? (NAMES[id] ?? null) : null);

const pass = (over: Partial<PassPoint>): PassPoint => ({
  id: crypto.randomUUID(),
  side: 'home',
  player_id: P1,
  recipient_id: null,
  start_xy: [10, 5],
  end_xy: [20, 5],
  length_m: 10,
  success: true,
  period: '1',
  start_ms: 65000,
  attacking_direction: 'unknown',
  source: 'cv_auto',
  verified: false,
  ...over,
});

function stats(passes: PassPoint[], over: Partial<TeamActionStats> = {}): TeamActionStats {
  return {
    source: {
      kind: 'cv_auto',
      action_version_id: null,
      run_id: null,
      run_published: true,
      revision: 1,
      status: 'confirmed',
      published: true,
      clock_basis: 'video',
      analysis_scope: 'full_match',
    },
    periods: [{ key: 'all', label: 'Весь матч' }],
    period: 'all',
    untimed: 0,
    coverage: { passes: 'partial' },
    rows: [
      {
        key: 'passes_total',
        label: 'Передачи',
        group: 'passes',
        category: 'passes',
        unit: 'count',
        coverage: 'partial',
        source: 'cv_auto',
        home: { value: 0, numerator: null, denominator: null, unknown: 0 },
        away: { value: 0, numerator: null, denominator: null, unknown: 0 },
      },
    ],
    shots: [],
    passes,
    pass_players: [],
    positions: [],
    positions_orientation: null,
    pitch: { length_m: 40, width_m: 20 },
    ...over,
  };
}

describe('orientPasses', () => {
  it('turns the second half when the attack direction is unknown: teams change ends at half time', () => {
    const { passes, orientation } = orientPasses(
      [pass({ period: '1' }), pass({ period: '2', start_xy: [30, 15], end_xy: [20, 15] })],
      40,
      20,
    );
    expect(orientation).toBe('halves');
    expect(passes.map((p) => [p.start_xy, p.end_xy])).toEqual([
      [
        [10, 5],
        [20, 5],
      ],
      [
        [10, 5],
        [20, 5],
      ],
    ]);
  });

  it('puts the home attack to the right when every pass knows its direction', () => {
    const { passes, orientation } = orientPasses(
      [
        pass({ attacking_direction: 'left', start_xy: [30, 5], end_xy: [20, 5] }),
        pass({ side: 'away', attacking_direction: 'right' }),
        // Направление не задано, но известно у другой передачи той же стороны в том же тайме.
        pass({ start_xy: [35, 10], end_xy: [33, 10] }),
      ],
      40,
      20,
    );
    expect(orientation).toBe('attack');
    expect(passes.map((p) => p.end_xy[0] - p.start_xy[0])).toEqual([10, -10, 2]);
  });

  it('keeps camera coordinates when the recording is not split into halves', () => {
    const { passes, orientation } = orientPasses([pass({ period: null })], 40, 20);
    expect(orientation).toBe('camera');
    expect(passes[0].start_xy).toEqual([10, 5]);
  });
});

it('counts accuracy only over known outcomes and shows a player percent from five passes', () => {
  expect(formatAccuracy(accuracy([{ total: 4, accurate: 2, known: 3 }], 5), true)).toBe('2 / 3');
  expect(formatAccuracy(accuracy([{ total: 8, accurate: 6, known: 8 }], 5), true)).toBe('6 / 8 · ≈75%');
  expect(formatAccuracy(accuracy([{ total: 8, accurate: 6, known: 8 }], 5), false)).toBe('6 / 8 · 75%');
  expect(formatAccuracy(accuracy([{ total: 2, accurate: 0, known: 0 }]), false)).toBe('2 · исход неизвестен');
});

function match() {
  const passes = [
    pass({ recipient_id: P2, start_ms: 65000 }),
    pass({ success: false, start_xy: [12, 8], end_xy: [25, 12], length_m: 13.6 }),
    pass({ player_id: P2, recipient_id: P1, start_xy: [22, 6], end_xy: [15, 4] }),
    pass({ side: 'away', player_id: P3, start_xy: [30, 10], end_xy: [22, 9], success: false }),
    pass({ side: 'away', player_id: null, success: null, start_xy: [28, 12], end_xy: [26, 14] }),
  ];
  return stats(passes, {
    pass_players: [
      { side: 'away', player_id: P3, total: 1, accurate: 0, known: 1, length_m: 8.1, verified: 0 },
      { side: 'away', player_id: null, total: 2, accurate: 0, known: 1, length_m: 2.8, verified: 0 },
      { side: 'home', player_id: P1, total: 6, accurate: 5, known: 6, length_m: 11.8, verified: 0 },
      { side: 'home', player_id: P2, total: 1, accurate: 1, known: 1, length_m: 7.3, verified: 0 },
    ],
  });
}

it('draws passes as arrows, failed ones red, and filters by team, outcome and player', () => {
  render(<PassStats stats={match()} homeName="Север" awayName="Юг" name={name} />);
  const teams = screen.getByLabelText('Точность передач команд');
  expect(within(teams).getByText('≈86%')).toBeInTheDocument(); // 6 из 7 у хозяев
  expect(within(teams).getByText(/точных 0 из 2 · без исхода 1/)).toBeInTheDocument();
  const map = screen.getByRole('img', { name: 'Карта передач: 5' });
  expect(map.querySelectorAll('g.pass')).toHaveLength(5);
  expect(map.querySelectorAll('g.pass.failure')).toHaveLength(2);
  expect(map.querySelectorAll('g.pass.unknown')).toHaveLength(1);
  // Направление и длина: стрелка от точки передачи к приёму, детали по нажатию.
  fireEvent.click(screen.getByRole('button', { name: 'Север: Иванов, 10 м, точная' }));
  expect(screen.getByText('1:05 видео · Иванов → Петров · 10 м · точная')).toBeInTheDocument();
  expect(screen.getByText(/второй тайм развёрнут/)).toBeInTheDocument();
  expect(screen.getByText(/Без точек на поле и не на карте: 5/)).toBeInTheDocument();

  // Замеренная погрешность видео: в подсказке процента, под картой при красных стрелках и в примечании.
  expect(within(teams).getByText('≈86%')).toHaveAttribute('title', expect.stringContaining('расхождение до 17 п.п.'));
  expect(screen.getByText(/Неточные из видео чаще ошибочны: верны 2 из 21/)).toBeInTheDocument();
  expect(
    screen.getByText(/расходится с ручным журналом до 17 п\.п\., а из неточных по видео верны 2 из 21/),
  ).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'Неточные' }));
  expect(screen.getByRole('img', { name: 'Карта передач: 2' }).querySelectorAll('g.pass.failure')).toHaveLength(2);
  fireEvent.click(screen.getByRole('button', { name: 'Все' }));
  fireEvent.click(screen.getByRole('button', { name: 'Юг' }));
  expect(screen.getByRole('img', { name: 'Карта передач: 2' })).toBeInTheDocument();
  expect(screen.getByText('Игрок не определён')).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'Обе команды' }));
  fireEvent.click(screen.getByRole('button', { name: 'Иванов' }));
  expect(screen.getByRole('img', { name: 'Карта передач: 2' })).toBeInTheDocument();
  expect(screen.getByRole('status')).toHaveTextContent('Иванов: передач 6, точных 5 / 6 · ≈83%, средняя длина 11,8 м');
  // У Петрова одна передача: процента нет, только «1 / 1».
  const petrov = screen.getByRole('button', { name: 'Петров' }).closest('tr')!;
  expect(within(petrov).getByTitle('Процент — от 5 передач с исходом')).toHaveTextContent('1 / 1');
});

it('marks only video passes as approximate', () => {
  const manual = match();
  manual.rows = manual.rows.map((r) => ({ ...r, source: 'manual' as const }));
  manual.passes = manual.passes.map((p) => ({ ...p, source: 'manual' as const, verified: true }));
  manual.pass_players = manual.pass_players.map((p) => ({ ...p, verified: p.total }));
  render(<PassStats stats={manual} homeName="Север" awayName="Юг" name={name} />);
  expect(within(screen.getByLabelText('Точность передач команд')).getByText('86%')).toBeInTheDocument();
  expect(screen.queryByText(/расходится с ручным журналом/)).toBeNull();
  expect(screen.queryByText(/Неточные из видео чаще ошибочны/)).toBeNull();
  expect(within(screen.getByLabelText('Точность передач команд')).getByText('86%')).not.toHaveAttribute('title');
});

it('shows the review progress and keeps ≈ until every pass is checked', () => {
  const partial = match();
  partial.rows = partial.rows.map((r) => ({ ...r, source: 'manual' as const }));
  partial.pass_players = partial.pass_players.map((p, i) => ({ ...p, verified: i < 2 ? p.total : 0 }));
  render(<PassStats stats={partial} homeName="Север" awayName="Юг" name={name} />);
  // Проверены передачи гостей (1 + 2), передачи хозяев (6 + 1) — нет.
  expect(screen.getByText('Проверено 3 из 10 передач.')).toBeInTheDocument();
  expect(within(screen.getByLabelText('Точность передач команд')).getByText('≈86%')).toBeInTheDocument();
});

it('marks a confirmed but unpublished review as checked, with accuracy below 100%', () => {
  const reviewed = match();
  reviewed.rows = reviewed.rows.map((r) => ({ ...r, source: 'cv_reviewed' as const }));
  reviewed.passes = reviewed.passes.map((p) => ({ ...p, source: 'cv_reviewed' as const, verified: true }));
  reviewed.pass_players = reviewed.pass_players.map((p) => ({ ...p, verified: p.total }));
  render(<PassStats stats={reviewed} homeName="Север" awayName="Юг" name={name} />);
  const percent = within(screen.getByLabelText('Точность передач команд')).getByText('≈86%');
  expect(percent).toHaveAttribute('title', expect.stringContaining('проверены вручную'));
  expect(
    screen.getByText(/разбор матча ещё не опубликован: найдена не каждая передача, точность не 100%/),
  ).toBeInTheDocument();
  // Замеренная погрешность непроверенных передач к проверенным не относится.
  expect(screen.queryByText(/Неточные из видео чаще ошибочны/)).toBeNull();
  expect(screen.queryByText(/расходится с ручным журналом/)).toBeNull();
});

it("shows one player's passes and accuracy in the player card", () => {
  render(<PlayerPasses stats={match()} playerId={P1} homeName="Север" awayName="Юг" name={name} />);
  expect(screen.getByText('6 · точных 5 / 6 · ≈83% · средняя длина 11,8 м')).toBeInTheDocument();
  expect(screen.getByText(/расхождение до 17 п\.п\./)).toBeInTheDocument();
  expect(screen.getByRole('img', { name: 'Карта передач: 2' })).toBeInTheDocument();
});

describe('passNetwork', () => {
  const players = [
    { side: 'home' as const, player_id: P1, total: 4, accurate: 3, known: 4, length_m: 8, verified: 0 },
    { side: 'home' as const, player_id: P2, total: 2, accurate: 2, known: 2, length_m: 8, verified: 0 },
  ];
  const passes = [
    pass({ attacking_direction: 'right', recipient_id: P2, start_xy: [10, 4], end_xy: [20, 6] }),
    pass({ attacking_direction: 'right', recipient_id: P2, start_xy: [12, 6], end_xy: [22, 8] }),
    pass({ attacking_direction: 'right', success: false, start_xy: [14, 8], end_xy: [30, 8] }),
    pass({ attacking_direction: 'right', player_id: P2, recipient_id: P1, start_xy: [20, 6], end_xy: [10, 4] }),
  ];

  it('places players at the mean of their passes and receptions and counts accurate passes between them', () => {
    const net = passNetwork(stats(passes, { pass_players: players }), 'home');
    expect(net.source).toBe('passes');
    expect(net.attackRight).toBe(true);
    const p1 = net.nodes.find((n) => n.playerId === P1)!;
    // Начала трёх своих передач и приём одной: (10+12+14+10)/4, (4+6+8+4)/4.
    expect([p1.x, p1.y, p1.made, p1.received]).toEqual([11.5, 5.5, 4, 1]);
    expect(net.edges).toEqual([
      { from: P1, to: P2, count: 2 },
      { from: P2, to: P1, count: 1 },
    ]);
    expect(net.maxCount).toBe(2);
    expect(defaultThreshold(net.maxCount)).toBe(2);
    expect(defaultThreshold(12)).toBe(3);
  });

  it('turns the away team to attack right and prefers video positions', () => {
    const away = stats(
      passes.map((p) => ({ ...p, side: 'away' as const, attacking_direction: 'left' as const })),
      {
        pass_players: players.map((p) => ({ ...p, side: 'away' as const })),
        positions: [{ side: 'away', player_id: P1, x: 30, y: 5, observed_s: 600 }],
        positions_orientation: 'attack',
      },
    );
    const net = passNetwork(away, 'away');
    expect(net.source).toBe('video');
    // Гости атакуют влево: разворот на 180° — своя половина у них слева, как у хозяев.
    expect(net.nodes.map((n) => [n.playerId, n.x, n.y])).toEqual([[P1, 10, 15]]);
    expect(net.withoutPosition).toBe(1);
    expect(net.edges).toEqual([]);
  });
});

it('draws the network, filters links by the threshold and explains the selected player', () => {
  const many = [
    ...Array.from({ length: 4 }, () => pass({ attacking_direction: 'right', recipient_id: P2 })),
    pass({ attacking_direction: 'right', player_id: P2, recipient_id: P1, start_xy: [20, 5], end_xy: [10, 5] }),
  ];
  render(
    <PassNetworkStats
      stats={stats(many, {
        pass_players: [
          { side: 'home', player_id: P1, total: 4, accurate: 4, known: 4, length_m: 10, verified: 0 },
          { side: 'home', player_id: P2, total: 1, accurate: 1, known: 1, length_m: 10, verified: 0 },
        ],
      })}
      homeName="Север"
      awayName="Юг"
      name={name}
      number={(id) => (id === P1 ? '7' : null)}
    />,
  );
  // По умолчанию — связки от 3 передач: остаётся одна стрелка Иванов → Петров.
  const graph = screen.getByRole('img', { name: 'Сеть передач: Север, игроков 2, связок 1' });
  expect(graph.querySelectorAll('line.network-link')).toHaveLength(1);
  expect(graph.querySelector('text.network-number')).toHaveTextContent('7');
  fireEvent.change(screen.getByLabelText('Порог связки, передач'), { target: { value: '1' } });
  expect(screen.getByRole('img', { name: 'Сеть передач: Север, игроков 2, связок 2' })).toBeInTheDocument();
  fireEvent.click(within(screen.getByRole('list', { name: 'Игроки сети' })).getByRole('button', { name: /Иванов/ }));
  expect(screen.getByRole('status')).toHaveTextContent(
    'Иванов: передач 4, точных приёмов 1; чаще всего: отдаёт → Петров (4), получает ← Петров (1)',
  );
  expect(screen.getByText(/Север атакует вправо/)).toBeInTheDocument();
});
