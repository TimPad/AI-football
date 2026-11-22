import { useId } from 'react';
import { PitchLines } from './PitchMap';
import './pitch.css';

export type NetworkDot = { id: string; x: number; y: number; touches: number; number: string | null; label: string };
export type NetworkLink = { from: string; to: string; count: number };

// Радиус узла по числу касаний (передачи и приёмы), метры поля: корень — чтобы площадь росла как число.
const radius = (touches: number) => Math.min(1.5, 0.45 + 0.11 * Math.sqrt(touches));
// Толщина связи по числу передач.
const width = (count: number, max: number) => 0.08 + (0.42 * count) / Math.max(1, max);
// Связи A→B и B→A — параллельными линиями: сдвиг поперёк направления.
const OFFSET_M = 0.28;

// Сеть передач команды: узлы — средние позиции игроков, стрелки — точные передачи от одного к другому.
export function PassNetwork({
  dots,
  links,
  lengthM,
  widthM,
  side,
  selected,
  onSelect,
  label,
}: {
  dots: NetworkDot[];
  links: NetworkLink[];
  lengthM: number;
  widthM: number;
  side: 'home' | 'away';
  selected: string | null;
  onSelect: (id: string | null) => void;
  label: string;
}) {
  const ids = useId().replace(/:/g, '');
  const at = new Map(dots.map((d) => [d.id, d]));
  const max = links.reduce((m, l) => Math.max(m, l.count), 0);
  const ordered = [...links].sort((a, b) => a.count - b.count);
  return (
    <figure className="pass-network pitch-map">
      <svg viewBox={`0 0 ${lengthM} ${widthM}`} role="img" aria-label={label}>
        <defs>
          <marker
            id={`${ids}-head`}
            className={`network-head ${side}`}
            viewBox="0 0 10 10"
            refX="9"
            refY="5"
            markerWidth="3"
            markerHeight="3"
            orient="auto"
          >
            <path d="M0,0 L10,5 L0,10 z" />
          </marker>
        </defs>
        <rect className="pitch-surface" x="0" y="0" width={lengthM} height={widthM} />
        <PitchLines lengthM={lengthM} widthM={widthM} />
        {ordered.map((l) => {
          const a = at.get(l.from),
            b = at.get(l.to);
          if (!a || !b) return null;
          const dx = b.x - a.x,
            dy = b.y - a.y,
            d = Math.hypot(dx, dy);
          if (d < 1e-6) return null;
          const ux = dx / d,
            uy = dy / d;
          // Сдвиг вправо от направления и обрезка у краёв узлов.
          const ox = -uy * OFFSET_M,
            oy = ux * OFFSET_M;
          const ra = radius(a.touches) + 0.1,
            rb = radius(b.touches) + 0.25;
          if (d <= ra + rb) return null;
          const faded = selected !== null && l.from !== selected && l.to !== selected;
          return (
            <line
              key={`${l.from}>${l.to}`}
              className={`network-link ${side}${faded ? ' faded' : ''}`}
              x1={a.x + ux * ra + ox}
              y1={a.y + uy * ra + oy}
              x2={b.x - ux * rb + ox}
              y2={b.y - uy * rb + oy}
              strokeWidth={width(l.count, max)}
              markerEnd={`url(#${ids}-head)`}
            >
              <title>{`${a.label} → ${b.label}: ${l.count}`}</title>
            </line>
          );
        })}
        {dots.map((d) => {
          const r = radius(d.touches);
          return (
            <g
              key={d.id}
              className={`network-node ${side}${d.id === selected ? ' selected' : ''}${selected && d.id !== selected ? ' faded' : ''}`}
              role="button"
              tabIndex={0}
              aria-pressed={d.id === selected}
              aria-label={`${d.label}: касаний ${d.touches}`}
              onClick={() => onSelect(d.id === selected ? null : d.id)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  onSelect(d.id === selected ? null : d.id);
                }
              }}
            >
              <circle cx={d.x} cy={d.y} r={r} />
              {d.number && (
                <text className="network-number" x={d.x} y={d.y} fontSize={Math.max(0.55, r * 0.9)}>
                  {d.number}
                </text>
              )}
              <text className="network-label" x={d.x} y={d.y + r + 0.75} fontSize={0.7}>
                {d.label}
              </text>
            </g>
          );
        })}
      </svg>
    </figure>
  );
}
