import { type MouseEvent, type PointerEvent, useState } from 'react';

export type Frame = { file: File; url: string; w: number; h: number };
export type PickPoint = { px: [string, string]; m: [string, string] };
export type Landmark = { label: string; m: [number, number] };
// Прямоугольник в пикселях кадра: x1, y1, x2, y2 (правый нижний край не включается).
export type Rect = [number, number, number, number];

// Точки разметки мини-футбольного поля в метрах: X — вдоль длины, Y — вдоль ширины.
// Отметки 6 и 10 м и ворота 3 м — по правилам футзала; линии поля берутся из карточки зала.
export function landmarks(length: number, width: number): Landmark[] {
  const L = length,
    W = width,
    c = W / 2,
    r = (v: number) => Math.round(v * 100) / 100;
  const at = (x: number, y: number) => `${r(x).toLocaleString('ru-RU')} × ${r(y).toLocaleString('ru-RU')} м`;
  const list: [string, number, number][] = [
    ['Угол', 0, 0],
    ['Угол', L, 0],
    ['Угол', L, W],
    ['Угол', 0, W],
    ['Центральная линия, край', L / 2, 0],
    ['Центральная линия, край', L / 2, W],
    ['Центр поля', L / 2, c],
    ['Отметка 6 м', 6, c],
    ['Отметка 6 м', L - 6, c],
    ['Отметка 10 м', 10, c],
    ['Отметка 10 м', L - 10, c],
    ['Штанга ворот', 0, c - 1.5],
    ['Штанга ворот', 0, c + 1.5],
    ['Штанга ворот', L, c - 1.5],
    ['Штанга ворот', L, c + 1.5],
  ];
  return list.map(([name, x, y]) => ({ label: `${name} · ${at(x, y)}`, m: [r(x), r(y)] }));
}

export function pointLabel(p: PickPoint, marks: Landmark[], i: number) {
  const m = p.m.map(Number);
  return (
    marks.find((l) => Math.abs(l.m[0] - m[0]) < 0.01 && Math.abs(l.m[1] - m[1]) < 0.01)?.label ??
    `Точка ${i + 1} · ${p.m.join(' × ')} м`
  );
}

// Размер кадра — из самого изображения: так точки и эталонный кадр заведомо в одном разрешении.
export function readImageSize(file: File): Promise<{ url: string; w: number; h: number }> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => resolve({ url, w: img.naturalWidth, h: img.naturalHeight });
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error('Не удалось открыть изображение'));
    };
    img.src = url;
  });
}

// Кадр из файла записи — в исходном разрешении видео (скриншот экрана дал бы размер окна, а не записи).
// Видео не покидает компьютер: на сервер уходит только этот кадр. Берём момент через несколько секунд от начала.
export function frameFromVideo(file: File, atSeconds?: number): Promise<File> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const video = document.createElement('video');
    const unreadable =
      'Браузер не смог открыть это видео. Сохраните стоп-кадр в полном разрешении и загрузите картинку.';
    const timer = setTimeout(() => fail(unreadable), 20000);
    const fail = (text: string) => {
      clearTimeout(timer);
      URL.revokeObjectURL(url);
      reject(new Error(text));
    };
    video.muted = true;
    video.preload = 'auto';
    video.playsInline = true;
    video.onerror = () => fail(unreadable);
    // У записей без длительности в заголовке duration = Infinity: тогда берём начало. Ноль не годится — переход на 0 не всегда даёт seeked.
    video.onloadedmetadata = () => {
      if (!video.videoWidth) return fail('В файле нет видеодорожки');
      const d = Number.isFinite(video.duration) ? video.duration : 0;
      // Нужный момент (кадр повтора) — если задан; иначе через несколько секунд от начала.
      const at = atSeconds === undefined ? Math.min(5, d / 2) : d ? Math.min(atSeconds, d - 0.05) : atSeconds;
      video.currentTime = Math.max(0.05, at);
    };
    video.onseeked = () => {
      clearTimeout(timer);
      const canvas = document.createElement('canvas');
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      canvas.getContext('2d')!.drawImage(video, 0, 0);
      URL.revokeObjectURL(url);
      canvas.toBlob(
        (blob) =>
          blob
            ? resolve(new File([blob], 'frame.jpg', { type: 'image/jpeg' }))
            : reject(new Error('Не удалось сохранить кадр')),
        'image/jpeg',
        0.95,
      );
    };
    video.src = url;
  });
}

// Кадр с наложенными точками: клик ставит пиксель активной точки.
export function FramePicker({
  frame,
  points,
  active,
  disabled,
  onPick,
  outline = true,
  rects = [],
}: {
  frame: Frame;
  points: PickPoint[];
  active: number;
  disabled: boolean;
  onPick: (px: [number, number]) => void;
  outline?: boolean; // контур по первым четырём точкам — только у неподвижной камеры
  rects?: Rect[]; // графика трансляции, закрытая от сверки
}) {
  const { w, h } = frame;
  const placed = points.map((p, i) => ({
    i,
    x: Number(p.px[0]),
    y: Number(p.px[1]),
    set: p.px[0] !== '' && p.px[1] !== '',
  }));
  const corners = placed.slice(0, 4).filter((p) => p.set);
  function pick(e: MouseEvent<SVGSVGElement>) {
    if (disabled) return;
    const box = e.currentTarget.getBoundingClientRect();
    const x = Math.round(((e.clientX - box.left) / box.width) * w),
      y = Math.round(((e.clientY - box.top) / box.height) * h);
    onPick([Math.min(w - 1, Math.max(0, x)), Math.min(h - 1, Math.max(0, y))]);
  }
  return (
    <div className="reference-stage frame-picker" style={{ aspectRatio: `${w} / ${h}` }}>
      <img src={frame.url} alt="Кадр с камеры для разметки" />
      <svg
        viewBox={`0 0 ${w} ${h}`}
        role="img"
        aria-label="Разметка точек на кадре"
        onClick={pick}
        style={{ cursor: disabled ? 'default' : 'crosshair' }}
      >
        <Rects rects={rects} />
        {outline && corners.length > 1 && (
          <polygon points={corners.map((p) => `${p.x},${p.y}`).join(' ')} strokeWidth={w / 250} />
        )}
        {placed
          .filter((p) => p.set)
          .map((p) => (
            <g key={p.i} className={p.i === active ? 'active' : ''}>
              <circle cx={p.x} cy={p.y} r={w / (p.i === active ? 120 : 180)} />
              <text x={p.x + w / 120} y={p.y - w / 150} fontSize={w / 45}>
                {p.i + 1}
              </text>
            </g>
          ))}
      </svg>
    </div>
  );
}

export function Rects({ rects, className = 'overlay-rect' }: { rects: Rect[]; className?: string }) {
  return (
    <>
      {rects.map(([x1, y1, x2, y2], i) => (
        <rect key={i} className={className} x={x1} y={y1} width={x2 - x1} height={y2 - y1} />
      ))}
    </>
  );
}

// Кадр, на котором рамку тянут мышью или пальцем: графика трансляции, плашка повтора.
export function RectPicker({
  frame,
  rects,
  label,
  disabled,
  onDraw,
  className,
}: {
  frame: Frame;
  rects: Rect[];
  label: string;
  disabled: boolean;
  onDraw: (rect: Rect) => void;
  className?: string;
}) {
  const { w, h } = frame;
  const [drag, setDrag] = useState<{ x: number; y: number; cx: number; cy: number } | null>(null);
  const at = (e: PointerEvent<SVGSVGElement>): [number, number] => {
    const box = e.currentTarget.getBoundingClientRect();
    return [
      Math.min(w, Math.max(0, Math.round(((e.clientX - box.left) / box.width) * w))),
      Math.min(h, Math.max(0, Math.round(((e.clientY - box.top) / box.height) * h))),
    ];
  };
  const box = (d: NonNullable<typeof drag>): Rect => [
    Math.min(d.x, d.cx),
    Math.min(d.y, d.cy),
    Math.max(d.x, d.cx),
    Math.max(d.y, d.cy),
  ];
  return (
    <div className="reference-stage frame-picker" style={{ aspectRatio: `${w} / ${h}` }}>
      <img src={frame.url} alt="Кадр для обводки рамкой" />
      <svg
        viewBox={`0 0 ${w} ${h}`}
        role="img"
        aria-label={label}
        style={{ cursor: disabled ? 'default' : 'crosshair', touchAction: 'none' }}
        onPointerDown={(e) => {
          if (disabled) return;
          e.currentTarget.setPointerCapture?.(e.pointerId);
          const [x, y] = at(e);
          setDrag({ x, y, cx: x, cy: y });
        }}
        onPointerMove={(e) => {
          if (!drag) return;
          const [cx, cy] = at(e);
          setDrag({ ...drag, cx, cy });
        }}
        onPointerUp={(e) => {
          if (!drag) return;
          const [cx, cy] = at(e);
          setDrag(null);
          const r = box({ ...drag, cx, cy });
          // Случайный клик без протяжки — не рамка.
          if (r[2] - r[0] >= 8 && r[3] - r[1] >= 8) onDraw(r);
        }}
        onPointerCancel={() => setDrag(null)}
      >
        <Rects rects={rects} className={className} />
        {drag && <Rects rects={[box(drag)]} className={`${className ?? 'overlay-rect'} drawing`} />}
      </svg>
    </div>
  );
}

// Контур поля по гомографии «пиксели -> метры» (так его строит обработчик для поворотной камеры).
// Углы, оказавшиеся по разные стороны горизонта, не рисуем: такой профиль сервис бы не принял.
export function outlineFromHomography(H: number[][], length: number, width: number): [number, number][] | null {
  const [[a, b, c], [d, e, f], [g, k, l]] = H;
  const inv = [
    [e * l - f * k, c * k - b * l, b * f - c * e],
    [f * g - d * l, a * l - c * g, c * d - a * f],
    [d * k - e * g, b * g - a * k, a * e - b * d],
  ];
  const corners = [
    [0, 0],
    [length, 0],
    [length, width],
    [0, width],
  ].map(([x, y]) => inv.map((row) => row[0] * x + row[1] * y + row[2]));
  if (!corners.every((p) => p[2] > 0) && !corners.every((p) => p[2] < 0)) return null;
  return corners.map((p) => [p[0] / p[2], p[1] / p[2]]);
}
