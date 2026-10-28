import {describe,expect,it} from 'vitest';
import {render,screen,within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MemoryRouter} from 'react-router-dom';
import {PairCard} from './PairCard';
import {BracketTree,rowsFor} from './BracketTree';
import {Bracket} from './Bracket';
import {pair,side} from './fixtures.test-data';
import {pairSpeech} from './labels';
import type {SectionView} from './api';

const leg=(n:number,iso:string|null,score:[number,number]|null,extra={})=>({match_id:score?`m${n}`:null,fixture_id:null,leg:n,scheduled_at:iso,status:score?'ended':iso?'scheduled':null,
 score:score?{home:score[0],away:score[1]}:null,shootout:null,technical:false,annulled:false,...extra});
const tz='Europe/Moscow';

describe('карточка пары',()=>{
 it('пара из двух матчей: обе даты, счёт каждого, итог и победитель',()=>{
  const p=pair('U1-1','Полуфинал',side('Север'),side('Юг'),{winner:'home',legs:[leg(1,'2026-11-12T16:00:00Z',[2,2]),leg(2,'2026-11-19T16:00:00Z',[3,1])]});
  render(<MemoryRouter><PairCard pair={p} timezone={tz} matchHref={id=>`/watch/matches/${id}`}/></MemoryRouter>);
  const card=screen.getByRole('article');
  expect(card).toHaveAccessibleName('Полуфинал. Север 5, Юг 3. Север прошёл дальше');
  const links=within(card).getAllByRole('link');
  expect(links.map(a=>a.textContent)).toEqual(['Матч 112 нояб., 19:002 : 2','Матч 219 нояб., 19:003 : 1']);
  expect(links[1]).toHaveAttribute('href','/watch/matches/m2');
  expect(card.querySelector('.pair-team.won')).toHaveTextContent('Север5');
 });
 it('пенальти в скобках и тех. поражение подписаны',()=>{
  const pens=pair('U1-2','Полуфинал',side('Восток'),side('Запад'),{winner:'home',legs:[{...leg(1,'2026-11-14T17:30:00Z',[1,1]),shootout:{home:4,away:3}}]});
  const {unmount}=render(<MemoryRouter><PairCard pair={pens} timezone={tz}/></MemoryRouter>);
  expect(screen.getByRole('article')).toHaveTextContent('Восток1 (4)');
  expect(screen.getByRole('article')).toHaveAccessibleName(/Пенальти 4:3/);
  unmount();
  const tech=pair('G1-R3-1','Группа A · Тур 3',side('Север'),side('Юг'),{bracket:null,walkover:'home',winner:'home',legs:[leg(1,null,[5,0],{technical:true})]});
  render(<MemoryRouter><PairCard pair={tech} timezone={tz}/></MemoryRouter>);
  expect(screen.getByRole('article')).toHaveTextContent('Тех. поражение');
  expect(pairSpeech(tech,tz)).toContain('Техническая победа');
 });
 it('несыгранный матч: дата или «Дата не назначена»',()=>{
  const p=pair('U2-1','Финал',side('Север'),side('Победитель пары 2',false),{legs:[leg(1,'2026-11-21T16:00:00Z',null)]});
  render(<MemoryRouter><PairCard pair={p} timezone={tz}/></MemoryRouter>);
  expect(screen.getByRole('article')).toHaveAccessibleName('Финал. Север — Победитель пары 2. Матч — 21 ноября в 19:00');
 });
});

const tree:SectionView={key:'upper',name:'Сетка',current_round:1,rounds:[
 {round_no:1,name:'1/4 финала',pairs:[1,2,3,4].map(s=>pair(`U1-${s}`,'1/4 финала',side(`К${s*2-1}`),side(`К${s*2}`),{slot:s}))},
 {round_no:2,name:'Полуфинал',pairs:[1,2].map(s=>pair(`U2-${s}`,'Полуфинал',side(s===1?'К1':'К5'),side('?',false),{slot:s,round_no:2,home_from:`U1-${s*2-1}`,away_from:`U1-${s*2}`}))},
 {round_no:3,name:'Финал',pairs:[pair('U3-1','Финал',side('?',false),side('?',false),{slot:1,round_no:3,home_from:'U2-1',away_from:'U2-2'})]}]};

describe('дерево сетки',()=>{
 it('пары следующего раунда стоят между своими, линий столько, сколько связей',()=>{
  const {place}=rowsFor(tree);
  expect(place(0,0)).toEqual({start:2,span:2});expect(place(1,0)).toEqual({start:2,span:4});expect(place(2,0)).toEqual({start:2,span:8});
  let n=0;const rect=()=>{n++;return {left:n*10,right:n*10+100,top:n*5,bottom:n*5+40,width:100,height:40,x:0,y:0,toJSON(){}}};
  const original=Element.prototype.getBoundingClientRect;Element.prototype.getBoundingClientRect=rect as never;
  try{render(<MemoryRouter><BracketTree section={tree} timezone={tz} path={null} onTeam={()=>{}}/></MemoryRouter>)}finally{Element.prototype.getBoundingClientRect=original}
  expect(document.querySelectorAll('.bracket-lines path')).toHaveLength(6);
 });
 it('нажатие на команду подсвечивает её путь, Esc снимает',async()=>{
  render(<MemoryRouter><Bracket sections={[tree]} timezone={tz} wide/></MemoryRouter>);
  await userEvent.click(screen.getAllByRole('button',{name:'К1'})[0]);
  expect(document.querySelectorAll('.pair-card[data-path]')).toHaveLength(2);
  expect(screen.getAllByRole('button',{name:'К1'})[0]).toHaveAttribute('aria-pressed','true');
  await userEvent.keyboard('{Escape}');
  expect(document.querySelectorAll('.pair-card[data-path]')).toHaveLength(0);
 });
});
