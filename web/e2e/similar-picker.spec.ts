import { spawnSync } from 'node:child_process';
import { expect, test } from '@playwright/test';

// Пакет с признаком цвета у фрагментов: 1 (A, 0–60 с) и 2 (A, 120–240 с) — одна форма, 3 (B) — другая.
function packageFor(job: unknown) {
  const code =
    "import sys,json,base64; from test_analysis_exchange import result_zip; job=json.load(sys.stdin)\nlook=lambda hot: base64.b64encode(bytes(255 if i==hot else 8 for i in range(156))).decode()\ndef mutate(m,r,t,c):\n for x in t['tracks']: x['appearance']=look(0 if x['team']=='A' else 40)\nsys.stdout.buffer.write(result_zip(job,mutate=mutate))";
  const result = spawnSync('../.venv/bin/python', ['-c', code], {
    input: JSON.stringify(job),
    env: { ...process.env, PYTHONPATH: '../tests' },
  });
  if (result.status !== 0) throw Error(result.stderr.toString());
  return result.stdout;
}

test('similar fragments are picked for a player and saved as track assignments', async ({ page }) => {
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
    name: `Подбор ${suffix}`,
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
    name: `Подбор фрагментов ${suffix}`,
    visibility: 'draft',
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
    for (let i = 1; i <= count; i++)
      people[side].push(await call('/players', { name: `${team} · игрок ${i} ${suffix}` }));
    const roster = await call(
      `/entries/${entry.id}/players`,
      { expected_revision: 0, players: people[side].map((p) => ({ player_id: p.id, shirt_number: null })) },
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
  const run = await imported.json();

  await page.goto(`${path}?tab=review`);
  const picker = page.getByRole('region', { name: 'Подбор похожих фрагментов' });
  await expect(page.getByRole('button', { name: 'Подбор', exact: true })).toHaveAttribute('aria-pressed', 'true');
  const player = people.home.find((p) => p.name.startsWith('Север · игрок 1'))!;
  await expect(picker.getByLabel('Игрок')).toHaveValue(/.+/);
  const chosen = await picker.getByLabel('Игрок').inputValue();
  // Начало подбора — самый длинный фрагмент команды (2: 2:00–4:00); после него подсказан похожий 1.
  await picker
    .getByRole('listitem', { name: 'Фрагмент 2:00–4:00' })
    .getByRole('button', { name: 'Он', exact: true })
    .click();
  await picker.getByRole('button', { name: 'Добавить отмеченных (1)' }).click();
  const next = picker.getByRole('listitem', { name: 'Фрагмент 0:00–1:00' });
  await expect(next).toContainText('похож 1.00');
  // Оставшийся фрагмент — из «Подсказок»: фрагменты есть у одного игрока, подсказка уверенная и уже отмечена.
  await page.getByRole('button', { name: 'Подсказки · 1', exact: true }).click();
  const hints = page.getByRole('region', { name: 'Подсказки игроков' });
  const card = hints.getByRole('listitem', { name: 'Фрагмент 0:00–1:00' });
  await expect(card).toContainText('уверенно');
  await expect(card.getByRole('checkbox', { name: 'Назначить' })).toBeChecked();
  for (const width of [390, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth),
    ).toBe(true);
    await hints.screenshot({ path: `test-results/suggestion-picker-${width}.png` });
  }
  await hints.getByRole('button', { name: 'Назначить отмеченных (1)' }).click();
  await expect(hints).toContainText('Подсказок нет');
  await page.getByRole('button', { name: 'Подбор', exact: true }).click();
  await expect(picker.getByRole('status', { name: 'Назначено времени команды' })).toContainText('100%');
  await picker.screenshot({ path: 'test-results/similar-picker.png' });
  await page.getByRole('button', { name: 'Сохранить сопоставление', exact: true }).click();
  await expect
    .poll(async () => {
      const saved = await (await page.request.get(`/api/v1${path}/analysis/runs/${run.id}`)).json();
      return saved.assignments
        .filter((a: { player_id: string | null }) => a.player_id === chosen)
        .map((a: { track_id: number }) => a.track_id)
        .sort();
    })
    .toEqual([1, 2]);
  expect(chosen).toBeTruthy();
  expect(player).toBeTruthy();
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth),
    ).toBe(true);
  }
  await picker.screenshot({ path: 'test-results/similar-picker-390.png' });
});
