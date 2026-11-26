import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { PublicAnalysis, PublicProtocol } from '../../api/domain';
import { boardGoals, boardScorers } from './board';
import { MatchTimeline } from './MatchTimeline';

// Табло: слева 2 гола, справа 1; второй гол левой плашки — во втором тайме.
const cv = (final = { left: 2, right: 1 }) =>
  ({
    scoreboard: {
      overlay: 'Мяч ТВ',
      final,
      goals: [
        { side: 'left', period: 1, elapsed_s: 114 },
        { side: 'right', period: 1, elapsed_s: 673 },
        { side: 'left', period: 2, elapsed_s: 167.5 },
      ],
    },
  }) as unknown as PublicAnalysis;
const protocol = (home: number, away: number, events: unknown[] = []) =>
  ({
    number: 1,
    lineup: [],
    regulation: { rules: { periods_s: [1200, 1200] } },
    projection: { effective_score: { home, away } },
    protocol: { events },
  }) as unknown as PublicProtocol;

describe('goals from the broadcast scoreboard', () => {
  it('maps plates to teams by the protocol score and counts the running score', () => {
    const goals = boardGoals(cv(), protocol(2, 1))!;
    expect(goals.map((g) => [g.side, g.period, g.elapsedMs, `${g.score.home}:${g.score.away}`])).toEqual([
      ['home', 1, 114_000, '1:0'],
      ['away', 1, 673_000, '1:1'],
      ['home', 2, 167_500, '2:1'],
    ]);
    // Слева на трансляции гости: протокол 1:2.
    expect(boardGoals(cv(), protocol(1, 2))!.map((g) => g.side)).toEqual(['away', 'home', 'away']);
  });

  it('is hidden when the protocol has goals, a different score or is not published', () => {
    expect(boardGoals(cv(), protocol(3, 1))).toBeNull();
    expect(boardGoals(cv(), protocol(2, 1, [{ id: 'g', kind: 'goal', side: 'home', period: 1 }]))).toBeNull();
    expect(boardGoals(cv(), null)).toBeNull();
    expect(boardGoals(null, protocol(2, 1))).toBeNull();
  });

  it('lists minutes under the teams in the header', () => {
    const p = protocol(2, 1);
    const scorers = boardScorers(p, boardGoals(cv(), p)!);
    expect(scorers.home.map((s) => s.minute)).toEqual(["2' 23'"]);
    expect(scorers.away.map((s) => s.minute)).toEqual(["12'"]);
  });

  it('shows board goals with the score in the timeline and the half-time score', () => {
    const p = protocol(2, 1, [{ id: 'c', kind: 'card', card: 'yellow', side: 'away', period: 2, elapsed_ms: 60_000 }]);
    render(<MatchTimeline value={p} board={boardGoals(cv(), p)} />);
    const list = screen.getByRole('list', { name: 'Лента матча' });
    const rows = within(list).getAllByRole('listitem');
    expect(rows.map((r) => r.textContent)).toEqual([
      "Гол · 1 : 0по табло трансляции2'",
      "12'Гол · 1 : 1по табло трансляции",
      'Конец 1-го тайма · 1 : 1',
      "22'Жёлтая карточка",
      "Гол · 2 : 1по табло трансляции23'",
    ]);
    expect(screen.getByText(/минута может быть на одну позже/)).toBeInTheDocument();
  });
});
