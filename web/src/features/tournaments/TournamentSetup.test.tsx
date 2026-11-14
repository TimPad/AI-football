import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';
import { TournamentCreate } from './TournamentSetup';

vi.mock('../auth/Auth', () => ({ useAuth: () => ({ session: { id: 'admin' } }) }));
afterEach(() => {
  localStorage.clear();
  vi.unstubAllGlobals();
});
function mount() {
  return render(
    <MemoryRouter initialEntries={['/tournaments/new']}>
      <Routes>
        <Route path="/tournaments/new" element={<TournamentCreate />} />
        <Route path="/tournaments/:id" element={<h1>Обзор</h1>} />
        <Route path="/tournaments/:id/setup" element={<h1>Продолжение настройки</h1>} />
      </Routes>
    </MemoryRouter>,
  );
}
function fill() {
  for (const [label, value] of [
    ['Название турнира', 'Кубок'],
    ['Начало турнира', '2026-10-18'],
    ['Окончание турнира', '2026-11-18'],
  ])
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
}
it('creates a draft with one «Далее», season from the dates and Moscow by default', async () => {
  const bodies: unknown[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (_input, init) => {
      bodies.push(JSON.parse(init.body));
      return new Response(JSON.stringify({ id: 't1' }));
    }),
  );
  mount();
  fill();
  expect(screen.getByText('Сезон 2026')).toBeInTheDocument();
  expect(screen.getByLabelText('Часовой пояс')).toHaveValue('Europe/Moscow');
  expect(screen.queryByRole('button', { name: 'Создать турнир' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Далее' }));
  await screen.findByRole('heading', { name: 'Продолжение настройки' });
  expect(bodies).toHaveLength(1);
  expect(bodies[0]).toMatchObject({ name: 'Кубок', season: '2026', timezone: 'Europe/Moscow', visibility: 'draft' });
});
it('restores input and replays identical creation after a lost response', async () => {
  const bodies: string[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (_input, init) => {
      bodies.push(init.body);
      if (bodies.length === 1) throw Error('lost');
      return new Response(JSON.stringify({ id: 't1' }));
    }),
  );
  const view = mount();
  fill();
  fireEvent.click(screen.getByRole('button', { name: 'Далее' }));
  await screen.findByRole('button', { name: 'Повторить создание' });
  view.unmount();
  mount();
  expect(screen.getByLabelText('Название турнира')).toHaveValue('Кубок');
  fireEvent.click(screen.getByRole('button', { name: 'Повторить создание' }));
  await screen.findByRole('heading', { name: 'Продолжение настройки' });
  expect(bodies[1]).toBe(bodies[0]);
});
it('derives a two-year season', async () => {
  const { seasonOf } = await import('./TournamentList');
  expect(seasonOf('2026-10-01', '2027-05-30')).toBe('2026/2027');
  expect(seasonOf('2026-10-01', '')).toBe('2026');
});
