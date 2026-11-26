import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { AnalysisAssignment, AnalysisRun } from '../../api/domain';
import { IdentityReview } from './IdentityReview';
import { SuggestionPicker } from './SuggestionPicker';

const look = (hot: number) =>
  btoa(String.fromCharCode(...Array.from({ length: 156 }, (_, i) => (i === hot ? 255 : 8))));
const RED = look(0);
const BLUE = look(40);
const track = (id: number, team: string, from: number, to: number, appearance: string | null) => ({
  track_id: id,
  team,
  role: 'player',
  intervals: [[from, to]],
  thumb: `thumbs/${id}.jpg`,
  has_metrics: true,
  appearance,
});
const base: AnalysisAssignment[] = [
  { track_id: 1, player_id: 'p1' },
  { track_id: 4, player_id: 'p2' },
];
const run = {
  job_id: 'job',
  id: 'run',
  match_id: 'match',
  revision: 0,
  status: 'review',
  context: {
    teams: { home: { id: 't1', name: 'Север' }, away: { id: 't2', name: 'Юг' } },
    rosters: [
      { player_id: 'p1', side: 'home', display_name: 'Север · игрок 1', shirt_number: '7' },
      { player_id: 'p2', side: 'home', display_name: 'Север · игрок 2', shirt_number: null },
      { player_id: 'p9', side: 'away', display_name: 'Юг · игрок 1', shirt_number: null },
    ],
  },
  side_map: { A: 'home', B: 'away' },
  assignments: base,
  tracks: [
    track(1, 'A', 0, 40, RED),
    track(2, 'A', 50, 90, RED),
    track(3, 'A', 0, 30, BLUE),
    track(4, 'A', 100, 160, BLUE),
    track(5, 'A', 200, 230, BLUE),
    track(6, 'A', 170, 175, null),
    track(7, 'B', 0, 150, RED),
  ],
  groups: [],
} as unknown as AnalysisRun;
const sideMap = { A: 'home', B: 'away' } as AnalysisRun['side_map'];
const show = (assignments = base, onChange = vi.fn(), onOpenSimilar = vi.fn()) =>
  render(
    <SuggestionPicker
      run={run}
      assignments={assignments}
      sideMap={sideMap}
      disabled={false}
      onChange={onChange}
      onOpenSimilar={onOpenSimilar}
    />,
  );
const group = (name: string) => screen.getByRole('region', { name: `Подсказки игроку ${name}` });
const card = (g: HTMLElement, span: string) => within(g).getByRole('listitem', { name: `Фрагмент ${span}` });
beforeEach(() => localStorage.clear());

describe('suggestion picker', () => {
  it('groups hints by player, ticks confident ones and assigns the ticked ones', () => {
    const onChange = vi.fn();
    show(base, onChange);
    const p2 = group('Север · игрок 2');
    expect(within(p2).getByRole('heading')).toHaveTextContent('подсказок: 2');
    const early = card(p2, '0:00–0:30');
    expect(early).toHaveTextContent('уверенно');
    expect(within(early).getByRole('checkbox', { name: 'Назначить' })).toBeChecked();
    fireEvent.click(within(card(p2, '3:20–3:50')).getByRole('checkbox', { name: 'Назначить' }));
    fireEvent.click(within(p2).getByRole('button', { name: 'Назначить отмеченных (1)' }));
    const next = onChange.mock.calls[0][0] as AnalysisAssignment[];
    expect(next).toContainEqual({ track_id: 3, player_id: 'p2' });
    expect(next.some((a) => a.track_id === 5)).toBe(false);
    expect(screen.getByRole('status', { name: 'Без подсказки' })).toHaveTextContent(
      'Без подсказки: 1 — нет признака цвета: 1',
    );
  });

  it('gives a rejected hint to the next player', () => {
    show();
    fireEvent.click(within(card(group('7 · Север · игрок 1'), '0:50–1:30')).getByRole('button', { name: 'Не он' }));
    expect(screen.queryByRole('region', { name: 'Подсказки игроку 7 · Север · игрок 1' })).toBeNull();
    expect(card(group('Север · игрок 2'), '0:50–1:30')).toBeInTheDocument();
  });

  it('ticks all, clears all and passes the unticked ones to the next player', () => {
    show();
    const p2 = group('Север · игрок 2');
    fireEvent.click(within(p2).getByRole('button', { name: 'Снять все' }));
    expect(within(p2).getByRole('button', { name: 'Назначить отмеченных (0)' })).toBeDisabled();
    fireEvent.click(within(p2).getByRole('button', { name: 'Отметить все' }));
    expect(within(p2).getByRole('button', { name: 'Назначить отмеченных (2)' })).toBeEnabled();
    fireEvent.click(within(card(p2, '3:20–3:50')).getByRole('checkbox', { name: 'Назначить' }));
    fireEvent.click(within(p2).getByRole('button', { name: 'Не он — неотмеченным (1)' }));
    expect(card(group('7 · Север · игрок 1'), '3:20–3:50')).toBeInTheDocument();
    expect(within(group('Север · игрок 2')).getByRole('button', { name: 'Назначить отмеченных (1)' })).toBeEnabled();
  });

  it('asks to start in the similar picker when no player has fragments', () => {
    const onOpenSimilar = vi.fn();
    show([], vi.fn(), onOpenSimilar);
    expect(screen.getByText(/Сначала назначьте каждому игроку хотя бы один фрагмент/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Открыть «Подбор»' }));
    expect(onOpenSimilar).toHaveBeenCalled();
  });

  it('is a mode of the review tab with the number of hints', () => {
    render(
      <MemoryRouter>
        <IdentityReview run={run} actorId="admin" editable onSave={vi.fn()} />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Подсказки · 3' }));
    const p2 = group('Север · игрок 2');
    fireEvent.click(within(p2).getByRole('button', { name: 'Назначить отмеченных (2)' }));
    expect(screen.getByText(/назначений в черновике: 4/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Подсказки · 1' })).toBeInTheDocument();
  });
});
