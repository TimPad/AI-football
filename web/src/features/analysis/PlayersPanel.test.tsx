import { fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { base, smallRun as run } from './identityFixtures';
import { PlayersPanel } from './PlayersPanel';

const show = (absent: string[] = [], onChange = vi.fn()) => {
  render(<PlayersPanel run={run} assignments={base} absent={absent} disabled={false} onChange={onChange} />);
  return onChange;
};
afterEach(() => vi.restoreAllMocks());

describe('players panel', () => {
  it('returns the fragments of a player who did not take part to the queue', () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    const onChange = show();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Участвовал в матче: Север · игрок 1' }));
    expect(window.confirm).toHaveBeenCalledWith('У игрока Север · игрок 1 фрагментов: 1 — вернуть их в очередь?');
    expect(onChange).toHaveBeenCalledWith([{ track_id: 4, player_id: 'p2' }], ['p1']);
  });

  it('keeps everything when the confirmation is declined', () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    const onChange = show();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Участвовал в матче: Север · игрок 1' }));
    expect(onChange).not.toHaveBeenCalled();
  });

  it('brings a player back without his old fragments', () => {
    const onChange = show(['p2']);
    fireEvent.click(screen.getByRole('checkbox', { name: 'Участвовал в матче: Север · игрок 2' }));
    expect(onChange).toHaveBeenCalledWith(base, []);
  });

  it('removes one fragment of the chosen player', () => {
    const onChange = show();
    fireEvent.click(screen.getByRole('button', { name: '№7 Север · игрок 1' }));
    const own = screen.getByRole('region', { name: 'Фрагменты игрока' });
    fireEvent.click(within(own).getByRole('button', { name: 'Убрать 0:00–0:40' }));
    expect(onChange).toHaveBeenCalledWith([{ track_id: 4, player_id: 'p2' }], []);
  });
});
