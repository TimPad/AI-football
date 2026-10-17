import {expect,type Page} from '@playwright/test';
// Задачи матча: четыре раздела, шаги раздела видны, когда он открыт. task открывает раздел шага, если нужно.
const SECTION:Record<string,string>={Сведения:'Протокол',Состав:'Протокол',События:'Протокол',Проверка:'Видео',Участие:'Видео',Действия:'Видео',
 Опубликовать:'Публикация',Предпросмотр:'Публикация'};
export const task=(page:Page,name:string)=>{
 const nav=page.getByRole('navigation',{name:'Задачи матча'});const link=nav.getByRole('link',{name,exact:true});
 return {link,click:async()=>{
  if(SECTION[name]&&!await link.isVisible()){
   const section=nav.getByRole('link',{name:SECTION[name],exact:true});await section.click();
   // Раздел открыт: подчёркнут сам (один шаг — строки шагов нет) или показывает свои шаги.
   await expect(section.and(page.locator('[aria-current],.open'))).toBeVisible();
   if(!await link.count())return;
  }
  await link.click();
 }};
};
// Справочники — в меню верхней строки кабинета.
export async function catalog(page:Page,name:'Команды'|'Игроки'|'Залы'){
 await page.getByRole('button',{name:'Справочники',exact:true}).click();await page.getByRole('navigation',{name:'Кабинет'}).getByRole('link',{name,exact:true}).click();
}
export async function login(page:Page){await page.goto('/login');await page.getByLabel('Логин',{exact:true}).fill('e2e-admin');await page.getByLabel('Пароль',{exact:true}).fill('e2e-only-password');await page.getByRole('button',{name:'Войти',exact:true}).click();await expect(page.getByRole('heading',{name:'Турниры',exact:true})).toBeVisible()}
export async function createTournament(page:Page){
 const suffix=crypto.randomUUID().slice(0,8);const name=`Тестовый кубок ${suffix}`;const home=`Север ${suffix}`;const away=`Юг ${suffix}`;
 await page.getByRole('link',{name:'Создать турнир',exact:true}).click();await page.getByLabel('Название турнира').fill(name);await page.getByLabel('Начало турнира').fill('2026-10-01');await page.getByLabel('Окончание турнира').fill('2027-05-30');await page.getByRole('button',{name:'Создать и добавить команды'}).click();await page.getByRole('button',{name:'Сохранить регламент',exact:true}).click();await expect(page.getByRole('button',{name:'Применить к будущим матчам'})).toBeVisible();const tid=page.url().split('/tournaments/')[1].split('?')[0].split('/')[0];
 await page.goto(`/tournaments/${tid}`);await page.getByRole('button',{name:'Опубликовать страницу турнира',exact:true}).click();await expect(page.getByText('Страница опубликована',{exact:true})).toBeVisible();
 await page.goto('/halls/new');await page.getByLabel('Название зала',{exact:true}).fill('Тестовый зал');await page.getByLabel('Адрес зала',{exact:true}).fill(`Ярославль, Спортивная ${suffix}`);await page.getByLabel('Длина поля, м',{exact:true}).fill('41');await page.getByLabel('Ширина поля, м',{exact:true}).fill('15.5');await page.getByRole('button',{name:'Сохранить зал',exact:true}).click();await expect(page).toHaveURL(/\/halls\/[0-9a-f-]+$/);const hallId=new URL(page.url()).pathname.split('/').pop()!;
 await catalog(page,'Команды');for(const team of [home,away]){await page.getByRole('button',{name:'Создать команду',exact:true}).click();await page.getByLabel('Название команды',{exact:true}).fill(team);await page.getByRole('button',{name:'Сохранить',exact:true}).click();await expect(page).toHaveURL(/\/teams\/[0-9a-f-]+$/);await page.goto('/teams');await expect(page.getByRole('cell',{name:team,exact:true})).toBeVisible()}
 await page.goto(`/tournaments/${tid}?tab=teams`);for(const team of [home,away]){await page.getByRole('button',{name:'Выбрать существующие',exact:true}).click();await page.getByLabel(team,{exact:true}).check();await page.getByRole('button',{name:/Добавить выбранные/}).click();await expect(page.getByRole('cell',{name:team,exact:true})).toBeVisible()}
 await page.getByRole('link',{name:'Матчи',exact:true}).click();await page.getByRole('button',{name:'Создать матч',exact:true}).click();await page.getByLabel('Хозяева',{exact:true}).selectOption({label:home});await page.getByLabel('Гости',{exact:true}).selectOption({label:away});await page.getByLabel('Дата и время · Europe/Moscow',{exact:true}).fill('2026-10-20T19:00');await page.getByLabel('Зал',{exact:true}).selectOption(hallId);await page.getByRole('dialog').getByRole('button',{name:'Создать матч',exact:true}).click();await page.getByRole('link',{name:`Открыть матч ${home} — ${away}`,exact:true}).click();await task(page,'Протокол').click();await expect(page.getByText(/Все изменения сохранены/)).toBeVisible();return {tid,home,away,hallId,path:new URL(page.url()).pathname};
}
export async function goal(page:Page){await page.getByRole('button',{name:'Гол',exact:true}).click();await page.getByRole('button',{name:'Добавить событие',exact:true}).click();await expect(page.getByRole('dialog')).toHaveCount(0);await expect(page.getByText(/Все изменения сохранены/)).toBeVisible()}
// В режиме событий ручной итог свёрнут в «Итог вручную»; в «Только итог» он открыт сразу.
export async function totals(page:Page,home:number,away:number){const manual=page.locator('details.manual-totals');if(await manual.count()&&await manual.getAttribute('open')===null)await manual.locator(':scope > summary').click();await page.getByLabel('Счёт хозяев',{exact:true}).fill(String(home));await page.getByLabel('Счёт гостей',{exact:true}).fill(String(away));await page.getByRole('button',{name:'Сохранить итоги',exact:true}).click();await expect(page.getByText(/Все изменения сохранены/)).toBeVisible();await expect(page.locator('.big-score')).toContainText(`${home} : ${away}`)}

// Проверка записи: трек выбирается в очереди, игрок назначается в инспекторе.
export async function assignTrack(page:Page,id:number,player:string){
 await page.getByRole('navigation',{name:'Очередь треков'}).getByRole('button',{name:new RegExp(`Трек ${id}(?!\\d)`)}).click();
 await page.getByLabel(`Игрок фрагмента ${id}`,{exact:true}).selectOption(player);
}
