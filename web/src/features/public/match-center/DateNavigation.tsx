import { CalendarDays, ChevronLeft, ChevronRight } from 'lucide-react';
import { ZONE } from '../../../components/match/MatchRow';
import { localDay, shiftDay } from '../../matches/timezone';

export { ZONE };
export const today = () => localDay(new Date().toISOString(), ZONE);
export function DateNavigation({ day, onDayChange }: { day: string; onDayChange: (d: string) => void }) {
  const label = new Intl.DateTimeFormat('ru-RU', { month: 'long', year: 'numeric' }).format(
    new Date(day + 'T12:00:00Z'),
  );
  return (
    <div className="center-dates">
      <div className="center-date-head">
        <h2>{label}</h2>
        <button onClick={() => onDayChange(today())}>Сегодня</button>
        <label className="center-date-picker">
          <CalendarDays />
          <span className="sr-only">Выбрать дату</span>
          <input
            type="date"
            aria-label="Дата матчей"
            value={day}
            onChange={(e) => {
              if (e.target.value) onDayChange(e.target.value);
            }}
          />
        </label>
      </div>
      <div className="center-date-strip">
        <button className="icon-button" aria-label="Предыдущий день" onClick={() => onDayChange(shiftDay(day, -1))}>
          <ChevronLeft />
        </button>
        <div className="center-date-days">
          {Array.from({ length: 7 }, (_, i) => shiftDay(day, i - 3)).map((d) => (
            <button key={d} aria-pressed={day === d} onClick={() => onDayChange(d)}>
              <span>{new Intl.DateTimeFormat('ru-RU', { weekday: 'short' }).format(new Date(d + 'T12:00:00Z'))}</span>
              <b>{Number(d.slice(-2))}</b>
            </button>
          ))}
        </div>
        <button className="icon-button" aria-label="Следующий день" onClick={() => onDayChange(shiftDay(day, 1))}>
          <ChevronRight />
        </button>
      </div>
    </div>
  );
}
// Полоса игровых дней турнира или команды: те же кнопки, что в календаре главной.
// Системный выбор даты — только по иконке календаря; выбранный так день тоже встаёт в полосу.
export function GameDays({
  days,
  day,
  onChange,
  allowAll = false,
}: {
  days: string[];
  day: string;
  onChange: (d: string | null) => void;
  allowAll?: boolean;
}) {
  const shown = [...new Set(day ? [...days, day] : days)].sort();
  const month = (d: string) =>
    new Intl.DateTimeFormat('ru-RU', { month: 'short' }).format(new Date(d + 'T12:00:00Z')).replace('.', '');
  return (
    <div className="game-days">
      <div className="center-date-days" role="group" aria-label="Дни матчей">
        {allowAll && (
          <button aria-pressed={!day} onClick={() => onChange(null)}>
            <span>все</span>
            <b>дни</b>
          </button>
        )}
        {shown.map((d) => (
          <button
            key={d}
            aria-pressed={day === d}
            aria-label={new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', weekday: 'long' }).format(
              new Date(d + 'T12:00:00Z'),
            )}
            onClick={() => onChange(d)}
          >
            <span>{new Intl.DateTimeFormat('ru-RU', { weekday: 'short' }).format(new Date(d + 'T12:00:00Z'))}</span>
            <b>{Number(d.slice(-2))}</b>
            <span>{month(d)}</span>
          </button>
        ))}
      </div>
      <label className="center-date-picker">
        <CalendarDays />
        <span className="sr-only">Выбрать дату</span>
        <input type="date" aria-label="Дата" value={day} onChange={(e) => onChange(e.target.value || null)} />
      </label>
    </div>
  );
}
