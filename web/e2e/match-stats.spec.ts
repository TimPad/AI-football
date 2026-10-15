import {test,expect} from '@playwright/test';
import {spawnSync} from 'node:child_process';

test('guest reads FotMob-like match statistics from published protocol and reviewed actions',async({page})=>{
 const seed=spawnSync('../.venv/bin/python',['../scripts/seed_match_stats_e2e.py'],{encoding:'utf8'});if(seed.status!==0)throw Error(seed.stderr||seed.stdout);
 const data=JSON.parse(seed.stdout);const api:string[]=[];
 page.on('request',r=>{if(r.url().includes('/api/'))api.push(r.url())});
 await page.goto(`/watch/matches/${data.match_id}`);
 await expect(page.getByLabel('Счёт 2 : 1')).toBeVisible();
 await expect(page.getByLabel('Авторы голов')).toContainText("Демо Север 2 6'");
 await expect(page.getByRole('list',{name:'Лента матча'})).toContainText('Гол · 2 : 1');
 await page.getByRole('navigation',{name:'Разделы матча'}).getByRole('link',{name:'Статистика',exact:true}).click();
 const shots=page.locator('.stat-card',{hasText:'Удары'}).filter({has:page.getByRole('heading',{name:'Удары',exact:true})});
 await expect(shots.locator('.stat-row',{hasText:'Всего ударов'})).toContainText('11');
 await expect(page.getByRole('img',{name:/Карта ударов: 18/})).toBeVisible();
 await page.getByRole('button',{name:'2-й тайм',exact:true}).click();
 await expect(page).toHaveURL(/period=2/);
 await expect(page.locator('.stat-card',{has:page.getByRole('heading',{name:'Дисциплина'})}).locator('.stat-row',{hasText:'Накопленные фолы'})).toBeVisible();
 for(const width of [1440,1024,390]){await page.setViewportSize({width,height:900});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth)).toBe(true)}
 expect(api.every(url=>url.includes('/api/v1/public/'))).toBe(true);
});
