import { useId, useState } from 'react';
import { PitchLines } from './PitchMap';
import './pitch.css';

// Стрелка уже в координатах карты (метры площадки, после разворота по направлению атаки).
export type PassArrow = {
  id: string;
  side: 'home' | 'away';
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  length: number;
  success: boolean | null;
  player: string | null;
  recipient: string | null;
  time: string | null;
};
const OUTCOME = (p: PassArrow) =>
  p.success === true ? 'точная' : p.success === false ? 'неточная' : 'исход неизвестен';
const metres = (v: number) => `${v.toLocaleString('ru-RU', { maximumFractionDigits: 1 })} м`;
const tone = (p: PassArrow) => (p.success === false ? 'failure' : p.success === null ? 'unknown' : p.side);

// Карта передач: стрелка от точки передачи к точке приёма, длина видна на поле; неточные — красным.
export function PassMap({
  passes,
  lengthM,
  widthM,
  homeName,
  awayName,
  note,
  compact = false,
}: {
  passes: PassArrow[];
  lengthM: number;
  widthM: number;
  homeName: string;
  awayName: string;
  note?: string;
  compact?: boolean;
}) {
  const ids = useId().replace(/:/g, '');
  const [selected, setSelected] = useState<string | null>(null);
  const current = passes.find((p) => p.id === selected) ?? null;
  if (!passes.length) return <p className="muted">Передач с отмеченными точками нет.</p>;
  // Выбранная стрелка рисуется последней, поверх остальных.
  const ordered = current ? [...passes.filter((p) => p.id !== current.id), current] : passes;
  return (
    <figure className={`pass-map pitch-map${compact ? ' compact' : ''}`}>
      <svg viewBox={`0 0 ${lengthM} ${widthM}`} role="img" aria-label={`Карта передач: ${passes.length}`}>
        <defs>
          {(['home', 'away', 'failure', 'unknown'] as const).map((t) => (
            <marker
              key={t}
              id={`${ids}-${t}`}
              className={`pass-head ${t}`}
              viewBox="0 0 10 10"
              refX="8"
              refY="5"
              markerWidth="4"
              markerHeight="4"
              orient="auto-start-reverse"
            >
              <path d="M0,0 L10,5 L0,10 z" />
            </marker>
          ))}
        </defs>
        <rect className="pitch-surface" x="0" y="0" width={lengthM} height={widthM} />
        <PitchLines lengthM={lengthM} widthM={widthM} />
        {ordered.map((p) => (
          <g
            key={p.id}
            className={`pass ${tone(p)}${p.id === selected ? ' selected' : ''}`}
            role="button"
            tabIndex={compact ? -1 : 0}
            aria-label={`${p.side === 'home' ? homeName : awayName}: ${p.player ?? 'игрок не определён'}, ${metres(p.length)}, ${OUTCOME(p)}`}
            onClick={() => setSelected(p.id === selected ? null : p.id)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                setSelected(p.id === selected ? null : p.id);
              }
            }}
          >
            <line className="pass-hit" x1={p.x1} y1={p.y1} x2={p.x2} y2={p.y2} />
            <line x1={p.x1} y1={p.y1} x2={p.x2} y2={p.y2} markerEnd={`url(#${ids}-${tone(p)})`} />
            <circle cx={p.x1} cy={p.y1} r={0.18} />
          </g>
        ))}
      </svg>
      <figcaption>
        {current ? (
          <span className="shot-detail">
            <i className={`side-dot ${current.side}`} aria-hidden="true" />
            {[
              current.time,
              `${current.player ?? (current.side === 'home' ? homeName : awayName)}${current.recipient ? ` → ${current.recipient}` : ''}`,
              metres(current.length),
              OUTCOME(current),
            ]
              .filter(Boolean)
              .join(' · ')}
          </span>
        ) : (
          !compact && <span>Нажмите на стрелку, чтобы увидеть передачу</span>
        )}
        <span className="shot-legend">
          <span>
            <i className="pass-key success" />
            точная
          </span>
          <span>
            <i className="pass-key failure" />
            неточная
          </span>
          {passes.some((p) => p.success === null) && (
            <span>
              <i className="pass-key unknown" />
              исход неизвестен
            </span>
          )}
        </span>
        {note && <span className="pass-note">{note}</span>}
      </figcaption>
    </figure>
  );
}
