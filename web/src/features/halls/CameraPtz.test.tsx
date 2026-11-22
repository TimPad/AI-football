import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { readImageSize } from './FramePicker';
import { HallPage } from './HallPage';

vi.mock('../auth/Auth', () => ({
  useAuth: () => ({ session: { id: 'admin-test', can_manage_analytics: false } }),
}));
// jsdom не декодирует изображения: размер кадра подставляем, остальная разметка — настоящая.
vi.mock('./FramePicker', async (original) => ({
  ...(await original<typeof import('./FramePicker')>()),
  readImageSize: vi.fn(async () => ({ url: 'blob:frame', w: 1000, h: 500 })),
}));
// В jsdom нет PointerEvent: рамку тянут событиями указателя, им нужны координаты мыши.
class FakePointerEvent extends MouseEvent {
  pointerId: number;
  constructor(type: string, init: PointerEventInit = {}) {
    super(type, init);
    this.pointerId = init.pointerId ?? 1;
  }
}
const original = window.PointerEvent;
beforeEach(() => {
  window.PointerEvent = FakePointerEvent as unknown as typeof PointerEvent;
});
afterEach(() => {
  window.PointerEvent = original;
  vi.unstubAllGlobals();
  localStorage.clear();
});

const hall = {
  id: 'h1',
  revision: 1,
  name: 'Арена',
  address: 'Москва',
  pitch_length_m: 40,
  pitch_width_m: 20,
  ceiling_height_m: null,
  surface: '',
  description: '',
  archived: false,
};
// Кадр 1000×500 показан в 500×250: координаты экрана переводятся в пиксели кадра.
function shown(element: Element) {
  element.getBoundingClientRect = () => ({
    left: 0,
    top: 0,
    width: 500,
    height: 250,
    right: 500,
    bottom: 250,
    x: 0,
    y: 0,
    toJSON: () => null,
  });
  return element;
}
function drag(element: Element, [x1, y1]: number[], [x2, y2]: number[]) {
  fireEvent.pointerDown(element, { clientX: x1, clientY: y1 });
  fireEvent.pointerMove(element, { clientX: x2, clientY: y2 });
  fireEvent.pointerUp(element, { clientX: x2, clientY: y2 });
}
type Call = { url: string; method: string; body: unknown };
function stub(profiles: unknown[]) {
  const calls: Call[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: unknown, options: RequestInit = {}) => {
      const json = (v: unknown, status = 200) =>
        new Response(JSON.stringify(v), { status, headers: { 'Content-Type': 'application/json' } });
      const method = options.method ?? 'GET';
      calls.push({
        url: String(url),
        method,
        body: typeof options.body === 'string' ? JSON.parse(options.body) : options.body,
      });
      if (method === 'POST') return json({ ...JSON.parse(String(options.body)), id: 'c1', version: 1 }, 201);
      if (method === 'PUT') return json({ id: 'c1' });
      if (String(url).endsWith('/reference-frame')) return new Response(new Blob(['jpg'], { type: 'image/jpeg' }));
      if (String(url).includes('/camera-profiles')) return json({ items: profiles, total: profiles.length });
      return json(hall);
    }),
  );
  render(
    <MemoryRouter initialEntries={['/halls/h1']}>
      <Routes>
        <Route path="/halls/:id" element={<HallPage />} />
      </Routes>
    </MemoryRouter>,
  );
  return calls;
}

it('creates a broadcast camera: points without an outline, broadcast graphics as frame fractions', async () => {
  const calls = stub([]);
  fireEvent.click(await screen.findByRole('button', { name: 'Добавить профиль камеры' }));
  fireEvent.click(screen.getByRole('button', { name: 'Трансляция с поворотом и зумом' }));
  expect(screen.getByRole('heading', { name: 'Эталонный кадр трансляции' })).toBeInTheDocument();
  expect(screen.getByLabelText('Момент записи')).toBeInTheDocument();
  const input = screen.getByText('Загрузить картинку').querySelector('input')!;
  fireEvent.change(input, { target: { files: [new File(['png'], 'wide.png', { type: 'image/png' })] } });
  const stage = shown(await screen.findByRole('img', { name: 'Разметка точек на кадре' }));
  // Угол 4 на этом плане не виден: добавляем центр поля и убираем угол.
  for (const [x, y] of [
    [0, 0],
    [500, 0],
    [500, 250],
  ])
    fireEvent.click(stage, { clientX: x, clientY: y });
  fireEvent.change(screen.getByLabelText('Добавить точку разметки'), { target: { value: '6' } });
  fireEvent.click(screen.getByRole('button', { name: 'Не отмечать точку 4' }));
  expect(screen.getByRole('status', { name: 'Разметка камеры' })).toHaveTextContent('Центр поля · 20 × 10 м');
  fireEvent.click(stage, { clientX: 250, clientY: 125 });
  expect(screen.getByRole('status', { name: 'Разметка камеры' })).toHaveTextContent('Все точки отмечены');
  // У трансляции контур по углам не рисуется: его строит обработчик.
  expect(stage.querySelector('polygon')).toBeNull();

  fireEvent.click(screen.getByRole('button', { name: 'Графика трансляции' }));
  const graphics = shown(screen.getByRole('img', { name: 'Графика трансляции на кадре' }));
  drag(graphics, [0, 0], [500, 40]); // табло во всю ширину сверху
  drag(graphics, [10, 10], [12, 11]); // случайный клик — не рамка
  expect(screen.getByRole('button', { name: 'Убрать графику 1' })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Убрать графику 2' })).toBeNull();
  expect(screen.getByRole('button', { name: 'Графика трансляции · 1' })).toHaveAttribute('aria-pressed', 'true');
  expect(graphics.querySelectorAll('rect.overlay-rect')).toHaveLength(1);

  fireEvent.click(screen.getByRole('button', { name: 'Сохранить профиль камеры' }));
  await waitFor(() => expect(calls.filter((c) => c.method === 'PUT')).toHaveLength(1));
  const post = calls.find((c) => c.method === 'POST')!.body as Record<string, unknown>;
  expect(post).toMatchObject({
    motion: 'ptz',
    overlay: [[0, 0, 1, 0.16]],
    calibration: null,
    points: [
      { px: [0, 0], m: [0, 0] },
      { px: [999, 0], m: [40, 0] },
      { px: [999, 499], m: [40, 20] },
      { px: [500, 250], m: [20, 10] },
    ],
  });
  expect(post).not.toHaveProperty('pitch_polygon_px');
  expect(calls.find((c) => c.method === 'PUT')!.url).toContain('/camera-profiles/c1/reference-frame');
});

it('puts the pitch corners back first when a broadcast draft turns into a fixed camera', async () => {
  stub([]);
  fireEvent.click(await screen.findByRole('button', { name: 'Добавить профиль камеры' }));
  fireEvent.click(screen.getByRole('button', { name: 'Трансляция с поворотом и зумом' }));
  const input = screen.getByText('Загрузить картинку').querySelector('input')!;
  fireEvent.change(input, { target: { files: [new File(['png'], 'wide.png', { type: 'image/png' })] } });
  const stage = shown(await screen.findByRole('img', { name: 'Разметка точек на кадре' }));
  fireEvent.click(stage, { clientX: 0, clientY: 0 });
  fireEvent.change(screen.getByLabelText('Добавить точку разметки'), { target: { value: '6' } });
  fireEvent.click(screen.getByRole('button', { name: 'Не отмечать точку 1' }));
  fireEvent.click(screen.getByRole('button', { name: 'Неподвижная камера' }));
  // Угол 1 вернулся первым и без отметки; центр поля остался пятой точкой.
  expect(screen.getByRole('status', { name: 'Разметка камеры' })).toHaveTextContent('Отметьте точку 1: Угол · 0 × 0 м');
  expect(screen.getByTitle('Центр поля · 20 × 10 м')).toHaveTextContent('5');
});

it('keeps the fixed camera request exactly as before', async () => {
  const calls = stub([]);
  fireEvent.click(await screen.findByRole('button', { name: 'Добавить профиль камеры' }));
  expect(screen.getByRole('button', { name: 'Неподвижная камера' })).toHaveAttribute('aria-pressed', 'true');
  const input = screen.getByText('Загрузить картинку').querySelector('input')!;
  fireEvent.change(input, { target: { files: [new File(['png'], 'frame.png', { type: 'image/png' })] } });
  const stage = shown(await screen.findByRole('img', { name: 'Разметка точек на кадре' }));
  for (const [x, y] of [
    [0, 0],
    [500, 0],
    [500, 250],
    [0, 250],
  ])
    fireEvent.click(stage, { clientX: x, clientY: y });
  expect(screen.queryByRole('button', { name: 'Графика трансляции' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить профиль камеры' }));
  await waitFor(() => expect(calls.some((c) => c.method === 'POST')).toBe(true));
  const post = calls.find((c) => c.method === 'POST')!.body as Record<string, unknown>;
  expect(Object.keys(post).sort()).toEqual(
    [
      'request_id',
      'expected_hall_revision',
      'name',
      'frame_width',
      'frame_height',
      'points',
      'pitch_polygon_px',
      'calibration',
    ].sort(),
  );
});

const ptzProfile = {
  id: 'c1',
  hall_id: 'h1',
  name: 'Трансляция',
  version: 2,
  hall_revision: 1,
  pitch_length_m: 40,
  pitch_width_m: 20,
  frame_width: 1000,
  frame_height: 500,
  points: [
    { px: [0, 0], m: [0, 0] },
    { px: [999, 0], m: [40, 0] },
    { px: [999, 499], m: [40, 20] },
    { px: [0, 499], m: [0, 20] },
  ],
  motion: 'ptz',
  pitch_polygon_px: null,
  overlay: [[0, 0, 1, 0.16]],
  // 25 px = 1 м: контур по гомографии — весь кадр.
  homography: [
    [0.04, 0, 0],
    [0, 0.04, 0],
    [0, 0, 1],
  ],
  calibration: null,
  reprojection_error_m: 0.02,
  leave_one_out_error_m: null,
  reference_sha256: 'a'.repeat(64),
  replay_badge: null,
  matches_current_dimensions: true,
  created_at: '2026-11-22T10:00:00Z',
};

it('shows the outline built from the points and cuts the replay badge from a replay frame', async () => {
  const calls = stub([ptzProfile]);
  const summary = await screen.findByText(/Трансляция · версия 2 · трансляция/);
  fireEvent.click(summary);
  const figure = screen.getByRole('img', { name: 'Эталонный кадр камеры «Трансляция», версия 2' }).closest('figure')!;
  expect(figure.querySelector('polygon')).toHaveAttribute('points', '0,0 1000,0 1000,500 0,500');
  expect(figure.querySelector('rect.overlay-rect')).toHaveAttribute('height', '80');
  expect(within(figure).getByText(/Эталонный кадр трансляции/)).toBeInTheDocument();

  // Кадр другого разрешения не годится: положение плашки — в пикселях кадра профиля.
  vi.mocked(readImageSize).mockResolvedValueOnce({ url: 'blob:small', w: 640, h: 360 });
  const picture = screen.getByText('Загрузить картинку').querySelector('input')!;
  fireEvent.change(picture, { target: { files: [new File(['png'], 'small.png', { type: 'image/png' })] } });
  expect(await screen.findByText(/Кадр 640 × 360 px, а профиль — 1000 × 500 px/)).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'Обвести на эталонном кадре' }));
  const stage = shown(await screen.findByRole('img', { name: 'Обводка плашки повтора на кадре' }));
  expect(screen.getByRole('button', { name: 'Сохранить плашку' })).toBeDisabled();
  drag(stage, [400, 200], [450, 220]);
  expect(screen.getByRole('status', { name: 'Обводка плашки' })).toHaveTextContent('Плашка 100 × 40 px');
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить плашку' }));
  await waitFor(() => expect(calls.some((c) => c.method === 'PUT')).toBe(true));
  const put = calls.find((c) => c.method === 'PUT')!;
  expect(put.url).toContain('/halls/h1/camera-profiles/c1/replay-badge');
  const form = put.body as FormData;
  expect([form.get('x'), form.get('y'), form.get('width'), form.get('height')]).toEqual(['800', '400', '100', '40']);
  expect(form.get('file')).toBeInstanceOf(File);
});

it('shows a set replay badge instead of the cutting tools', async () => {
  stub([{ ...ptzProfile, replay_badge: { sha256: 'b'.repeat(64), xy: [800, 400], size: [100, 40] } }]);
  fireEvent.click(await screen.findByText(/Трансляция · версия 2/));
  expect(screen.getByRole('img', { name: 'Плашка повтора' })).toHaveAttribute(
    'src',
    '/api/v1/halls/h1/camera-profiles/c1/replay-badge',
  );
  expect(screen.getByText(/левый верхний угол — 800, 400 px/)).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Обвести на эталонном кадре' })).toBeNull();
  expect(document.querySelector('rect.badge-rect')).toHaveAttribute('width', '100');
});
