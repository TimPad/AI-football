import {test,expect,type Page} from '@playwright/test';
import {login} from './helpers';

// Контраст текста к фону, считанный из вычисленных стилей (прозрачный фон — берётся у ближайшего непрозрачного предка).
async function contrastOf(page:Page,selector:string){
 return page.evaluate(sel=>{
  const el=document.querySelector(sel) as HTMLElement;if(!el)return 0;
  const rgb=(v:string)=>(v.match(/[\d.]+/g)??[]).map(Number);
  const lum=([r,g,b]:number[])=>{const f=(c:number)=>{c/=255;return c<=0.03928?c/12.92:((c+0.055)/1.055)**2.4};return 0.2126*f(r)+0.7152*f(g)+0.0722*f(b)};
  let bg=el;while(bg&&(getComputedStyle(bg).backgroundColor==='rgba(0, 0, 0, 0)'||getComputedStyle(bg).backgroundColor==='transparent'))bg=bg.parentElement as HTMLElement;
  const a=lum(rgb(getComputedStyle(el).color)),b=lum(rgb(getComputedStyle(bg??document.body).backgroundColor));
  return (Math.max(a,b)+0.05)/(Math.min(a,b)+0.05);
 },selector);
}
const darkBody=(page:Page)=>page.evaluate(()=>{const [r,g,b]=(getComputedStyle(document.documentElement).backgroundColor.match(/\d+/g)??[]).map(Number);return (r+g+b)/3<40});

test('тёмная тема сайта зрителя: фон, контраст, без прокрутки вбок; кабинет остаётся светлым',async({page,browser})=>{
 await login(page);
 const session=await (await page.request.get('/api/v1/auth/me')).json();const headers={'X-CSRF-Token':session.csrf_token,Origin:new URL(page.url()).origin};
 const call=async(path:string,data?:unknown,method='POST')=>{const r=await page.request.fetch(`/api/v1${path}`,{method,data,headers});expect(r.ok(),await r.text()).toBeTruthy();return r.json()};
 const suffix=crypto.randomUUID().slice(0,6);
 const t=await call('/tournaments',{name:`Тёмный кубок ${suffix}`,season:'2026',starts_on:'2026-11-01',ends_on:'2026-12-31',timezone:'Europe/Moscow',visibility:'public'});
 const preset=(await call('/tournaments/regulation-presets',undefined,'GET')).items[0].rules;
 const reg=await call(`/tournaments/${t.id}/regulations`,{variant_name:'Основной',rules:preset});
 const entries:string[]=[];
 for(let i=1;i<=4;i++){const team=await call('/teams',{name:`Ночь ${i} ${suffix}`});entries.push((await call(`/tournaments/${t.id}/entries`,{team_id:team.id})).id)}
 const stages=(await call(`/tournaments/${t.id}/format`,{template:'playoff',regulation_id:reg.id,request_id:crypto.randomUUID()})).stages;
 await call(`/stages/${stages[0].id}/draw`,{method:'seeded',seed:0,seeding:entries,expected_revision:0,request_id:crypto.randomUUID()});
 for(const width of [375,1440]){
  const guest=await browser.newContext({viewport:{width,height:900},colorScheme:'dark'});const p=await guest.newPage();
  await p.goto(`/watch/tournaments/${t.id}`);
  await expect(p.locator('.pair-card').first()).toBeVisible();
  expect(await darkBody(p)).toBe(true);
  expect(await contrastOf(p,'.pair-card .pair-team span:not(.team-logo), .pair-card .pair-team .team-path')).toBeGreaterThanOrEqual(4.5);
  expect(await contrastOf(p,'.pair-leg')).toBeGreaterThanOrEqual(4.5);
  expect(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await p.screenshot({path:`test-results/public-dark-${width}.png`,fullPage:true});
  await p.goto('/');expect(await darkBody(p)).toBe(true);
  expect(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await guest.close();
 }
 const dark=await browser.newContext({colorScheme:'dark'});const cabinet=await dark.newPage();
 await cabinet.goto('/login');expect(await darkBody(cabinet)).toBe(false);
 await dark.close();
});
