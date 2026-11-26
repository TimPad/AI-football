import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import type { AnalysisAssignment } from '../../api/domain';
import { IdentityQueue } from './IdentityQueue';
import { IdentityReview } from './IdentityReview';
import { base, smallRun as run, sideMap } from './identityFixtures';

function Harness({ onChange }: { onChange: (next: AnalysisAssignment[]) => void }) {
  const [assignments, setAssignments] = useState(base);
  return (
    <IdentityQueue
      run={run}
      assignments={assignments}
      sideMap={sideMap}
      absent={[]}
      disabled={false}
      onChange={(next) => {
        onChange(next);
        setAssignments(next);
      }}
    />
  );
}
const show = (onChange = vi.fn()) => {
  render(<Harness onChange={onChange} />);
  return onChange;
};
const last = (fn: ReturnType<typeof vi.fn>) => fn.mock.calls[fn.mock.calls.length - 1][0] as AnalysisAssignment[];
const key = (k: string) => fireEvent.keyDown(window, { key: k });

describe('identity queue', () => {
  it('goes through open fragments by time and keeps the order after a decision', () => {
    const onChange = show();
    expect(screen.getByText(/0:00–0:30 · 30 с/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '1 · №7 Север · игрок 1' })).toBeDisabled();
    key('2');
    expect(last(onChange)).toContainEqual({ track_id: 3, player_id: 'p2' });
    expect(screen.getByText(/0:50–1:30 · 40 с/)).toBeInTheDocument();
    expect(screen.getByRole('status', { name: 'Прогресс очереди' })).toHaveTextContent('фрагмент 2 из 4 · осталось 3');
  });

  it('passes skipped fragments again at the end', () => {
    const onChange = show();
    key(' ');
    key('x');
    expect(last(onChange)).toContainEqual({ track_id: 2, excluded_reason: 'Не игрок матча' });
    key('x');
    key('2');
    expect(screen.getByText(/пропущено: 1/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Пройти пропущенные' }));
    expect(screen.getByText(/0:00–0:30 · 30 с/)).toBeInTheDocument();
  });

  it('undoes the last decision', () => {
    const onChange = show();
    key('2');
    key('Backspace');
    expect(last(onChange)).toEqual(base);
    expect(screen.getByText(/0:00–0:30 · 30 с/)).toBeInTheDocument();
  });

  it('highlights only a confident hint and never reorders the players', () => {
    show();
    expect(screen.getByRole('button', { name: '2 · Север · игрок 2' })).toHaveClass('hinted');
    key(' ');
    expect(screen.getByRole('button', { name: '1 · №7 Север · игрок 1' })).toHaveClass('hinted');
    key(' ');
    expect(screen.getByText('подсказки нет')).toBeInTheDocument();
    const names = screen.getAllByRole('button', { name: /Север · игрок/ }).map((b) => b.textContent);
    expect(names).toEqual(['1 · №7 Север · игрок 1', '2 · Север · игрок 2']);
  });
});

describe('review tab', () => {
  it('opens the queue by default and saves decisions by itself', async () => {
    vi.useFakeTimers();
    localStorage.clear();
    const save = vi.fn().mockResolvedValue(undefined);
    render(
      <MemoryRouter>
        <IdentityReview run={{ ...run, assignments: base }} actorId="admin" editable onSave={save} />
      </MemoryRouter>,
    );
    expect(screen.getByRole('button', { name: 'Очередь' })).toHaveAttribute('aria-pressed', 'true');
    fireEvent.keyDown(window, { key: '2' });
    expect(save).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(2100);
    expect(save).toHaveBeenCalledTimes(1);
    expect(save.mock.calls[0][0].assignments).toContainEqual({ track_id: 3, player_id: 'p2' });
    expect(save.mock.calls[0][0].absent_players).toEqual([]);
    vi.useRealTimers();
  });

  it('keeps who did not take part in the draft', () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    localStorage.clear();
    render(
      <MemoryRouter>
        <IdentityReview run={{ ...run, assignments: base }} actorId="admin" editable onSave={vi.fn()} />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Игроки' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Участвовал в матче: Север · игрок 1' }));
    fireEvent.click(screen.getByRole('button', { name: 'Очередь' }));
    expect(screen.queryByRole('button', { name: /№7 Север · игрок 1/ })).toBeNull();
    vi.restoreAllMocks();
  });
});
