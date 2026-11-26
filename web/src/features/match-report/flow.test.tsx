import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { PublicAnalysis, PublicProtocol, TeamActionStats } from '../../api/domain';
import { matchFlow } from './flow';
import { MatchFlow } from './MatchFlow';

const bin = (half: number, minute: number, start: number, a: number | null, b: number | null) => ({
  half,
  minute,
  start_s: start,
  A: { observed_s: 50, attack_share: a },
  B: { observed_s: 50, attack_share: b },
});
// Тайм 1 — с 100 с записи, тайм 2 — с 1300 с; у видео A — гости.
const cv = {
  primary_period_key: 'all',
  side_map: { A: 'away', B: 'home' },
  periods: [
    {
      key: 'all',
      spans: [
        [100, 220],
        [1300, 1360],
      ],
      flow: { bin_s: 60, bins: [bin(1, 0, 100, 0.1, 0.5), bin(1, 1, 160, 0.4, 0.2), bin(2, 0, 1300, null, 0.3)] },
    },
  ],
} as unknown as PublicAnalysis;
const actions = {
  source: { clock_basis: 'video' },
  passes: [
    { side: 'home', start_ms: 130_000, period: '1' },
    { side: 'away', start_ms: 170_000, period: '1' },
    { side: 'home', start_ms: 1_310_000, period: '2' },
    { side: 'home', start_ms: 500_000, period: null }, // в перерыве — не на графике
  ],
} as unknown as TeamActionStats;
const protocol = {
  protocol: { events: [{ kind: 'goal', side: 'home', period: 1, elapsed_ms: 75_000 }] },
} as unknown as PublicProtocol;

describe('match flow', () => {
  it('turns video teams into home and away and places passes and goals by minute', () => {
    const flow = matchFlow(cv, actions, protocol);
    expect(flow.map((m) => [m.half, m.minute, m.pressure])).toEqual([
      [1, 0, 0.4], // хозяева (B) 0,5 − гости (A) 0,1
      [1, 1, -0.2],
      [2, 0, null],
    ]);
    expect(flow.map((m) => [m.passes.home, m.passes.away])).toEqual([
      [1, 0],
      [0, 1],
      [1, 0],
    ]);
    expect(flow.map((m) => m.goals)).toEqual([[], ['home'], []]);
    expect(matchFlow(null, actions, protocol)).toEqual([]);
  });

  it('draws pressure bars by default and switches to passes', () => {
    render(<MatchFlow minutes={matchFlow(cv, actions, protocol)} homeName="Север" awayName="Юг" />);
    const chart = screen.getByRole('img', { name: 'Ход матча по минутам: давление, минут 3' });
    expect(chart.querySelectorAll('rect.flow-bar.home')).toHaveLength(1);
    expect(chart.querySelectorAll('rect.flow-bar.away')).toHaveLength(1);
    expect(chart.querySelectorAll('line.flow-break')).toHaveLength(1);
    expect(chart.querySelectorAll('circle.flow-goal.home')).toHaveLength(1);
    expect(screen.getByText(/Точки — голы из протокола/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Передачи' }));
    const passes = screen.getByRole('img', { name: 'Ход матча по минутам: передачи, минут 3' });
    expect(passes.querySelectorAll('rect.flow-bar.home')).toHaveLength(2);
    expect(passes.querySelectorAll('rect.flow-bar.away')).toHaveLength(1);
  });
});
