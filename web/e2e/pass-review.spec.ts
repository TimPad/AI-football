import { spawnSync } from 'node:child_process';
import { expect, test } from '@playwright/test';

// Пакет версии 3 с двумя передачами команды A: точная трек 1 → трек 2 на 10 с и неточная на 30 с.
function packageFor(job: unknown) {
  const code =
    "import sys,json; from test_analysis_exchange import result_zip,events_doc; job=json.load(sys.stdin)\ndef mutate(m,r,t,c):\n for p in r['periods'][0]['players']: p['heatmap_s'][0][0]=1\n m.update(contract_version='3')\nsys.stdout.buffer.write(result_zip(job,mutate=mutate,extras={'events.json':events_doc()}))";
  const result = spawnSync('../.venv/bin/python', ['-c', code], {
    input: JSON.stringify(job),
    env: { ...process.env, PYTHONPATH: '../tests' },
  });
  if (result.status !== 0) throw Error(result.stderr.toString());
  return result.stdout;
}

test('video passes are checked one by one; guests see the checked passes before the actions are published', async ({
  page,
  browser,
}) => {
  await page.goto('/login');
  await page.getByLabel('Логин', { exact: true }).fill('e2e-analyst');
  await page.getByLabel('Пароль', { exact: true }).fill('e2e-only-password');
  await page.getByRole('button', { name: 'Войти', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Турниры', exact: true })).toBeVisible();
  const session = await (await page.request.get('/api/v1/auth/me')).json();
  const headers = { 'X-CSRF-Token': session.csrf_token, Origin: new URL(page.url()).origin };
  async function call(path: string, data: unknown, method = 'POST') {
    const r = await page.request.fetch(`/api/v1${path}`, { method, data, headers });
    expect(r.ok(), await r.text()).toBeTruthy();
    return r.json();
  }
  const suffix = crypto.randomUUID().slice(0, 6);
  const hall = await call('/halls', {
    name: `Передачи ${suffix}`,
    address: 'Тестовый адрес',
    pitch_length_m: 40,
    pitch_width_m: 20,
  });
  const camera = await call(`/halls/${hall.id}/camera-profiles`, {
    name: 'Камера',
    expected_hall_revision: hall.revision,
    frame_width: 1000,
    frame_height: 500,
    points: [
      { px: [0, 0], m: [0, 0] },
      { px: [999, 0], m: [40, 0] },
      { px: [999, 499], m: [40, 20] },
      { px: [0, 499], m: [0, 20] },
    ],
    pitch_polygon_px: [
      [0, 0],
      [999, 0],
      [999, 499],
      [0, 499],
    ],
  });
  const tour = await call('/tournaments', {
    name: `Проверка передач ${suffix}`,
    visibility: 'public',
    season: '2026',
    starts_on: '2026-10-01',
    ends_on: '2026-12-31',
  });
  const regulation = await call(`/tournaments/${tour.id}/regulations`, { variant_name: 'Группа', rules: {} });
  const entries = [];
  const lineup = [];
  const people: Record<string, { id: string; name: string }[]> = { home: [], away: [] };
  for (const [side, team, count] of [
    ['home', 'Север', 2],
    ['away', 'Юг', 1],
  ] as const) {
    const created = await call('/teams', { name: `${team} ${suffix}` });
    const entry = await call(`/tournaments/${tour.id}/entries`, { team_id: created.id });
    entries.push(entry);
    for (let i = 1; i <= count; i++) people[side].push(await call('/players', { name: `${team} ${i} ${suffix}` }));
    const roster = await call(
      `/entries/${entry.id}/players`,
      { expected_revision: 0, players: people[side].map((p, i) => ({ player_id: p.id, shirt_number: String(i + 7) })) },
      'PUT',
    );
    lineup.push(...roster.players.map((p: { id: string }) => ({ entry_player_id: p.id, side })));
  }
  let match = await call(`/tournaments/${tour.id}/matches`, {
    home_entry_id: entries[0].id,
    away_entry_id: entries[1].id,
    regulation_id: regulation.id,
    scheduled_at: '2026-10-20T18:00:00+03:00',
    hall_id: hall.id,
    camera_profile_id: camera.id,
  });
  match = await call(`/matches/${match.id}/commands`, {
    request_id: crypto.randomUUID(),
    expected_revision: match.revision,
    kind: 'set_lineup',
    payload: { players: lineup },
  });
  const path = `/matches/${match.id}`;
  const job = await call(`${path}/analysis/jobs`, { request_id: crypto.randomUUID() });
  const imported = await page.request.post(`/api/v1${path}/analysis/imports`, {
    multipart: { file: { name: 'result.zip', mimeType: 'application/zip', buffer: packageFor(job) } },
    headers: { ...headers, 'X-Request-ID': crypto.randomUUID() },
  });
  expect(imported.ok(), await imported.text()).toBeTruthy();
  let run = await imported.json();
  const players = { 1: people.home[0].id, 2: people.home[1].id, 3: people.away[0].id };
  run = await call(
    `${path}/analysis/runs/${run.id}/assignments`,
    {
      request_id: crypto.randomUUID(),
      expected_revision: run.revision,
      side_map: { A: 'home', B: 'away' },
      assignments: Object.entries(players).map(([track, player]) => ({ track_id: Number(track), player_id: player })),
    },
    'PUT',
  );
  let analysis = await (await page.request.get(`/api/v1${path}/analysis`)).json();
  run = await call(`${path}/analysis/runs/${run.id}/confirm`, {
    request_id: crypto.randomUUID(),
    expected_revision: run.revision,
    expected_analysis_revision: analysis.analysis_revision,
  });
  // Видеоанализ опубликован, действия матча — нет: зритель видит передачи из видео с пометкой «авто».
  analysis = await (await page.request.get(`/api/v1${path}/analysis`)).json();
  await call(`${path}/analysis/runs/${run.id}/publish`, {
    request_id: crypto.randomUUID(),
    expected_revision: run.revision,
    expected_analysis_revision: analysis.analysis_revision,
  });
  const guest = await (await browser.newContext()).newPage();
  const publicStats = async () => (await guest.request.get(`/api/v1/public${path}/action-stats`)).json();
  const passesRow = (stats: { rows: { key: string; source: string }[] }) =>
    stats.rows.find((r) => r.key === 'passes_total')!.source;
  expect(passesRow(await publicStats())).toBe('cv_auto');
  const before = await (await page.request.get(`/api/v1${path}/action-stats`)).json();
  expect(before.passes.map((p: { verified: boolean }) => p.verified)).toEqual([false, false]);

  await page.goto(`${path}?tab=actions`);
  const review = page.getByRole('region', { name: 'Проверка передач' });
  await expect(review.getByRole('status', { name: 'Проверено передач' })).toContainText('0 / 2');
  await expect(review.locator('.pass-review-title')).toContainText(
    `0:10 · ${people.home[0].name} → ${people.home[1].name}`,
  );
  await review.getByRole('button', { name: /^Верно/ }).click();
  // Вторая — «неточная» по видео; на записи её принял партнёр: делаем точной и указываем принявшего.
  await expect(review.locator('.pass-review-title')).toContainText('0:30');
  await review.getByRole('button', { name: /^Точная/ }).click();
  await review.getByLabel('Принял').selectOption(people.home[1].id);
  await review.screenshot({ path: 'test-results/pass-review.png' });
  await review.getByRole('button', { name: /^Верно/ }).click();
  await expect(review.getByRole('note')).toContainText('Все передачи проверены');
  await review.getByRole('button', { name: 'Сохранить и подтвердить проверку', exact: true }).click();
  // «2 / 2» черновик показывает и до ответа сервера: ждём, пока статистика перейдёт на проверенную версию.
  const stats = async () => (await page.request.get(`/api/v1${path}/action-stats`)).json();
  await expect.poll(async () => (await stats()).source.kind).toBe('manual');
  await expect(review.getByRole('status', { name: 'Проверено передач' })).toContainText('2 / 2');
  const after = await stats();
  expect(after.passes.map((p: { verified: boolean; success: boolean }) => [p.verified, p.success])).toEqual([
    [true, true],
    [true, true],
  ]);
  expect(after.pass_players).toEqual([
    expect.objectContaining({ player_id: people.home[0].id, total: 2, accurate: 2, verified: 2 }),
  ]);
  // Зритель видит проверку сразу, с пометкой «проверено» и точностью «не 100%»; действия при этом не опубликованы.
  await expect.poll(async () => passesRow(await publicStats())).toBe('cv_reviewed');
  await guest.goto(`/watch${path}?tab=stats`);
  const card = guest.locator('.stat-card', { has: guest.getByRole('heading', { name: 'Передачи: карта и точность' }) });
  await expect(card.getByText(/проверены вручную, разбор матча ещё не опубликован/)).toBeVisible();
  await expect(card.getByLabel('Точность передач команд')).toContainText('≈100%');
  await expect(guest.locator('.stat-row', { hasText: 'Точные передачи' }).getByText('проверено')).toBeVisible();
  await card.screenshot({ path: 'test-results/pass-review-public.png' });
  for (const width of [768, 390]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth),
    ).toBe(true);
  }
  await review.screenshot({ path: 'test-results/pass-review-390.png' });
});
