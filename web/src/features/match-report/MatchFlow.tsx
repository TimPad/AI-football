import { useState } from 'react';
import type { FlowMinute } from './flow';

const W = 640;
const H = 170;
const MID = 85;
const AMP = 62;
const GAP = 2; // пустые столбики на перерыв
const signed = (v: number) => `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(Math.round(v * 100))}`;

// График хода матча, как «Моментум» в FotMob: столбики по минутам, вверх — перевес хозяев, вниз — гостей.
export function MatchFlow({
  minutes,
  homeName,
  awayName,
}: {
  minutes: FlowMinute[];
  homeName: string;
  awayName: string;
}) {
  const [mode, setMode] = useState<'pressure' | 'passes'>('pressure');
  if (!minutes.length) return null;
  const halves = [...new Set(minutes.map((m) => m.half))].sort((a, b) => a - b);
  const slots: { m: FlowMinute; i: number }[] = [];
  const breaks: number[] = [];
  let i = 0;
  halves.forEach((h, k) => {
    if (k) {
      breaks.push(i + GAP / 2 - 0.5);
      i += GAP;
    }
    for (const m of minutes.filter((x) => x.half === h).sort((a, b) => a.minute - b.minute)) slots.push({ m, i: i++ });
  });
  const step = W / Math.max(i, 1);
  const bar = Math.max(1, step * 0.78);
  const x = (k: number) => k * step + (step - bar) / 2;
  const maxPressure = Math.max(0.05, ...slots.map(({ m }) => Math.abs(m.pressure ?? 0)));
  const maxPasses = Math.max(1, ...slots.map(({ m }) => Math.max(m.passes.home, m.passes.away)));
  const hasPasses = slots.some(({ m }) => m.passes.home + m.passes.away > 0);
  const hasGoals = slots.some(({ m }) => m.goals.length > 0);
  const label = (m: FlowMinute) => `${m.minute + 1}' · ${m.half}-й тайм`;
  return (
    <div className="match-flow">
      {hasPasses && (
        <div className="segmented" role="group" aria-label="Что показывать">
          {(
            [
              ['pressure', 'Давление'],
              ['passes', 'Передачи'],
            ] as const
          ).map(([id, text]) => (
            <button
              key={id}
              type="button"
              aria-pressed={mode === id}
              className={mode === id ? 'active' : ''}
              onClick={() => setMode(id)}
            >
              {text}
            </button>
          ))}
        </div>
      )}
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={`Ход матча по минутам: ${mode === 'pressure' ? 'давление' : 'передачи'}, минут ${slots.length}`}
      >
        <line className="flow-axis" x1="0" y1={MID} x2={W} y2={MID} />
        {breaks.map((b) => (
          <line key={b} className="flow-break" x1={b * step + step / 2} y1="10" x2={b * step + step / 2} y2={H - 10} />
        ))}
        {slots.map(({ m, i: k }) => {
          if (mode === 'pressure') {
            if (m.pressure == null) return null;
            const h = (Math.abs(m.pressure) / maxPressure) * AMP;
            const home = m.pressure >= 0;
            return (
              <rect
                key={`${m.half}:${m.minute}`}
                className={`flow-bar ${home ? 'home' : 'away'}`}
                x={x(k)}
                y={home ? MID - h : MID}
                width={bar}
                height={Math.max(h, 0.5)}
              >
                <title>{`${label(m)}: давление ${home ? homeName : awayName} ${signed(m.pressure)} п.п.`}</title>
              </rect>
            );
          }
          const up = (m.passes.home / maxPasses) * AMP;
          const down = (m.passes.away / maxPasses) * AMP;
          return (
            <g key={`${m.half}:${m.minute}`}>
              <title>{`${label(m)}: передачи ${homeName} ${m.passes.home}, ${awayName} ${m.passes.away}`}</title>
              {up > 0 && <rect className="flow-bar home" x={x(k)} y={MID - up} width={bar} height={up} />}
              {down > 0 && <rect className="flow-bar away" x={x(k)} y={MID} width={bar} height={down} />}
            </g>
          );
        })}
        {slots.flatMap(({ m, i: k }) =>
          m.goals.map((side, n) => (
            <circle
              key={`${m.half}:${m.minute}:${side}:${n}`}
              className={`flow-goal ${side}`}
              cx={x(k) + bar / 2}
              cy={side === 'home' ? 12 + n * 9 : H - 12 - n * 9}
              r="3.5"
            >
              <title>{`${label(m)}: гол ${side === 'home' ? homeName : awayName}`}</title>
            </circle>
          )),
        )}
      </svg>
      <div className="flow-legend small">
        <span>
          <i className="side-dot home" /> {homeName} — вверх
        </span>
        <span>
          <i className="side-dot away" /> {awayName} — вниз
        </span>
        <span className="muted">{halves.length > 1 ? 'пунктир — перерыв · ' : ''}минута — от начала тайма</span>
      </div>
      <p className="muted small">
        {mode === 'pressure'
          ? 'Давление — у чьих ворот шла игра: доля времени полевых игроков в чужой трети за минуту, по видео; столбик — разница команд.'
          : '≈ — передачи из видео по минутам: находится не каждая передача.'}
        {hasGoals ? ' Точки — голы из протокола.' : ''}
      </p>
    </div>
  );
}
