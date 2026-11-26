import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import type { AnalysisAssignment } from '../../api/domain';
import { IdentityGrid } from './IdentityGrid';
import { base, smallRun as run, sideMap } from './identityFixtures';

function Harness({ onChange }: { onChange: (next: AnalysisAssignment[]) => void }) {
  const [assignments, setAssignments] = useState(base);
  return (
    <IdentityGrid
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
const tile = (span: string) => screen.getByRole('button', { name: `Фрагмент ${span}` });

describe('identity grid', () => {
  it('assigns with the brush on click and clears on a second click', () => {
    const onChange = show();
    fireEvent.click(screen.getByRole('button', { name: '2 · Север · игрок 2' }));
    fireEvent.click(tile('3:20–3:50'));
    expect(last(onChange)).toContainEqual({ track_id: 5, player_id: 'p2' });
    expect(tile('3:20–3:50')).toHaveTextContent('Север · игрок 2');
    fireEvent.click(tile('3:20–3:50'));
    expect(last(onChange).some((a) => a.track_id === 5)).toBe(false);
  });

  it('selects with Ctrl and gives the class key to every selected tile', () => {
    const onChange = show();
    fireEvent.click(tile('0:00–0:30'), { ctrlKey: true });
    fireEvent.click(tile('3:20–3:50'), { ctrlKey: true });
    expect(screen.getByRole('status', { name: 'Выделение' })).toHaveTextContent('выделено: 2');
    fireEvent.keyDown(window, { key: '2' });
    expect(last(onChange)).toEqual(
      expect.arrayContaining([
        { track_id: 3, player_id: 'p2' },
        { track_id: 5, player_id: 'p2' },
      ]),
    );
    expect(screen.getByRole('status', { name: 'Выделение' })).toHaveTextContent('выделено: 0');
  });

  it('selects a range with Shift and excludes it', () => {
    const onChange = show();
    fireEvent.click(tile('0:00–0:30'), { ctrlKey: true });
    fireEvent.click(tile('2:50–2:55'), { shiftKey: true });
    fireEvent.click(screen.getByRole('button', { name: 'X · Не игрок матча' }));
    const excluded = last(onChange)
      .filter((a) => a.excluded_reason === 'Не игрок матча')
      .map((a) => a.track_id);
    expect(excluded.sort()).toEqual([2, 3, 6]);
  });

  it('refuses a fragment seen together with the player and counts it', () => {
    const onChange = show();
    fireEvent.click(screen.getByRole('button', { name: '1 · №7 Север · игрок 1' }));
    fireEvent.click(tile('0:00–0:30'));
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByRole('status', { name: 'Не назначено' })).toHaveTextContent(
      'Не назначено из-за одновременности: 1',
    );
  });

  it('keeps tiles in place until refresh', () => {
    show();
    fireEvent.click(screen.getByRole('button', { name: '2 · Север · игрок 2' }));
    fireEvent.click(tile('3:20–3:50'));
    expect(tile('3:20–3:50')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Обновить' }));
    expect(screen.queryByRole('button', { name: 'Фрагмент 3:20–3:50' })).toBeNull();
  });

  it('drops the brush when the team changes', () => {
    const onChange = vi.fn();
    render(
      <IdentityGrid run={run} assignments={[]} sideMap={sideMap} absent={[]} disabled={false} onChange={onChange} />,
    );
    fireEvent.click(screen.getByRole('button', { name: '2 · Север · игрок 2' }));
    fireEvent.click(screen.getByRole('button', { name: 'Юг' }));
    fireEvent.click(tile('0:00–2:30'));
    expect(onChange).not.toHaveBeenCalled();
  });
});
