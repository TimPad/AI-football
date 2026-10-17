import {afterEach,it,expect,vi} from 'vitest';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import {MemoryRouter,Routes,Route} from 'react-router-dom';
import {RosterImportPage} from './RosterImportPage';
vi.mock('../auth/Auth',()=>({useAuth:()=>({session:{id:'admin'}})}));
const I='c81c1810-5dc0-4edf-819e-b86c72ec2bf6';
const base={id:I,revision:1,scope:'tournament',target_id:'t1',status:'ready',expires_at:'2026-11-01T00:00:00Z',
 sheets:[{name:'Состав',headers:['Команда','ФИО','Номер'],row_count:1}],configuration:{sheet:'Состав',mapping:{team:0,name:1,shirt_number:2},edits:{},decisions:{},team_decisions:{},excluded_rows:[]},
 rows:[{id:'0:2',source_row:2,name:'Иван Тест',team_name:'Север',shirt_number:'7',player_id:'p1',team_id:'a',player_candidates:[],team_candidates:[],issues:[],excluded:false,action:'Создать игрока',values:{name:'Иван Тест',team:'Север',shirt_number:'7'}}],
 summary:{teams_created:1,players_created:1,players_reused:0,entries_updated:1,skipped_rows:0,errors:0},can_commit:true,result:null};
function page(){return render(<MemoryRouter initialEntries={[`/roster-imports/${I}`]}><Routes><Route path="/roster-imports/:id" element={<RosterImportPage/>}/></Routes></MemoryRouter>)}
afterEach(()=>{vi.unstubAllGlobals();localStorage.clear()});
it('blocks application until edited rows have been checked again',async()=>{
 vi.stubGlobal('fetch',vi.fn(async()=>new Response(JSON.stringify(base))));
 page();await screen.findByRole('heading',{name:'Проверка состава'});
 expect(screen.getByRole('button',{name:'Применить импорт'})).toBeEnabled();
 fireEvent.change(screen.getByLabelText('ФИО, строка 2'),{target:{value:'Исправлено'}});
 expect(screen.getByRole('button',{name:'Применить импорт'})).toBeDisabled();
 expect(screen.getByText('Проверьте изменения перед применением')).toBeVisible();
});
it('replays the same committed command after a lost response and remount',async()=>{
 const bodies:string[]=[];
 vi.stubGlobal('fetch',vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>{
  if(String(input).endsWith('/commit')){bodies.push(String(init?.body));if(bodies.length===1)throw Error('lost');
   return new Response(JSON.stringify({...base.summary,links:[{path:'/teams/a',label:'Север'}]}));}
  return new Response(JSON.stringify(base));
 }));
 const view=page();await screen.findByRole('button',{name:'Применить импорт'});
 fireEvent.click(screen.getByRole('button',{name:'Применить импорт'}));
 await screen.findByRole('button',{name:'Повторить применение'});view.unmount();
 page();fireEvent.click(await screen.findByRole('button',{name:'Повторить применение'}));
 await screen.findByRole('heading',{name:'Состав загружен'});
 await waitFor(()=>expect(bodies).toHaveLength(2));expect(bodies[1]).toBe(bodies[0]);
});
