import { MapPin, Plus } from 'lucide-react';
import { type FormEvent, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ApiError, all, api, post } from '../../api/client';
import type { CameraProfile, Hall } from '../../api/domain';
import { Check, downloadJson, Empty, ErrorBox, Field, Loading, useLoad } from '../../components/ui';
import { useDocumentTitle } from '../../components/useDocumentTitle';
import { useAuth } from '../auth/Auth';
import { useDraft } from '../protocol/drafts';
import { AddressField } from './AddressField';
import {
  type Frame,
  FramePicker,
  frameFromVideo,
  landmarks,
  outlineFromHomography,
  pointLabel,
  type Rect,
  RectPicker,
  Rects,
  readImageSize,
} from './FramePicker';

export function HallList() {
  useDocumentTitle('Залы');
  const state = useLoad(() => all<Hall>('/halls'), 'halls');
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Залы</h1>
          <p className="muted">Площадки для расписания и видеоаналитики</p>
        </div>
        <Link className="primary button" to="/halls/new">
          <Plus />
          Создать зал
        </Link>
      </div>
      {!state.data ? (
        <Loading error={state.error} retry={state.reload} />
      ) : !state.data.length ? (
        <Empty>Добавьте первый зал, чтобы назначать его матчам.</Empty>
      ) : (
        <div className="hall-cards">
          {state.data.map((h) => (
            <Link className="surface hall-card" key={h.id} to={`/halls/${h.id}`}>
              <div className="row">
                <h2>{h.name}</h2>
                {h.archived && <span className="muted">В архиве</span>}
              </div>
              <p>
                <MapPin size={16} />
                {h.address}
              </p>
              <strong>
                {h.pitch_length_m} × {h.pitch_width_m} м
              </strong>
              <small className="muted">{h.surface || 'Покрытие не указано'}</small>
            </Link>
          ))}
        </div>
      )}
    </>
  );
}
export function HallPage() {
  const { id } = useParams();
  return <HallContent key={id ?? 'new'} id={id} />;
}
function HallContent({ id }: { id?: string }) {
  const navigate = useNavigate();
  const state = useLoad(() => (id ? api<Hall>(`/halls/${id}`) : Promise.resolve(null)), id ?? 'new');
  if (state.data === undefined) return <Loading error={state.error} retry={state.reload} />;
  return (
    <>
      <HallEditor
        key={state.data?.revision ?? 0}
        existing={state.data ?? undefined}
        onSaved={(h) => {
          state.setData(h);
          if (!id) navigate(`/halls/${h.id}`, { replace: true });
        }}
      />
      {state.data && <CameraProfiles hall={state.data} />}
    </>
  );
}
// Optional latitude/longitude keep already-sent legacy drafts safely retryable.
type HallDraft = {
  request_id: string;
  expected_revision: number;
  attempted: boolean;
  name: string;
  address: string;
  pitch_length_m: string;
  pitch_width_m: string;
  ceiling_height_m: string;
  latitude?: string;
  longitude?: string;
  address_source?: 'manual' | 'yandex';
  address_selection_token?: string | null;
  surface: string;
  description: string;
  archived: boolean;
};
function hallDraft(h?: Hall): HallDraft {
  return {
    request_id: crypto.randomUUID(),
    expected_revision: h?.revision ?? 0,
    attempted: false,
    name: h?.name ?? '',
    address: h?.address ?? '',
    pitch_length_m: String(h?.pitch_length_m ?? ''),
    pitch_width_m: String(h?.pitch_width_m ?? ''),
    ceiling_height_m: String(h?.ceiling_height_m ?? ''),
    latitude: h?.latitude == null ? undefined : String(h.latitude),
    longitude: h?.longitude == null ? undefined : String(h.longitude),
    address_source: h?.address_source === 'yandex' ? 'yandex' : 'manual',
    surface: h?.surface ?? '',
    description: h?.description ?? '',
    archived: h?.archived ?? false,
  };
}
function validHall(v: unknown): v is HallDraft {
  const d = v as HallDraft;
  return (
    !!d &&
    typeof d.request_id === 'string' &&
    typeof d.expected_revision === 'number' &&
    typeof d.attempted === 'boolean' &&
    typeof d.archived === 'boolean' &&
    ['name', 'address', 'pitch_length_m', 'pitch_width_m', 'ceiling_height_m', 'surface', 'description'].every(
      (k) => typeof d[k as keyof HallDraft] === 'string',
    )
  );
}
const optionalNumber = (value: string) => (value === '' ? null : Number(value));
export function HallEditor({
  existing,
  onSaved,
  embedded = false,
  draftScope,
}: {
  existing?: Hall;
  onSaved: (h: Hall) => void;
  embedded?: boolean;
  draftScope?: string;
}) {
  const auth = useAuth();
  const [initial] = useState(() => hallDraft(existing));
  const draft = useDraft(
    `aifootball:hall:${auth.session!.id}:${draftScope ?? existing?.id ?? 'new'}`,
    initial,
    validHall,
  );
  const d = draft.value;
  const [busy, setBusy] = useState(false);
  const [addressBusy, setAddressBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const locked = busy || d.attempted || draft.corrupt;
  function change(patch: Partial<HallDraft>) {
    draft.change({ ...d, ...patch, request_id: crypto.randomUUID() });
  }
  async function save(e: FormEvent) {
    e.preventDefault();
    if (addressBusy) return;
    setBusy(true);
    setError(undefined);
    const submitted = { ...d, attempted: true };
    if (!d.attempted && !d.address_source && !d.address_selection_token) {
      delete submitted.latitude;
      delete submitted.longitude;
    }
    draft.change(submitted);
    const body = {
      request_id: d.request_id,
      name: d.name,
      address: d.address,
      pitch_length_m: Number(d.pitch_length_m),
      pitch_width_m: Number(d.pitch_width_m),
      ceiling_height_m: optionalNumber(d.ceiling_height_m),
      ...(submitted.latitude !== undefined && submitted.longitude !== undefined
        ? { latitude: optionalNumber(submitted.latitude), longitude: optionalNumber(submitted.longitude) }
        : {}),
      ...(submitted.address_selection_token ? { address_selection_token: submitted.address_selection_token } : {}),
      surface: d.surface,
      description: d.description,
    };
    try {
      const h = existing
        ? await api<Hall>(`/halls/${existing.id}`, {
            method: 'PUT',
            body: JSON.stringify({ ...body, expected_revision: d.expected_revision, archived: d.archived }),
          })
        : await post<Hall>('/halls', body);
      draft.clear();
      onSaved(h);
    } catch (e) {
      setError(e);
      if (!(e instanceof ApiError) || (e.code !== 'network' && e.status < 500))
        draft.change({ ...d, attempted: false, request_id: crypto.randomUUID() });
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      {!embedded && (
        <>
          <Link className="breadcrumb" to="/halls">
            Залы / {existing ? 'Карточка зала' : 'Новый зал'}
          </Link>
          <div className="page-head">
            <div>
              <h1>{existing ? existing.name : 'Создать зал'}</h1>
              <p className="muted">Укажите размеры игровой площадки между линиями разметки.</p>
            </div>
          </div>
        </>
      )}
      {draft.dirty && <p className="draft-banner">Ввод сохранён в черновике</p>}
      {draft.error && <p className="error">{draft.error}</p>}
      {d.attempted && !busy && (
        <p className="warning">Ответ на сохранение не получен. Повторная отправка не создаст второй зал.</p>
      )}
      <form onSubmit={save} className="surface">
        <fieldset className="team-fieldset" disabled={locked}>
          <div className="form-grid">
            <Field label="Название зала">
              <input required maxLength={200} value={d.name} onChange={(e) => change({ name: e.target.value })} />
            </Field>
            <AddressField
              disabled={locked}
              onBusyChange={setAddressBusy}
              value={{
                address: d.address,
                latitude: d.latitude ? Number(d.latitude) : null,
                longitude: d.longitude ? Number(d.longitude) : null,
                source: d.address_source ?? 'manual',
                selectionToken: d.address_selection_token ?? null,
              }}
              onChange={(v) =>
                change({
                  address: v.address,
                  latitude: v.latitude == null ? '' : String(v.latitude),
                  longitude: v.longitude == null ? '' : String(v.longitude),
                  address_selection_token: v.selectionToken,
                  address_source: v.source,
                })
              }
            />
            {(
              [
                ['pitch_length_m', 'Длина поля, м', true, 300],
                ['pitch_width_m', 'Ширина поля, м', true, 300],
                ['ceiling_height_m', 'Высота потолка, м', false, 100],
              ] as const
            ).map(([key, label, required, max]) => (
              <Field key={key} label={label}>
                <input
                  type="number"
                  required={required}
                  min="0.01"
                  max={max}
                  step="any"
                  value={d[key]}
                  onChange={(e) => change({ [key]: e.target.value })}
                />
              </Field>
            ))}
            {Number(d.pitch_width_m) > Number(d.pitch_length_m) && Number(d.pitch_length_m) > 0 && (
              <p className="warning hall-size-warning">
                Ширина больше длины — похоже, перепутаны. Длина — между воротами, обычно она больше ширины.
              </p>
            )}
            <Field label="Покрытие">
              <input
                maxLength={200}
                placeholder="Паркет, резина, искусственная трава"
                value={d.surface}
                onChange={(e) => change({ surface: e.target.value })}
              />
            </Field>
          </div>
          <Field label="Описание зала">
            <textarea
              rows={3}
              maxLength={4000}
              value={d.description}
              onChange={(e) => change({ description: e.target.value })}
            />
          </Field>
          {existing && (
            <Check label="Зал в архиве" checked={d.archived} onChange={(archived) => change({ archived })} />
          )}
        </fieldset>
        <ErrorBox error={error} />
        {error instanceof ApiError && error.status === 409 && (
          <button
            type="button"
            onClick={() => {
              draft.clear();
              window.location.reload();
            }}
          >
            Отбросить ввод и обновить с сервера
          </button>
        )}
        <div className="team-save-bar">
          <button className="primary" disabled={busy || addressBusy || draft.corrupt}>
            {busy ? 'Сохраняем…' : d.attempted ? 'Повторить сохранение' : 'Сохранить зал'}
          </button>
          <button type="button" onClick={() => downloadJson(d, 'зал-черновик.json')}>
            Скачать ввод
          </button>
        </div>
        {existing && (
          <p className="muted">
            Матчи сохраняют выбранные размеры. Правка карточки зала применяется к новым назначениям.
          </p>
        )}
      </form>
    </>
  );
}
type Point = { px: [string, string]; m: [string, string] };
type Motion = 'fixed' | 'ptz';
// motion и overlay необязательны: черновики, сохранённые до поворотных камер, остаются годными.
type CameraDraft = {
  request_id: string;
  expected_hall_revision: number;
  attempted: boolean;
  name: string;
  frame_width: string;
  frame_height: string;
  points: Point[];
  polygon: string;
  calibration: string;
  motion?: Motion;
  overlay?: number[][]; // графика трансляции, доли кадра x1, y1, x2, y2
};
const cornerPoints = (h: Hall): Point[] =>
  [
    [0, 0],
    [h.pitch_length_m, 0],
    [h.pitch_length_m, h.pitch_width_m],
    [0, h.pitch_width_m],
  ].map((m) => ({ px: ['', ''], m: m.map(String) as [string, string] }));
// Неподвижной камере контур строится по первым четырём точкам — углам поля. У трансляции углы могли убрать:
// возвращаем их на первые места, отметки уже отмеченных точек сохраняются.
function cornersFirst(points: Point[], h: Hall): Point[] {
  const same = (a: Point, b: Point) => a.m.every((v, i) => Number(v) === Number(b.m[i]));
  const corners = cornerPoints(h).map((c) => points.find((p) => same(p, c)) ?? c);
  return [...corners, ...points.filter((p) => !corners.some((c) => same(p, c)))];
}
function cameraDraft(h: Hall): CameraDraft {
  return {
    request_id: crypto.randomUUID(),
    expected_hall_revision: h.revision,
    attempted: false,
    name: 'Основная камера',
    frame_width: '',
    frame_height: '',
    points: cornerPoints(h),
    polygon: '',
    calibration: '',
  };
}
function validCamera(v: unknown): v is CameraDraft {
  const d = v as CameraDraft;
  return (
    !!d &&
    typeof d.request_id === 'string' &&
    typeof d.expected_hall_revision === 'number' &&
    typeof d.attempted === 'boolean' &&
    ['name', 'frame_width', 'frame_height', 'polygon', 'calibration'].every(
      (k) => typeof d[k as keyof CameraDraft] === 'string',
    ) &&
    (d.motion === undefined || d.motion === 'fixed' || d.motion === 'ptz') &&
    (d.overlay === undefined ||
      (Array.isArray(d.overlay) &&
        d.overlay.every((r) => Array.isArray(r) && r.length === 4 && r.every((v) => typeof v === 'number')))) &&
    Array.isArray(d.points) &&
    d.points.length >= 4 &&
    d.points.every(
      (p) =>
        p &&
        Array.isArray(p.px) &&
        Array.isArray(p.m) &&
        p.px.length === 2 &&
        p.m.length === 2 &&
        [...p.px, ...p.m].every((x) => typeof x === 'string'),
    )
  );
}
function CameraProfiles({ hall }: { hall: Hall }) {
  const state = useLoad(() => all<CameraProfile>(`/halls/${hall.id}/camera-profiles`), `${hall.id}:${hall.revision}`);
  const [open, setOpen] = useState(false);
  return (
    <section className="surface hall-profiles">
      <div className="panel-head">
        <div>
          <h2>Камеры и координаты поля</h2>
          <p className="muted">
            Точки на кадре → метры на поле: для неподвижной камеры и для трансляции с поворотом и зумом.
          </p>
        </div>
        <button disabled={hall.archived} onClick={() => setOpen(!open)}>
          {open ? 'Закрыть форму' : 'Добавить профиль камеры'}
        </button>
      </div>
      {open && (
        <CameraEditor
          key={hall.revision}
          hall={hall}
          onSaved={() => {
            state.reload();
            setOpen(false);
          }}
        />
      )}
      {!state.data ? (
        <Loading error={state.error} retry={state.reload} />
      ) : !state.data.length ? (
        <p className="muted">Профиль ещё не добавлен. Для назначения зала в расписании он не требуется.</p>
      ) : (
        <div className="camera-versions">
          {state.data.map((p) => (
            <details key={p.id}>
              <summary>
                {p.name} · версия {p.version}
                {p.motion === 'ptz' ? ' · трансляция' : ''}
                {!p.matches_current_dimensions ? ' · прежние размеры поля' : ''}
              </summary>
              <p className="muted">
                Кадр {p.frame_width} × {p.frame_height} · поле {metres(p.pitch_length_m)} × {metres(p.pitch_width_m)} м
                · точность разметки около {cm(p.reprojection_error_m)} см
                {p.leave_one_out_error_m != null ? ` (проверка — ${cm(p.leave_one_out_error_m)} см)` : ''}
              </p>
              <ReferenceFrame hall={hall} profile={p} onSaved={state.reload} />
              {p.motion === 'ptz' && <ReplayBadge hall={hall} profile={p} onSaved={state.reload} />}
              <ProfilePoints points={p.points} />
            </details>
          ))}
        </div>
      )}
    </section>
  );
}
const metres = (v: number) => v.toLocaleString('ru-RU', { maximumFractionDigits: 2 });
const cm = (m: number) => Math.max(1, Math.round(m * 100));
// Опорные точки — свёрнутой таблицей: номер совпадает с подписью точки на эталонном кадре.
function ProfilePoints({ points }: { points: CameraProfile['points'] }) {
  return (
    <details className="profile-points">
      <summary>Опорные точки · {points.length}</summary>
      <table>
        <thead>
          <tr>
            <th>№</th>
            <th>На кадре, px</th>
            <th>На поле, м</th>
          </tr>
        </thead>
        <tbody>
          {(points as { px: number[]; m: number[] }[]).map((pt, i) => (
            <tr key={i} className="num">
              <td>{i + 1}</td>
              <td>{pt.px.map((v) => Math.round(v)).join(' × ')}</td>
              <td>{pt.m.map(metres).join(' × ')}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}
// Эталонный кадр версии профиля: обработчик сверяет с ним положение камеры в каждой записи
// и сам поправляет небольшой сдвиг. Точки и контур рисуются поверх — видно, легли ли они на разметку.
function ReferenceFrame({ hall, profile, onSaved }: { hall: Hall; profile: CameraProfile; onSaved: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const path = `/halls/${hall.id}/camera-profiles/${profile.id}/reference-frame`;
  async function upload(file: File) {
    setBusy(true);
    setError(undefined);
    try {
      const body = new FormData();
      body.set('file', file);
      await api<CameraProfile>(path, { method: 'PUT', body, signal: AbortSignal.timeout(120000) });
      onSaved();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  const w = profile.frame_width,
    h = profile.frame_height;
  const ptz = profile.motion === 'ptz';
  // У трансляции контур не размечен: показываем тот, что обработчик построит по точкам.
  const outline = ptz
    ? outlineFromHomography(profile.homography, profile.pitch_length_m, profile.pitch_width_m)
    : profile.pitch_polygon_px;
  const badge = profile.replay_badge;
  if (profile.reference_sha256)
    return (
      <figure className="reference-frame">
        <div className="reference-stage" style={{ aspectRatio: `${w} / ${h}` }}>
          <img src={`/api/v1${path}`} alt={`Эталонный кадр камеры «${profile.name}», версия ${profile.version}`} />
          <svg viewBox={`0 0 ${w} ${h}`} aria-hidden="true">
            <Rects rects={(profile.overlay ?? []).map((r) => fractionsToPx(r, w, h))} />
            {badge && (
              <Rects
                className="badge-rect"
                rects={[[badge.xy[0], badge.xy[1], badge.xy[0] + badge.size[0], badge.xy[1] + badge.size[1]]]}
              />
            )}
            {outline && <polygon points={outline.map((p) => p.join(',')).join(' ')} strokeWidth={w / 250} />}
            {(profile.points as { px: [number, number] }[]).map((p, i) => (
              <g key={i}>
                <circle cx={p.px[0]} cy={p.px[1]} r={w / 180} />
                <text x={p.px[0] + w / 120} y={p.px[1] - w / 150} fontSize={w / 45}>
                  {i + 1}
                </text>
              </g>
            ))}
          </svg>
        </div>
        <figcaption className="muted">
          {ptz ? (
            <>
              Эталонный кадр трансляции. Каждый кадр записи обработчик привязывает к нему по фону: стенам, баннерам,
              разметке. Графика трансляции (жёлтый пунктир) в сверку не идёт, кадры с плашкой повтора (красная рамка) —
              в координаты. Контур построен по точкам и должен лечь на линии поля.
            </>
          ) : (
            <>
              Эталонный кадр. В каждой записи обработчик сверяет с ним положение камеры и сам поправляет небольшой
              сдвиг; при большом — попросит новую версию профиля. Точки и контур нанесены по профилю и должны лежать на
              разметке поля.
            </>
          )}
        </figcaption>
      </figure>
    );
  return (
    <div className="reference-upload">
      {ptz ? (
        <p>
          Эталонный кадр не загружен, а без него задание по трансляции не выдаётся. Загрузите кадр, на котором отмечены
          точки ({w} × {h} px): к нему обработчик привяжет каждый кадр записи.
        </p>
      ) : (
        <p>
          Эталонный кадр не загружен. Загрузите кадр этой камеры в том же положении и разрешении ({w} × {h} px), по
          которому отмечены точки: обработчик будет сам замечать сдвиг камеры между днями и поправлять геометрию.
        </p>
      )}
      <label className={`button${busy ? ' disabled' : ''}`}>
        {busy ? 'Загружаем…' : 'Загрузить эталонный кадр'}
        <input
          type="file"
          accept="image/jpeg,image/png,image/webp"
          hidden
          disabled={busy || hall.archived}
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) upload(f);
            e.target.value = '';
          }}
        />
      </label>
      <ErrorBox error={error} />
      <p className="muted small">
        Кадр задаётся один раз для версии профиля. Задания, выданные до загрузки, создайте заново.
      </p>
    </div>
  );
}
const fractionsToPx = (r: number[], w: number, h: number): Rect => [r[0] * w, r[1] * h, r[2] * w, r[3] * h];
const pxToFractions = (r: Rect, w: number, h: number) =>
  [r[0] / w, r[1] / h, r[2] / w, r[3] / h].map((v) => Math.round(v * 10000) / 10000);
// «12:34» или «1:02:03» -> секунды; пусто или неразборчиво — undefined (берётся начало записи).
function seconds(value: string) {
  const parts = value.trim().split(':').map(Number);
  if (!value.trim() || parts.length > 3 || parts.some((v) => !Number.isFinite(v) || v < 0)) return undefined;
  return parts.reduce((total, v) => total * 60 + v, 0);
}
// Момент записи для кадра: самый широкий план для эталона, повтор с плашкой.
function MomentField({ value, onChange, label }: { value: string; onChange: (v: string) => void; label: string }) {
  return (
    <label className="moment-field">
      {label}
      <input inputMode="numeric" placeholder="мм:сс" value={value} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}
// Плашка повтора трансляции: по ней обработчик узнаёт повторы — их снимает та же камера, и по фону склейку
// не заметить. Обводится на полном кадре повтора; сервер сам вырезает её и запоминает положение.
function ReplayBadge({ hall, profile, onSaved }: { hall: Hall; profile: CameraProfile; onSaved: () => void }) {
  const [frame, setFrame] = useState<Frame | null>(null);
  const [rect, setRect] = useState<Rect | null>(null);
  const [moment, setMoment] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const base = `/halls/${hall.id}/camera-profiles/${profile.id}`;
  const badge = profile.replay_badge;
  const w = profile.frame_width,
    h = profile.frame_height;
  if (badge)
    return (
      <figure className="replay-badge">
        <img src={`/api/v1${base}/replay-badge`} alt="Плашка повтора" width={badge.size[0]} height={badge.size[1]} />
        <figcaption className="muted">
          Плашка повтора {badge.size[0]} × {badge.size[1]} px, левый верхний угол — {badge.xy[0]}, {badge.xy[1]} px.
          Кадры с ней обработчик считает повтором и в координаты не берёт. Другую плашку задаёт новая версия профиля.
        </figcaption>
      </figure>
    );
  async function open(load: () => Promise<File>) {
    setError(undefined);
    setBusy(true);
    try {
      const file = await load();
      const size = await readImageSize(file);
      if (size.w !== w || size.h !== h) {
        URL.revokeObjectURL(size.url);
        throw new Error(
          `Кадр ${size.w} × ${size.h} px, а профиль — ${w} × ${h} px. Нужен кадр той же трансляции в полном разрешении.`,
        );
      }
      if (frame) URL.revokeObjectURL(frame.url);
      setFrame({ file, url: size.url, w, h });
      setRect(null);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  async function save() {
    if (!frame || !rect) return;
    setBusy(true);
    setError(undefined);
    try {
      const body = new FormData();
      body.set('file', frame.file);
      body.set('x', String(rect[0]));
      body.set('y', String(rect[1]));
      body.set('width', String(rect[2] - rect[0]));
      body.set('height', String(rect[3] - rect[1]));
      await api<CameraProfile>(`${base}/replay-badge`, { method: 'PUT', body, signal: AbortSignal.timeout(120000) });
      URL.revokeObjectURL(frame.url);
      onSaved();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="replay-badge-setup">
      <h3>Плашка повтора</h3>
      <p className="muted">
        Необязательно. Повторы трансляция показывает той же камерой, и по фону их не отличить от игры. Если в повторе
        есть плашка — логотип или надпись «Повтор», — обведите её на кадре повтора: такие кадры обработчик не возьмёт в
        координаты и метры.
      </p>
      <div className="row wrap">
        {profile.reference_sha256 && (
          <button
            type="button"
            disabled={busy || hall.archived}
            onClick={() =>
              open(async () => {
                const r = await fetch(`/api/v1${base}/reference-frame`, { credentials: 'same-origin' });
                if (!r.ok) throw new Error('Не удалось открыть эталонный кадр');
                return new File([await r.blob()], 'reference.jpg', { type: 'image/jpeg' });
              })
            }
          >
            Обвести на эталонном кадре
          </button>
        )}
        <MomentField label="Повтор в записи" value={moment} onChange={setMoment} />
        <label className={`button${busy ? ' disabled' : ''}`}>
          Взять кадр повтора из записи
          <input
            type="file"
            accept="video/*"
            hidden
            disabled={busy || hall.archived}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void open(() => frameFromVideo(f, seconds(moment)));
              e.target.value = '';
            }}
          />
        </label>
        <label className={`button${busy ? ' disabled' : ''}`}>
          Загрузить картинку
          <input
            type="file"
            accept="image/jpeg,image/png,image/webp"
            hidden
            disabled={busy || hall.archived}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void open(async () => f);
              e.target.value = '';
            }}
          />
        </label>
      </div>
      {frame && (
        <>
          <p className="frame-step" role="status" aria-label="Обводка плашки">
            {rect
              ? `Плашка ${rect[2] - rect[0]} × ${rect[3] - rect[1]} px. Если рамка неточная, обведите заново.`
              : 'Обведите плашку рамкой: нажмите в одном углу и протяните до противоположного.'}
          </p>
          <RectPicker
            frame={frame}
            rects={rect ? [rect] : []}
            label="Обводка плашки повтора на кадре"
            className="badge-rect"
            disabled={busy}
            onDraw={setRect}
          />
          <button type="button" className="primary" disabled={!rect || busy} onClick={save}>
            {busy ? 'Сохраняем…' : 'Сохранить плашку'}
          </button>
        </>
      )}
      <ErrorBox error={error} />
    </div>
  );
}
function CameraEditor({ hall, onSaved }: { hall: Hall; onSaved: () => void }) {
  const auth = useAuth();
  const [initial] = useState(() => cameraDraft(hall));
  const draft = useDraft(`aifootball:camera:${auth.session!.id}:${hall.id}:${hall.revision}`, initial, validCamera);
  const d = draft.value;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const locked = busy || d.attempted || draft.corrupt;
  // Кадр живёт только в браузере до сохранения: после создания профиля он же загружается как эталонный.
  const [frame, setFrame] = useState<Frame | null>(null);
  const [chosen, setChosen] = useState<number | null>(null);
  const marks = landmarks(hall.pitch_length_m, hall.pitch_width_m);
  const empty = (p: Point) => p.px[0] === '' || p.px[1] === '';
  const ptz = d.motion === 'ptz';
  const overlay = d.overlay ?? [];
  // Трансляция: на кадре отмечают или точки разметки, или графику трансляции.
  const [drawing, setDrawing] = useState(false);
  const [moment, setMoment] = useState('');
  // Активная точка — выбранная вручную или первая неотмеченная; когда отмечены все, клик по кадру ничего не меняет.
  const active = chosen ?? d.points.findIndex(empty);
  function change(patch: Partial<CameraDraft>) {
    draft.change({ ...d, ...patch, request_id: crypto.randomUUID() });
  }
  const [reading, setReading] = useState(false);
  const specialist = !!auth.session?.can_manage_analytics;
  async function openFrame(source: File) {
    setError(undefined);
    setReading(true);
    try {
      const file = source.type.startsWith('video/')
        ? await frameFromVideo(source, ptz ? seconds(moment) : undefined)
        : source;
      const { url, w, h } = await readImageSize(file);
      if (frame) URL.revokeObjectURL(frame.url);
      setFrame({ file, url, w, h });
      change({ frame_width: String(w), frame_height: String(h) });
      setChosen(null);
    } catch (e) {
      setError(e);
    } finally {
      setReading(false);
    }
  }
  function pick(px: [number, number]) {
    const points = d.points.map((p, n) => (n === active ? { ...p, px: px.map(String) as [string, string] } : p));
    change({ points });
    // Следующей становится первая ещё не отмеченная точка.
    const next = points.findIndex(empty);
    setChosen(next < 0 ? null : next);
  }
  function addLandmark(index: number) {
    const m = marks[index];
    if (!m) return;
    change({ points: [...d.points, { px: ['', ''], m: m.m.map(String) as [string, string] }] });
    setChosen(d.points.length);
  }
  async function save(e: FormEvent) {
    e.preventDefault();
    setError(undefined);
    const missing = d.points.map((p, i) => (empty(p) || p.m[0] === '' || p.m[1] === '' ? i + 1 : 0)).filter(Boolean);
    if (!d.frame_width || !d.frame_height) {
      setError(new Error('Сначала возьмите кадр с этой камеры'));
      return;
    }
    if (missing.length) {
      setError(new Error(`Отметьте на кадре точки: ${missing.join(', ')}`));
      return;
    }
    setBusy(true);
    try {
      const points = d.points.map((p) => ({ px: p.px.map(Number), m: p.m.map(Number) }));
      const body = {
        request_id: d.request_id,
        expected_hall_revision: d.expected_hall_revision,
        name: d.name,
        frame_width: Number(d.frame_width),
        frame_height: Number(d.frame_height),
        points,
        // Трансляция: контур обработчик строит по точкам, объектив с зумом не калибруется.
        ...(ptz
          ? { motion: 'ptz', overlay }
          : { pitch_polygon_px: d.polygon.trim() ? JSON.parse(d.polygon) : points.slice(0, 4).map((p) => p.px) }),
        calibration: !ptz && d.calibration.trim() ? JSON.parse(d.calibration) : null,
      };
      draft.change({ ...d, attempted: true });
      const profile = await post<CameraProfile>(`/halls/${hall.id}/camera-profiles`, body);
      draft.clear();
      // Тот же кадр — эталонный: для сверки сдвига камеры, а у трансляции — для привязки каждого кадра записи.
      // Ошибка загрузки не отменяет созданный профиль: кадр можно загрузить в карточке профиля.
      if (frame) {
        try {
          const form = new FormData();
          form.set('file', frame.file);
          await api<CameraProfile>(`/halls/${hall.id}/camera-profiles/${profile.id}/reference-frame`, {
            method: 'PUT',
            body: form,
            signal: AbortSignal.timeout(120000),
          });
        } catch {
          /* кадр можно загрузить в карточке профиля */
        }
      }
      onSaved();
    } catch (e) {
      setError(e);
      if (!(e instanceof ApiError) || (e.code !== 'network' && e.status < 500))
        draft.change({ ...d, attempted: false, request_id: crypto.randomUUID() });
    } finally {
      setBusy(false);
    }
  }
  const table = (
    <>
      <div className="team-table-scroll">
        <table className="camera-point-table">
          <thead>
            <tr>
              <th>Точка</th>
              <th>X кадра, px</th>
              <th>Y кадра, px</th>
              <th>X поля, м</th>
              <th>Y поля, м</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {d.points.map((p, i) => (
              <tr key={i}>
                <th>{i + 1}</th>
                {(['px', 'm'] as const).flatMap((kind) =>
                  [0, 1].map((axis) => (
                    <td key={`${kind}:${axis}`}>
                      <input
                        aria-label={`Точка ${i + 1}: ${axis ? 'Y' : 'X'} ${kind === 'px' ? 'кадра' : 'поля'}`}
                        type="number"
                        step="any"
                        min={0}
                        max={
                          kind === 'px'
                            ? Number(axis ? d.frame_height : d.frame_width) - 1
                            : axis
                              ? hall.pitch_width_m
                              : hall.pitch_length_m
                        }
                        value={p[kind][axis]}
                        onChange={(e) =>
                          change({
                            points: d.points.map((point, n) =>
                              n === i
                                ? {
                                    ...point,
                                    [kind]: point[kind].map((v, a) => (a === axis ? e.target.value : v)) as [
                                      string,
                                      string,
                                    ],
                                  }
                                : point,
                            ),
                          })
                        }
                      />
                    </td>
                  )),
                )}
                <td>
                  {(i >= 4 || (ptz && d.points.length > 4)) && (
                    <button
                      type="button"
                      aria-label={`Убрать точку ${i + 1}`}
                      onClick={() => {
                        change({ points: d.points.filter((_, n) => n !== i) });
                        setChosen(null);
                      }}
                    >
                      ×
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button
        type="button"
        disabled={d.points.length >= 50}
        onClick={() => change({ points: [...d.points, { px: ['', ''], m: ['', ''] }] })}
      >
        Добавить опорную точку
      </button>
    </>
  );
  return (
    <form className="camera-editor" onSubmit={save} noValidate>
      {draft.error && <p className="error">{draft.error}</p>}
      {d.attempted && !busy && (
        <p className="warning">Повторите сохранение, чтобы получить ответ для того же профиля.</p>
      )}
      <fieldset className="team-fieldset" disabled={locked}>
        <Field label="Название камеры">
          <input required maxLength={200} value={d.name} onChange={(e) => change({ name: e.target.value })} />
        </Field>
        <div className="camera-motion">
          <div className="segmented" role="group" aria-label="Как снимает камера">
            {(['fixed', 'ptz'] as const).map((m) => (
              <button
                key={m}
                type="button"
                className={(d.motion ?? 'fixed') === m ? 'active' : ''}
                aria-pressed={(d.motion ?? 'fixed') === m}
                onClick={() => {
                  change(m === 'fixed' ? { motion: m, points: cornersFirst(d.points, hall) } : { motion: m });
                  setDrawing(false);
                  setChosen(null);
                }}
              >
                {m === 'fixed' ? 'Неподвижная камера' : 'Трансляция с поворотом и зумом'}
              </button>
            ))}
          </div>
          <p className="muted small">
            {ptz
              ? 'Оператор поворачивает камеру и меняет зум. Точки отмечаются на одном эталонном кадре, а каждый кадр записи обработчик сам привяжет к нему по фону: стенам, баннерам, разметке.'
              : 'Камера закреплена и весь матч смотрит в одну точку.'}
          </p>
        </div>
        <h3>{ptz ? 'Эталонный кадр трансляции' : 'Кадр с камеры'}</h3>
        {!frame && !ptz && (
          <p className="muted">
            Возьмите кадр из записи этой камеры — кликом отметите на нём углы поля. Подойдёт любой момент матча: важна
            неподвижная разметка, а не игроки. Видео остаётся на компьютере, на сервер уходит только кадр; после
            сохранения он станет эталонным, и обработчик будет замечать сдвиг камеры.
          </p>
        )}
        {!frame && ptz && (
          <p className="muted">
            Возьмите самый широкий план матча, где видно больше всего разметки, без повтора и графики на весь экран.
            Укажите момент записи или загрузите стоп-кадр. Видео остаётся на компьютере, на сервер уходит только кадр.
          </p>
        )}
        <div className="row wrap">
          {ptz && <MomentField label="Момент записи" value={moment} onChange={setMoment} />}
          <label className={`button${frame ? '' : ' primary'}`}>
            {reading ? 'Открываем…' : frame ? 'Взять другой кадр из записи' : 'Взять кадр из записи'}
            <input
              type="file"
              accept="video/*"
              hidden
              disabled={reading}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void openFrame(f);
                e.target.value = '';
              }}
            />
          </label>
          <label className="button">
            {frame ? 'Заменить картинкой' : 'Загрузить картинку'}
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp"
              hidden
              disabled={reading}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void openFrame(f);
                e.target.value = '';
              }}
            />
          </label>
        </div>
        {!frame && (
          <p className="muted small">
            Картинка — стоп-кадр в полном разрешении записи (например, сохранённый в VLC), а не снимок экрана.
          </p>
        )}
        {frame && ptz && (
          <div className="segmented" role="group" aria-label="Что отмечать на кадре">
            <button
              type="button"
              className={drawing ? '' : 'active'}
              aria-pressed={!drawing}
              onClick={() => setDrawing(false)}
            >
              Точки разметки
            </button>
            <button
              type="button"
              className={drawing ? 'active' : ''}
              aria-pressed={drawing}
              onClick={() => setDrawing(true)}
            >
              Графика трансляции{overlay.length ? ` · ${overlay.length}` : ''}
            </button>
          </div>
        )}
        {frame && ptz && drawing && (
          <>
            <p className="frame-step" role="status" aria-label="Графика трансляции">
              Обведите рамкой табло, логотипы и бегущую строку — всё, что нарисовано поверх картинки и не двигается
              вместе с полем. Нажмите в одном углу и протяните до противоположного.
            </p>
            <RectPicker
              frame={frame}
              rects={overlay.map((r) => fractionsToPx(r, frame.w, frame.h))}
              label="Графика трансляции на кадре"
              disabled={locked || overlay.length >= 20}
              onDraw={(r) => change({ overlay: [...overlay, pxToFractions(r, frame.w, frame.h)] })}
            />
            <div className="frame-points">
              {overlay.map((r, i) => (
                <button
                  type="button"
                  key={i}
                  aria-label={`Убрать графику ${i + 1}`}
                  title={`${Math.round(r[0] * 100)}–${Math.round(r[2] * 100)}% ширины, ${Math.round(r[1] * 100)}–${Math.round(r[3] * 100)}% высоты`}
                  onClick={() => change({ overlay: overlay.filter((_, n) => n !== i) })}
                >
                  Графика {i + 1} ×
                </button>
              ))}
            </div>
            <p className="muted small">
              Обработчик не ищет по графике совпадений с эталоном и не берёт оттуда игроков. Если графики нет, ничего не
              обводите.
            </p>
          </>
        )}
        {frame && !drawing && (
          <>
            <p className="frame-step" role="status" aria-label="Разметка камеры">
              {active < 0 ? (
                'Все точки отмечены. Чтобы поправить точку, выберите её номер ниже.'
              ) : (
                <>
                  Отметьте точку {active + 1}: <b>{pointLabel(d.points[active], marks, active)}</b> — кликните по этому
                  месту на кадре.
                </>
              )}
            </p>
            <FramePicker
              frame={frame}
              points={d.points}
              active={active}
              disabled={locked || active < 0}
              onPick={pick}
              outline={!ptz}
              rects={ptz ? overlay.map((r) => fractionsToPx(r, frame.w, frame.h)) : []}
            />
            <div className="frame-points">
              {d.points.map((p, i) => (
                <span key={i} className="frame-point">
                  <button
                    type="button"
                    aria-pressed={i === active}
                    className={empty(p) ? '' : 'done'}
                    onClick={() => setChosen(i)}
                    title={pointLabel(p, marks, i)}
                  >
                    {i + 1}
                    {empty(p) ? '' : ' ✓'}
                  </button>
                  {ptz && d.points.length > 4 && (
                    <button
                      type="button"
                      className="frame-point-remove"
                      aria-label={`Не отмечать точку ${i + 1}`}
                      onClick={() => {
                        change({ points: d.points.filter((_, n) => n !== i) });
                        setChosen(null);
                      }}
                    >
                      ×
                    </button>
                  )}
                </span>
              ))}
              <select
                aria-label="Добавить точку разметки"
                value=""
                onChange={(e) => addLandmark(Number(e.target.value))}
              >
                <option value="">+ точка разметки…</option>
                {marks.map((m, i) => (
                  <option key={i} value={i}>
                    {m.label}
                  </option>
                ))}
              </select>
            </div>
            <p className="muted small">
              {ptz
                ? 'Отметьте не меньше четырёх точек разметки, видных на этом кадре, лучше по всей длине поля: углы, центральную линию, отметки 6 и 10 м, штанги. Невидимую точку замените: добавьте другую и уберите лишнюю крестиком. Контур поля обработчик построит по точкам сам.'
                : 'Первые четыре точки — углы поля, по ним строится контур. Чем больше видимых точек разметки, тем точнее координаты.'}{' '}
              Кадр {frame.w} × {frame.h} px.
            </p>
          </>
        )}
        {/* Координаты числами, контур и объектив — техническая настройка: только для Админ+ и свёрнуто. */}
        {specialist && (
          <details className="camera-advanced">
            <summary>
              {ptz ? 'Для специалиста: координаты точек' : 'Для специалиста: координаты, контур и объектив'}
            </summary>
            {!frame && (
              <div className="form-grid">
                <Field label="Ширина кадра, px">
                  <input
                    type="number"
                    min={16}
                    max={16384}
                    value={d.frame_width}
                    onChange={(e) => change({ frame_width: e.target.value })}
                  />
                </Field>
                <Field label="Высота кадра, px">
                  <input
                    type="number"
                    min={16}
                    max={16384}
                    value={d.frame_height}
                    onChange={(e) => change({ frame_height: e.target.value })}
                  />
                </Field>
              </div>
            )}
            <p className="muted">
              Ось X идёт вдоль длины ({hall.pitch_length_m} м), Y — вдоль ширины ({hall.pitch_width_m} м); на кадре X
              направлен вправо, Y вниз.
            </p>
            {table}
            {!ptz && (
              <>
                <Field label="Контур поля на кадре, JSON">
                  <textarea
                    rows={3}
                    value={d.polygon}
                    onChange={(e) => change({ polygon: e.target.value })}
                    placeholder="[[x1,y1],[x2,y2],[x3,y3],[x4,y4]]"
                  />
                </Field>
                <p className="muted">Если оставить пустым, контур проходит через первые четыре точки.</p>
                <Field label="Калибровка объектива, JSON">
                  <textarea
                    rows={3}
                    value={d.calibration}
                    onChange={(e) => change({ calibration: e.target.value })}
                    placeholder={'{"K":[[fx,0,cx],[0,fy,cy],[0,0,1]],"dist":[k1,k2,p1,p2,k3]}'}
                  />
                </Field>
              </>
            )}
          </details>
        )}
      </fieldset>
      <ErrorBox error={error} />
      {(frame || specialist || d.attempted) && (
        <div className="team-save-bar">
          <button className="primary" disabled={busy || draft.corrupt}>
            {d.attempted ? 'Повторить сохранение профиля' : 'Сохранить профиль камеры'}
          </button>
        </div>
      )}
      <p className="muted">
        {ptz
          ? 'Повороты и зум оператора профиль учитывает сам. Новая версия нужна, если камеру переставили, сменились разрешение или графика трансляции.'
          : 'При перемещении камеры, зуме или смене разрешения создайте новую версию профиля.'}
      </p>
    </form>
  );
}
