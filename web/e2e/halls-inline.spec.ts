import {test,expect} from '@playwright/test';
import {login,createTournament} from './helpers';
test('creates a suggested hall without losing the match form',async({page})=>{
 await login(page);const t=await createTournament(page);await page.goto(`/tournaments/${t.tid}`);await page.getByRole('button',{name:'Создать матч',exact:true}).click();
 await page.getByLabel('Хозяева',{exact:true}).selectOption({label:t.home});await page.getByLabel('Гости',{exact:true}).selectOption({label:t.away});await page.getByLabel('Дата и время · Europe/Moscow',{exact:true}).fill('2026-10-21T20:00');
 await page.getByRole('button',{name:'Создать зал',exact:true}).click();const dialog=page.getByRole('dialog',{name:'Создать зал',exact:true});
 await dialog.getByLabel('Название зала',{exact:true}).fill('Арена внутри матча');const address=dialog.getByRole('combobox',{name:'Адрес зала',exact:true});await address.fill('Спортивная');await dialog.getByRole('option',{name:/Тестовая арена/}).waitFor();await address.press('ArrowDown');await address.press('Enter');await expect(address).toHaveValue('Тестовый город, Спортивная, 1');
 await dialog.getByLabel('Длина поля, м',{exact:true}).fill('40');await dialog.getByLabel('Ширина поля, м',{exact:true}).fill('20');await dialog.getByRole('button',{name:'Сохранить зал',exact:true}).click();await expect(dialog).toHaveCount(0);
 await expect(page.getByLabel('Дата и время · Europe/Moscow',{exact:true})).toHaveValue('2026-10-21T20:00');await expect(page.getByLabel('Хозяева',{exact:true}).locator('option:checked')).toHaveText(t.home);
 const hallId=await page.getByLabel('Зал',{exact:true}).inputValue();const hall=await (await page.request.get(`/api/v1/halls/${hallId}`)).json();expect(hall.address_source).toBe('yandex');expect(hall.latitude).toBe(57.62);expect(hall.longitude).toBe(39.88);
 const response=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith(`/tournaments/${t.tid}/matches`));await page.getByRole('dialog',{name:'Новый матч',exact:true}).getByRole('button',{name:'Создать матч',exact:true}).click();const match=await (await response).json();expect(match.scheduled_at).toBe('2026-10-21T17:00:00Z');expect(match.hall_snapshot.address).toBe(hall.address);
});
