# Подсказки игрока для оставшихся фрагментов — план этапа 1

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** режим «Подсказки» на вкладке «Проверка»: каждому неназначенному кандидату команды — лучший по цвету формы
игрок, уверенные подсказки отмечены сразу, человек назначает их группой.

**Architecture:** только кабинет (React). Чистая функция `hintsFor` в `suggestions.ts` строится на тех же кирпичах,
что и «Подбор» (`candidatesOf`, `lookIndex`, `meanLook`, `cosine`, `clash`). Компонент `SuggestionPicker` меняет
назначения черновика через `onChange`, как другие режимы; `IdentityReview` добавляет кнопку режима. Сервер,
обработчик, пакет и база не меняются. Спецификация — `docs/superpowers/specs/2026-11-26-identity-suggestions-design.md`.

**Tech Stack:** React 18 + TypeScript, Vitest + Testing Library, Playwright, Biome.

---

## Где работать

Сайт организатора работает из этой рабочей копии (`laughing-pike`, ветка `local/serve-hse` = `main` + PR #45 +
спецификация). Ветку не переключать: под работающим сайтом пропадёт PR #45. Работать здесь, коммитить в
`local/serve-hse`; в задаче 8 изменения переносятся на ветку от `main` без checkout. `web/dist` не пересобирать до
задачи 8 (сайт читает её).

Команды фронтенда — из `web/`: `npx vitest run <файлы>`, `npx tsc -b`, `npm run lint`, `npx biome format --write <файлы>`.
`<scratchpad>` в командах — временная папка вне репозитория (scratchpad сессии): выгрузки и сборки для E2E.

## Файлы

| Файл | Что |
|---|---|
| `web/src/features/analysis/candidates.ts` | + `clock` (формат м:сс), переезжает из `SimilarPicker.tsx` |
| `web/src/features/analysis/CandidateThumb.tsx` | новый: миниатюра кандидата (выносится из `SimilarPicker.tsx`) |
| `web/src/features/analysis/SimilarPicker.tsx` | использует `CandidateThumb` и `clock` |
| `web/src/features/analysis/suggestions.ts` | новый: `hintsFor`, `groupByPlayer`, `initialTicks`, `rejectKey`, `CONFIDENT_MARGIN` |
| `web/src/features/analysis/suggestions.test.ts` | новый: модульные тесты расчёта |
| `web/src/features/analysis/SuggestionPicker.tsx` | новый: экран режима |
| `web/src/features/analysis/SuggestionPicker.test.tsx` | новый: тесты экрана и режима во вкладке |
| `web/src/features/analysis/IdentityReview.tsx` | кнопка «Подсказки · N», ветка режима |
| `web/src/features/analysis/review.css` | стили групп и метки уверенности |
| `web/e2e/similar-picker.spec.ts` | второй фрагмент назначается из «Подсказок» |
| `README.md`, `docs/README.md` | абзац о режиме и ссылка на спецификацию и план |

---

### Task 1: `clock` и `CandidateThumb` — общие для «Подбора» и «Подсказок»

**Files:**
- Modify: `web/src/features/analysis/candidates.ts` (после `SHORT_S`)
- Create: `web/src/features/analysis/CandidateThumb.tsx`
- Modify: `web/src/features/analysis/SimilarPicker.tsx:1-67,133,167`
- Test: `web/src/features/analysis/similar.test.tsx` (существующий, без изменений)

- [ ] **Step 1: Добавить `clock` в `candidates.ts`** — сразу после строки `export const SHORT_S = 10;`:

```ts
// Время записи «м:сс» для подписей кандидатов.
export const clock = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
```

- [ ] **Step 2: Создать `CandidateThumb.tsx`**

```tsx
import type { AnalysisRun } from '../../api/domain';
import type { Candidate } from './candidates';
import type { LookIndex } from './similar';

// Кадр кандидата — миниатюра его самого длинного фрагмента, у которого кадр есть.
export function CandidateThumb({
  run,
  index,
  candidate,
  className,
}: {
  run: AnalysisRun;
  index: LookIndex;
  candidate: Candidate;
  className: string;
}) {
  const seconds = (id: number) => index.tracks.get(id)?.intervals.reduce((s, [a, b]) => s + b - a, 0) ?? 0;
  const id = candidate.trackIds
    .filter((t) => index.tracks.get(t)?.thumb)
    .sort((a, b) => seconds(b) - seconds(a))[0];
  return id != null ? (
    <img
      className={`track-thumb ${className}`}
      src={`/api/v1/matches/${run.match_id}/analysis/runs/${run.id}/thumbs/${id}`}
      alt={`Фрагмент ${id}`}
    />
  ) : (
    <span className={`thumb-missing ${className}`}>Кадр недоступен</span>
  );
}
```

- [ ] **Step 3: Перевести `SimilarPicker.tsx` на общие части.** Заменить импорты и убрать локальные `clock`, `seconds`,
  `thumb`:

```tsx
import { useMemo, useState } from 'react';
import type { AnalysisAssignment, AnalysisRun } from '../../api/domain';
import { CandidateThumb } from './CandidateThumb';
import { assignGroup, baseGroups, candidatesOf, clock, decisionOf } from './candidates';
import { assignedShare, clash, lookIndex, suggest } from './similar';

const STEP = 12;
type Mark = 'yes' | 'no';
```

Удалить строку `const clock = ...` (прежняя строка 7), строку `const seconds = (id: number) => ...` и функцию `thumb`
целиком (прежние строки 54–67). Вызовы заменить:

```tsx
                {thumb(c, 'small')}
```
→
```tsx
                <CandidateThumb run={run} index={index} candidate={c} className="small" />
```
и
```tsx
                {thumb(c, 'similar')}
```
→
```tsx
                <CandidateThumb run={run} index={index} candidate={c} className="similar" />
```

Тип `Candidate` из импорта `./candidates` в `SimilarPicker.tsx` больше не нужен — убрать, если Biome укажет на него.

- [ ] **Step 4: Проверить, что «Подбор» не изменился**

Run: `cd web && npx vitest run src/features/analysis && npx tsc -b`
Expected: все тесты `src/features/analysis` проходят (как до изменения), `tsc` без ошибок.

- [ ] **Step 5: Commit**

```bash
npx biome format --write src/features/analysis/candidates.ts src/features/analysis/CandidateThumb.tsx src/features/analysis/SimilarPicker.tsx
git add web/src/features/analysis/candidates.ts web/src/features/analysis/CandidateThumb.tsx web/src/features/analysis/SimilarPicker.tsx
git commit -m "refactor(review): share the candidate thumbnail and clock"
```

---

### Task 2: расчёт подсказок `suggestions.ts`

**Files:**
- Create: `web/src/features/analysis/suggestions.ts`
- Test: `web/src/features/analysis/suggestions.test.ts`

Данные теста: «красная» и «синяя» форма как в `similar.test.tsx`; косинус красного и синего ≈ 0,19.

- [ ] **Step 1: Написать падающие тесты** — `web/src/features/analysis/suggestions.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import type { AnalysisAssignment, AnalysisRun } from '../../api/domain';
import { baseGroups, candidatesOf } from './candidates';
import { lookIndex } from './similar';
import { CONFIDENT_MARGIN, groupByPlayer, hintsFor, initialTicks, rejectKey } from './suggestions';

const look = (hot: number) =>
  btoa(String.fromCharCode(...Array.from({ length: 156 }, (_, i) => (i === hot ? 255 : 8))));
const RED = look(0);
const BLUE = look(40);
const track = (id: number, team: string, from: number, to: number, appearance: string | null) => ({
  track_id: id,
  team,
  role: 'player',
  intervals: [[from, to]],
  thumb: `thumbs/${id}.jpg`,
  has_metrics: true,
  appearance,
});
// A: 1 красный (0–40) и 4 синий (100–160) назначены; открыты 2 красный (50–90), 3 синий (0–30, виден вместе с 1),
// 5 синий (200–230), 6 без признака; 8 красный (300–340), 9 и 10 красные, видны одновременно (400–440, 410–450).
const run = {
  id: 'run',
  match_id: 'match',
  context: {
    teams: { home: { id: 't1', name: 'Север' }, away: { id: 't2', name: 'Юг' } },
    rosters: [
      { player_id: 'p1', side: 'home', display_name: 'Север · игрок 1', shirt_number: '7' },
      { player_id: 'p2', side: 'home', display_name: 'Север · игрок 2', shirt_number: null },
      { player_id: 'p3', side: 'home', display_name: 'Север · игрок 3', shirt_number: null },
      { player_id: 'p9', side: 'away', display_name: 'Юг · игрок 1', shirt_number: null },
    ],
  },
  side_map: { A: 'home', B: 'away' },
  assignments: [],
  tracks: [
    track(1, 'A', 0, 40, RED),
    track(2, 'A', 50, 90, RED),
    track(3, 'A', 0, 30, BLUE),
    track(4, 'A', 100, 160, BLUE),
    track(5, 'A', 200, 230, BLUE),
    track(6, 'A', 170, 175, null),
    track(7, 'B', 0, 150, RED),
    track(8, 'A', 300, 340, RED),
    track(9, 'A', 400, 440, RED),
    track(10, 'A', 410, 450, RED),
  ],
  groups: [],
} as unknown as AnalysisRun;
const index = lookIndex(run);
const candidates = candidatesOf(run, baseGroups(run));
const home = ['p1', 'p2', 'p3'];
const base: AnalysisAssignment[] = [
  { track_id: 1, player_id: 'p1' },
  { track_id: 4, player_id: 'p2' },
];
const byKey = (h: ReturnType<typeof hintsFor>) => Object.fromEntries(h.hints.map((x) => [x.candidate.key, x]));
const cand = (key: string) => candidates.filter((c) => c.key === key)[0];

describe('hints for leftover fragments', () => {
  it('gives each open candidate the most similar player who is not on court at the same time', () => {
    const result = hintsFor(index, candidates, 'A', home, base, new Set());
    const h = byKey(result);
    expect(h['2'].playerId).toBe('p1');
    expect(h['5'].playerId).toBe('p2');
    // 3 виден вместе с фрагментом 1 игрока p1: остаётся только p2, отрыв — от нуля.
    expect(h['3'].playerId).toBe('p2');
    expect(h['3'].margin).toBeCloseTo(h['3'].score, 6);
    expect(result.players).toBe(2);
    expect(Object.keys(h)).not.toContain('1');
    expect(Object.keys(h)).not.toContain('7');
  });

  it('lists candidates without a look or without a fitting player separately', () => {
    const plain = hintsFor(index, candidates, 'A', home, base, new Set());
    expect(plain.unhinted).toEqual([{ candidate: cand('6'), reason: 'no_look' }]);
    const rejected = hintsFor(index, candidates, 'A', home, base, new Set([rejectKey('p2', cand('3'))]));
    expect(rejected.unhinted).toContainEqual({ candidate: cand('3'), reason: 'no_player' });
  });

  it('moves a rejected candidate to the next most similar player', () => {
    const h = byKey(hintsFor(index, candidates, 'A', home, base, new Set([rejectKey('p1', cand('2'))])));
    expect(h['2'].playerId).toBe('p2');
  });

  it('never suggests players without fragments and follows the current assignments', () => {
    const only = byKey(hintsFor(index, candidates, 'A', home, [{ track_id: 1, player_id: 'p1' }], new Set()));
    expect(only['5'].playerId).toBe('p1');
    expect(Object.values(only).some((x) => x.playerId === 'p3')).toBe(false);
    expect(byKey(hintsFor(index, candidates, 'A', home, base, new Set()))['5'].playerId).toBe('p2');
    expect(hintsFor(index, candidates, 'A', home, [], new Set()).players).toBe(0);
  });

  it('calls a hint confident only when the best player leads by the margin', () => {
    const twins = [...base, { track_id: 8, player_id: 'p3' }];
    const result = hintsFor(index, candidates, 'A', home, twins, new Set());
    const h = byKey(result);
    // p1 и p3 одинаково красные: у красного 2 отрыв 0.
    expect(h['2'].margin).toBeCloseTo(0, 6);
    expect(h['2'].confident).toBe(false);
    expect(h['5'].confident).toBe(true);
    for (const x of result.hints) expect(x.confident).toBe(x.margin >= CONFIDENT_MARGIN);
  });

  it('pre-ticks only one of two confident candidates seen at the same time', () => {
    const result = hintsFor(index, candidates, 'A', home, base, new Set());
    const [group] = groupByPlayer(result.hints).filter((g) => g.playerId === 'p1');
    expect(group.hints.map((x) => x.candidate.key).sort()).toEqual(['10', '2', '8', '9']);
    const ticks = initialTicks(index, group.hints);
    expect(['9', '10'].filter((k) => ticks.has(k))).toHaveLength(1);
    expect(ticks.has('2') && ticks.has('8')).toBe(true);
  });

  it('orders groups by the number of hints', () => {
    const groups = groupByPlayer(hintsFor(index, candidates, 'A', home, base, new Set()).hints);
    expect(groups.map((g) => [g.playerId, g.hints.length])).toEqual([
      ['p1', 4],
      ['p2', 2],
    ]);
  });
});
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `cd web && npx vitest run src/features/analysis/suggestions.test.ts`
Expected: FAIL — `Failed to resolve import "./suggestions"`.

- [ ] **Step 3: Написать `suggestions.ts`**

```ts
import type { AnalysisAssignment } from '../../api/domain';
import { type Candidate, decisionOf } from './candidates';
import { clash, cosine, type Look, type LookIndex, meanLook } from './similar';

// Подсказки для оставшихся фрагментов: каждому неназначенному кандидату команды — самый похожий по цвету формы
// игрок из тех, у кого уже есть фрагменты и кто не виден одновременно с кандидатом. Замер 26.11.2026 на матче
// ВШЭ Ю — JWH (docs/superpowers/specs/2026-11-26-identity-suggestions-design.md): верно 83%, при отрыве лучшего
// игрока от второго ≥ 0,03 — 93%. Решает человек: подсказка только отмечает и упорядочивает.

export const CONFIDENT_MARGIN = 0.03;

export type Hint = { candidate: Candidate; playerId: string; score: number; margin: number; confident: boolean };
export type Unhinted = { candidate: Candidate; reason: 'no_look' | 'no_player' };
export type Hints = { hints: Hint[]; unhinted: Unhinted[]; players: number };

// Отклонение «Не он» — пара игрок и кандидат.
export const rejectKey = (playerId: string, candidate: Candidate) => `${playerId}|${candidate.key}`;

export function hintsFor(
  index: LookIndex,
  candidates: Candidate[],
  team: 'A' | 'B',
  playerIds: string[],
  assignments: AnalysisAssignment[],
  rejected: Set<string>,
): Hints {
  // Игроки с фрагментами и признаком цвета: по ним строится средний признак.
  const players: { id: string; own: number[]; mean: Look }[] = [];
  for (const id of playerIds) {
    const own = assignments.filter((a) => a.player_id === id).map((a) => a.track_id);
    const mean = own.length ? meanLook(index, own) : null;
    if (mean) players.push({ id, own, mean });
  }
  const hints: Hint[] = [];
  const unhinted: Unhinted[] = [];
  if (!players.length) return { hints, unhinted, players: 0 };
  for (const candidate of candidates) {
    if (candidate.team !== team || decisionOf(assignments, candidate.trackIds).kind !== 'none') continue;
    const look = meanLook(index, candidate.trackIds);
    if (!look) {
      unhinted.push({ candidate, reason: 'no_look' });
      continue;
    }
    const scored = players
      .filter((p) => !rejected.has(rejectKey(p.id, candidate)) && !clash(index, p.own, candidate.trackIds))
      .map((p) => ({ id: p.id, score: cosine(p.mean, look) }))
      .sort((a, b) => b.score - a.score);
    if (!scored.length) {
      unhinted.push({ candidate, reason: 'no_player' });
      continue;
    }
    const margin = scored[0].score - (scored[1]?.score ?? 0);
    hints.push({
      candidate,
      playerId: scored[0].id,
      score: scored[0].score,
      margin,
      confident: margin >= CONFIDENT_MARGIN,
    });
  }
  return { hints, unhinted, players: players.length };
}

// Группы подсказок по игроку: больше подсказок — выше; внутри — по убыванию похожести.
export function groupByPlayer(hints: Hint[]): { playerId: string; hints: Hint[] }[] {
  const groups = new Map<string, Hint[]>();
  for (const h of hints) groups.set(h.playerId, [...(groups.get(h.playerId) ?? []), h]);
  return [...groups.entries()]
    .map(([playerId, list]) => ({ playerId, hints: [...list].sort((a, b) => b.score - a.score) }))
    .sort((a, b) => b.hints.length - a.hints.length || a.playerId.localeCompare(b.playerId));
}

// Отмеченные сразу: уверенные подсказки игрока по убыванию похожести, кроме видных одновременно с уже отмеченными.
export function initialTicks(index: LookIndex, hints: Hint[]): Set<string> {
  const keys = new Set<string>();
  const ticked: number[] = [];
  for (const h of [...hints].sort((a, b) => b.score - a.score)) {
    if (!h.confident || (ticked.length && clash(index, ticked, h.candidate.trackIds))) continue;
    keys.add(h.candidate.key);
    ticked.push(...h.candidate.trackIds);
  }
  return keys;
}
```

- [ ] **Step 4: Убедиться, что тесты проходят**

Run: `cd web && npx vitest run src/features/analysis/suggestions.test.ts`
Expected: PASS, 7 тестов.

- [ ] **Step 5: Commit**

```bash
npx biome format --write src/features/analysis/suggestions.ts src/features/analysis/suggestions.test.ts
git add web/src/features/analysis/suggestions.ts web/src/features/analysis/suggestions.test.ts
git commit -m "feat(review): best-matching player for each leftover fragment"
```

---

### Task 3: экран `SuggestionPicker`

**Files:**
- Create: `web/src/features/analysis/SuggestionPicker.tsx`
- Modify: `web/src/features/analysis/review.css` (в конец)
- Test: `web/src/features/analysis/SuggestionPicker.test.tsx`

- [ ] **Step 1: Написать падающие тесты** — `web/src/features/analysis/SuggestionPicker.test.tsx`
  (данные — те же, что в задаче 2):

```tsx
import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { AnalysisAssignment, AnalysisRun } from '../../api/domain';
import { IdentityReview } from './IdentityReview';
import { SuggestionPicker } from './SuggestionPicker';

const look = (hot: number) =>
  btoa(String.fromCharCode(...Array.from({ length: 156 }, (_, i) => (i === hot ? 255 : 8))));
const RED = look(0);
const BLUE = look(40);
const track = (id: number, team: string, from: number, to: number, appearance: string | null) => ({
  track_id: id,
  team,
  role: 'player',
  intervals: [[from, to]],
  thumb: `thumbs/${id}.jpg`,
  has_metrics: true,
  appearance,
});
const base: AnalysisAssignment[] = [
  { track_id: 1, player_id: 'p1' },
  { track_id: 4, player_id: 'p2' },
];
const run = {
  job_id: 'job',
  id: 'run',
  match_id: 'match',
  revision: 0,
  status: 'review',
  context: {
    teams: { home: { id: 't1', name: 'Север' }, away: { id: 't2', name: 'Юг' } },
    rosters: [
      { player_id: 'p1', side: 'home', display_name: 'Север · игрок 1', shirt_number: '7' },
      { player_id: 'p2', side: 'home', display_name: 'Север · игрок 2', shirt_number: null },
      { player_id: 'p9', side: 'away', display_name: 'Юг · игрок 1', shirt_number: null },
    ],
  },
  side_map: { A: 'home', B: 'away' },
  assignments: base,
  tracks: [
    track(1, 'A', 0, 40, RED),
    track(2, 'A', 50, 90, RED),
    track(3, 'A', 0, 30, BLUE),
    track(4, 'A', 100, 160, BLUE),
    track(5, 'A', 200, 230, BLUE),
    track(6, 'A', 170, 175, null),
    track(7, 'B', 0, 150, RED),
  ],
  groups: [],
} as unknown as AnalysisRun;
const sideMap = { A: 'home', B: 'away' } as AnalysisRun['side_map'];
const show = (assignments = base, onChange = vi.fn(), onOpenSimilar = vi.fn()) =>
  render(
    <SuggestionPicker
      run={run}
      assignments={assignments}
      sideMap={sideMap}
      disabled={false}
      onChange={onChange}
      onOpenSimilar={onOpenSimilar}
    />,
  );
const group = (name: string) => screen.getByRole('region', { name: `Подсказки игроку ${name}` });
const card = (g: HTMLElement, span: string) => within(g).getByRole('listitem', { name: `Фрагмент ${span}` });
beforeEach(() => localStorage.clear());

describe('suggestion picker', () => {
  it('groups hints by player, ticks confident ones and assigns the ticked ones', () => {
    const onChange = vi.fn();
    show(base, onChange);
    const p2 = group('Север · игрок 2');
    expect(within(p2).getByRole('heading')).toHaveTextContent('подсказок: 2');
    const early = card(p2, '0:00–0:30');
    expect(early).toHaveTextContent('уверенно');
    expect(within(early).getByRole('checkbox', { name: 'Назначить' })).toBeChecked();
    fireEvent.click(within(card(p2, '3:20–3:50')).getByRole('checkbox', { name: 'Назначить' }));
    fireEvent.click(within(p2).getByRole('button', { name: 'Назначить отмеченных (1)' }));
    const next = onChange.mock.calls[0][0] as AnalysisAssignment[];
    expect(next).toContainEqual({ track_id: 3, player_id: 'p2' });
    expect(next.some((a) => a.track_id === 5)).toBe(false);
    expect(screen.getByRole('status', { name: 'Без подсказки' })).toHaveTextContent(
      'Без подсказки: 1 — нет признака цвета: 1',
    );
  });

  it('gives a rejected hint to the next player', () => {
    show();
    fireEvent.click(within(card(group('7 · Север · игрок 1'), '0:50–1:30')).getByRole('button', { name: 'Не он' }));
    expect(screen.queryByRole('region', { name: 'Подсказки игроку 7 · Север · игрок 1' })).toBeNull();
    expect(card(group('Север · игрок 2'), '0:50–1:30')).toBeInTheDocument();
  });

  it('asks to start in the similar picker when no player has fragments', () => {
    const onOpenSimilar = vi.fn();
    show([], vi.fn(), onOpenSimilar);
    expect(screen.getByText(/Сначала назначьте каждому игроку хотя бы один фрагмент/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Открыть «Подбор»' }));
    expect(onOpenSimilar).toHaveBeenCalled();
  });

  it('is a mode of the review tab with the number of hints', () => {
    render(
      <MemoryRouter>
        <IdentityReview run={run} actorId="admin" editable onSave={vi.fn()} />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Подсказки · 3' }));
    const p2 = group('Север · игрок 2');
    fireEvent.click(within(p2).getByRole('button', { name: 'Назначить отмеченных (2)' }));
    expect(screen.getByText(/назначений в черновике: 4/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Подсказки · 1' })).toBeInTheDocument();
  });
});
```

Ожидания по данным: у команды A открыты 2 (красный → p1), 3 (синий, только p2), 5 (синий → p2), 6 без признака.
У p2 две уверенные подсказки 3 (0:00–0:30) и 5 (3:20–3:50), они не видны одновременно — обе отмечены. «Подсказки · 3»:
A — 3, у B игроков с фрагментами нет. После назначения 3 и 5 игроку p2 в черновике 4 назначения, остаётся подсказка 2.

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `cd web && npx vitest run src/features/analysis/SuggestionPicker.test.tsx`
Expected: FAIL — `Failed to resolve import "./SuggestionPicker"`.

- [ ] **Step 3: Написать `SuggestionPicker.tsx`**

```tsx
import { useMemo, useState } from 'react';
import type { AnalysisAssignment, AnalysisRun } from '../../api/domain';
import { CandidateThumb } from './CandidateThumb';
import { assignGroup, baseGroups, candidatesOf, clock } from './candidates';
import { clash, lookIndex } from './similar';
import { groupByPlayer, type Hint, hintsFor, initialTicks, rejectKey } from './suggestions';

const REASONS = { no_look: 'нет признака цвета', no_player: 'ни один игрок не подходит по времени' } as const;

// Подсказки: каждому неназначенному кандидату команды — лучший по цвету формы игрок из уже размеченных; уверенные
// отмечены сразу. Назначает человек: снимает отметки с ошибок, «Не он» отдаёт кандидата следующему игроку.
// Как и в других режимах, меняются назначения черновика; на сервер их отправляет «Сохранить сопоставление».
export function SuggestionPicker({
  run,
  assignments,
  sideMap,
  disabled,
  onChange,
  onOpenSimilar,
}: {
  run: AnalysisRun;
  assignments: AnalysisAssignment[];
  sideMap: AnalysisRun['side_map'];
  disabled: boolean;
  onChange: (next: AnalysisAssignment[]) => void;
  onOpenSimilar: () => void;
}) {
  const index = useMemo(() => lookIndex(run), [run]);
  const candidates = useMemo(() => candidatesOf(run, baseGroups(run)), [run]);
  const [team, setTeam] = useState<'A' | 'B'>('A');
  const [rejected, setRejected] = useState<Set<string>>(() => new Set());
  const [marks, setMarks] = useState<Record<string, boolean>>({});
  const roster = run.context.rosters.filter((p) => p.side === sideMap[team]);
  const result = hintsFor(
    index,
    candidates,
    team,
    roster.map((p) => p.player_id),
    assignments,
    rejected,
  );
  const groups = groupByPlayer(result.hints);
  const name = (id: string) => {
    const p = roster.find((x) => x.player_id === id);
    return p ? `${p.shirt_number ? `${p.shirt_number} · ` : ''}${p.display_name}` : id;
  };
  const forget = (keys: string[]) =>
    setMarks((m) => {
      const next = { ...m };
      for (const k of keys) delete next[k];
      return next;
    });
  function reject(h: Hint) {
    setRejected((r) => new Set(r).add(rejectKey(h.playerId, h.candidate)));
    forget([h.candidate.key]);
  }
  const reasons = Object.entries(
    result.unhinted.reduce<Record<string, number>>((n, u) => ({ ...n, [u.reason]: (n[u.reason] ?? 0) + 1 }), {}),
  )
    .map(([reason, n]) => `${REASONS[reason as keyof typeof REASONS]}: ${n}`)
    .join('; ');
  return (
    <section className="suggestion-picker" aria-label="Подсказки игроков">
      <div className="similar-head">
        <div className="segmented review-mode" role="group" aria-label="Команда">
          {(['A', 'B'] as const).map((t) => (
            <button key={t} aria-pressed={team === t} onClick={() => setTeam(t)}>
              {run.context.teams[sideMap[t]].name}
            </button>
          ))}
        </div>
      </div>
      {!result.players ? (
        <div className="row wrap">
          <p className="muted">
            Сначала назначьте каждому игроку хотя бы один фрагмент в «Подборе» — подсказки строятся по ним.
          </p>
          <button onClick={onOpenSimilar}>Открыть «Подбор»</button>
        </div>
      ) : groups.length ? (
        groups.map((g) => {
          const defaults = initialTicks(index, g.hints);
          const ticked = (h: Hint) => marks[h.candidate.key] ?? defaults.has(h.candidate.key);
          const chosen = g.hints.filter(ticked);
          const chosenIds = chosen.flatMap((h) => h.candidate.trackIds);
          function assign() {
            let next = assignments;
            for (const h of chosen) next = assignGroup(next, h.candidate.trackIds, g.playerId);
            forget(g.hints.map((h) => h.candidate.key));
            onChange(next);
          }
          return (
            <section className="hint-group" key={g.playerId} aria-label={`Подсказки игроку ${name(g.playerId)}`}>
              <h3>
                {name(g.playerId)} — подсказок: {g.hints.length}
              </h3>
              <ul className="similar-grid">
                {g.hints.map((h) => {
                  const c = h.candidate;
                  const on = ticked(h);
                  const blocked = !on && chosenIds.length > 0 && clash(index, chosenIds, c.trackIds);
                  return (
                    <li
                      key={c.key}
                      className={`similar-card${on ? ' yes' : ''}`}
                      aria-label={`Фрагмент ${clock(c.span[0])}–${clock(c.span[1])}`}
                    >
                      <CandidateThumb run={run} index={index} candidate={c} className="similar" />
                      <span className="small num">
                        похож {h.score.toFixed(2)} · {clock(c.seconds)}
                      </span>
                      <span className="muted small num">
                        {clock(c.span[0])}–{clock(c.span[1])}
                        {c.goalkeeper ? ' · вратарь' : ''}
                      </span>
                      <span className={`hint-confidence ${h.confident ? 'sure' : 'unsure'}`}>
                        {h.confident ? 'уверенно' : 'сомнительно'}
                      </span>
                      <div className="similar-actions">
                        <label className="check" title={blocked ? 'Виден одновременно с уже отмеченным' : undefined}>
                          <input
                            type="checkbox"
                            checked={on}
                            disabled={disabled || blocked}
                            onChange={() => setMarks((m) => ({ ...m, [c.key]: !on }))}
                          />
                          Назначить
                        </label>
                        <button disabled={disabled} onClick={() => reject(h)}>
                          Не он
                        </button>
                      </div>
                    </li>
                  );
                })}
              </ul>
              <div className="row wrap">
                <button className="primary" disabled={disabled || !chosen.length} onClick={assign}>
                  Назначить отмеченных ({chosen.length})
                </button>
              </div>
            </section>
          );
        })
      ) : (
        <p className="muted">Подсказок нет: все фрагменты команды с признаком цвета назначены.</p>
      )}
      {result.unhinted.length > 0 && (
        <p className="muted small" role="status" aria-label="Без подсказки">
          Без подсказки: {result.unhinted.length} — {reasons}. Их назначают в «По фрагментам».
        </p>
      )}
    </section>
  );
}
```

- [ ] **Step 4: Добавить стили** — в конец `web/src/features/analysis/review.css`:

```css
.suggestion-picker {
  display: grid;
  gap: 16px;
}
.hint-group {
  display: grid;
  gap: 8px;
}
.hint-group h3 {
  margin: 0;
  font-size: 15px;
}
.hint-confidence {
  padding: 0 6px;
  border-radius: 999px;
  font-size: 12px;
}
.hint-confidence.sure {
  background: var(--ok-soft);
}
.hint-confidence.unsure {
  background: var(--warn-soft);
}
```

- [ ] **Step 5: Прогнать тесты экрана** (последний тест — режим во вкладке — упадёт до задачи 4)

Run: `cd web && npx vitest run src/features/analysis/SuggestionPicker.test.tsx -t "suggestion picker" `
Expected: 3 теста экрана проходят; «is a mode of the review tab with the number of hints» падает — кнопки режима
ещё нет.

- [ ] **Step 6: Commit**

```bash
npx biome format --write src/features/analysis/SuggestionPicker.tsx src/features/analysis/SuggestionPicker.test.tsx src/features/analysis/review.css
git add web/src/features/analysis/SuggestionPicker.tsx web/src/features/analysis/SuggestionPicker.test.tsx web/src/features/analysis/review.css
git commit -m "feat(review): suggestion picker grouped by player"
```

---

### Task 4: режим «Подсказки · N» во вкладке «Проверка»

**Files:**
- Modify: `web/src/features/analysis/IdentityReview.tsx` (импорты, состояние режима, кнопки режимов, ветка
  отрисовки)
- Test: `web/src/features/analysis/SuggestionPicker.test.tsx` (тест «is a mode of the review tab…» из задачи 3)

- [ ] **Step 1: Импорты.** В `IdentityReview.tsx` заменить
  `import { useEffect, useState } from 'react';` на `import { useEffect, useMemo, useState } from 'react';`,
  `import { baseGroups, dropConflicts, identityConflicts } from './candidates';` на
  `import { baseGroups, candidatesOf, dropConflicts, identityConflicts } from './candidates';` и добавить:

```tsx
import { lookIndex } from './similar';
import { SuggestionPicker } from './SuggestionPicker';
import { hintsFor } from './suggestions';
```

- [ ] **Step 2: Тип режима и число подсказок.** Заменить объявление режима

```tsx
  const [mode, setMode] = useState<'similar' | 'players' | 'tracks'>(
```
на
```tsx
  const [mode, setMode] = useState<'similar' | 'hints' | 'players' | 'tracks'>(
```

и сразу после этого `useState(...)` (после строки `);`, закрывающей его) добавить:

```tsx
  // Число подсказок для кнопки режима: обе команды, без отклонений (их держит сам режим).
  const lookIdx = useMemo(() => lookIndex(run), [run]);
  const allCandidates = useMemo(() => candidatesOf(run, baseGroups(run)), [run]);
  const sideMap = draft.value.side_map;
  const draftAssignments = draft.value.assignments;
  const hintCount = useMemo(
    () =>
      looks
        ? (['A', 'B'] as const).reduce(
            (n, t) =>
              n +
              hintsFor(
                lookIdx,
                allCandidates,
                t,
                run.context.rosters.filter((p) => p.side === sideMap[t]).map((p) => p.player_id),
                draftAssignments,
                new Set(),
              ).hints.length,
            0,
          )
        : 0,
    [looks, lookIdx, allCandidates, run, sideMap, draftAssignments],
  );
```

- [ ] **Step 3: Кнопка режима.** В группе `aria-label="Сопоставлять"` после кнопки «Подбор» (внутри того же
  `{looks && (...)}` — обернуть обе кнопки во фрагмент):

```tsx
          {looks && (
            <>
              <button aria-pressed={mode === 'similar'} onClick={() => setMode('similar')}>
                Подбор
              </button>
              <button aria-pressed={mode === 'hints'} onClick={() => setMode('hints')}>
                Подсказки · {hintCount}
              </button>
            </>
          )}
```

- [ ] **Step 4: Ветка отрисовки.** Перед `) : mode === 'players' ? (` вставить ветку режима:

```tsx
      ) : mode === 'hints' ? (
        <SuggestionPicker
          run={run}
          assignments={assignments}
          sideMap={draft.value.side_map}
          disabled={disabled}
          onChange={(next) => change({ ...draft.value, assignments: next })}
          onOpenSimilar={() => setMode('similar')}
        />
```

- [ ] **Step 5: Прогнать тесты анализа**

Run: `cd web && npx vitest run src/features/analysis && npx tsc -b`
Expected: все тесты `src/features/analysis` проходят, включая 4 теста `SuggestionPicker.test.tsx`; `tsc` без ошибок.

- [ ] **Step 6: Commit**

```bash
npx biome format --write src/features/analysis/IdentityReview.tsx
git add web/src/features/analysis/IdentityReview.tsx
git commit -m "feat(review): suggestions mode on the review tab"
```

---

### Task 5: E2E — второй фрагмент из «Подсказок»

**Files:**
- Modify: `web/e2e/similar-picker.spec.ts` (блок после первого «Добавить отмеченных (1)»)

- [ ] **Step 1: Заменить назначение второго фрагмента.** Блок

```ts
  const next = picker.getByRole('listitem', { name: 'Фрагмент 0:00–1:00' });
  await expect(next).toContainText('похож 1.00');
  await next.getByRole('button', { name: 'Он', exact: true }).click();
  await picker.getByRole('button', { name: 'Добавить отмеченных (1)' }).click();
  await expect(picker.getByRole('status', { name: 'Назначено времени команды' })).toContainText('100%');
```
заменить на
```ts
  const next = picker.getByRole('listitem', { name: 'Фрагмент 0:00–1:00' });
  await expect(next).toContainText('похож 1.00');
  // Оставшийся фрагмент — из «Подсказок»: фрагменты есть у одного игрока, подсказка уверенная и уже отмечена.
  await page.getByRole('button', { name: 'Подсказки · 1', exact: true }).click();
  const hints = page.getByRole('region', { name: 'Подсказки игроков' });
  const card = hints.getByRole('listitem', { name: 'Фрагмент 0:00–1:00' });
  await expect(card).toContainText('уверенно');
  await expect(card.getByRole('checkbox', { name: 'Назначить' })).toBeChecked();
  await hints.getByRole('button', { name: 'Назначить отмеченных (1)' }).click();
  await expect(hints).toContainText('Подсказок нет');
  await page.getByRole('button', { name: 'Подбор', exact: true }).click();
  await expect(picker.getByRole('status', { name: 'Назначено времени команды' })).toContainText('100%');
```

Дальше тест без изменений: снимок «Подбора», сохранение и проверка, что игроку назначены фрагменты 1 и 2.

- [ ] **Step 2: Прогнать E2E изолированно** (сервис организатора на 8000 не трогать; общую `web/dist` не
  пересобирать). Выгрузка коммита:

```bash
R=<scratchpad>/e2e-hints; E="$R/export"; rm -rf "${R:?}"; mkdir -p "$E"
git archive HEAD | tar -x -C "$E"
ln -s "$PWD/.env" "$E/.env"; ln -s "$PWD/.venv" "$E/.venv"; ln -s "$PWD/web/node_modules" "$E/web/node_modules"
cd "$E/web" && npx vite build --outDir "$R/dist"
PYTHONPATH="$E/src" AIF_E2E_FAKE_MAIL=1 AIF_E2E_FAKE_ADDRESS=1 AIF_E2E_PORT=8286 \
  AIF_E2E_DATABASE_NAME=aifootball_hints_e2e AIF_WEB_DIST="$R/dist" npx playwright test --reporter=line
```
Expected: 35 passed (вместе с изменённым `similar-picker.spec.ts`).

- [ ] **Step 3: Commit**

```bash
git add web/e2e/similar-picker.spec.ts
git commit -m "test(e2e): assign the leftover fragment from suggestions"
```

---

### Task 6: документация

**Files:**
- Modify: `README.md` (после абзаца «Подбор похожих фрагментов»)
- Modify: `docs/README.md` (раздел «Архитектура и следующие этапы», после строки «Люди вместо фрагментов»)

- [ ] **Step 1: README** — новый пункт после «**Подбор похожих фрагментов:** …»:

```markdown
- **Подсказки для оставшихся фрагментов:** режим «Подсказки» в «Проверке» — обратный взгляд к «Подбору»: каждому неназначенному кандидату команды — самый похожий по цвету формы игрок из тех, у кого уже есть фрагменты и кто не виден одновременно с кандидатом. Подсказки сгруппированы по игрокам; уверенные (лучший игрок обходит второго на ≥ 0,03) отмечены сразу, «Не он» отдаёт кандидата следующему игроку, «Назначить отмеченных» меняет черновик сопоставления. Замер на ВШЭ Ю — JWH по 513 назначенным фрагментам: верно 83%, уверенные — 93% ([спецификация](docs/superpowers/specs/2026-11-26-identity-suggestions-design.md)). Фрагменты без признака цвета назначаются в «По фрагментам».
```

- [ ] **Step 2: docs/README.md** — новая строка после «Люди вместо фрагментов»:

```markdown
- [Подсказки игрока для оставшихся фрагментов](superpowers/specs/2026-11-26-identity-suggestions-design.md): режим «Подсказки» в «Проверке» по цвету формы (этап 1, [план](superpowers/plans/2026-11-26-identity-suggestions.md)); этап 2 — продолжение трека по месту обрыва, нужны концы фрагментов в пакете.
```

- [ ] **Step 3: Commit**

```bash
git add README.md docs/README.md
git commit -m "docs: suggestions mode in README and docs index"
```

---

### Task 7: общая проверка

- [ ] **Step 1:** `cd web && npm run lint` — ошибок нет (предупреждения в новых строках — убрать).
- [ ] **Step 2:** `cd web && npx vitest run` — все тесты проходят.
- [ ] **Step 3:** `cd web && npx tsc -b && npx vite build --outDir <scratchpad>/build-check` — без ошибок (не в общую
  `web/dist`).
- [ ] **Step 4:** `git diff --check main...HEAD` — без пробелов в концах строк.
- [ ] **Step 5:** проверить в браузере на тестовом сервисе из задачи 5: «Подсказки» на ширине 1440 и 390 px без
  горизонтальной прокрутки (как проверяет `similar-picker.spec.ts`).

---

### Task 8: PR от `main` и сайт

- [ ] **Step 1: Ветка от `main` без checkout.** `BASE` — коммит `local/serve-hse` перед этой работой (`e3e0d6b`,
  PR #45; спецификация и план входят в перенос):

```bash
git fetch -q origin
T=$(git merge-tree --write-tree --merge-base=e3e0d6b origin/main HEAD)   # конфликтов быть не должно
C=$(git commit-tree "$T" -p origin/main -m "feat(review): player suggestions for leftover fragments")
git branch feat/identity-suggestions "$C"
```

Если PR #45 к этому времени слит в `main`, `merge-base` тот же: изменения PR #45 уже есть с обеих сторон.

- [ ] **Step 2: Проверить ветку на выгрузке** (`git archive feat/identity-suggestions`): vitest, `tsc -b`, сборка,
  E2E 35/35 — как в задаче 5.
- [ ] **Step 3: PR** — `git push -u origin feat/identity-suggestions`, `gh pr create --base main` с описанием на русском
  (что сделано, замер, проверка), привязать к сессии. Не сливать без пользователя.
- [ ] **Step 4: Сайт** — только по согласию пользователя: `vite build` в `web/` и перезапуск сервера во вкладке «site
  server» той же командой.
