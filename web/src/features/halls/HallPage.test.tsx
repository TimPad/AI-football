import {it,expect,vi,afterEach} from 'vitest';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {HallPage} from './HallPage';
vi.mock('../auth/Auth',()=>({useAuth:()=>({session:{id:'admin-test'}})}));
afterEach(()=>{vi.unstubAllGlobals();localStorage.clear()});
it('uses a manually entered address for Yandex Maps without asking for GPS coordinates',async()=>{
 localStorage.clear();
 render(<MemoryRouter><HallPage/></MemoryRouter>);
 const address=await screen.findByLabelText('Адрес зала');
 expect(screen.queryByLabelText('Широта')).toBeNull();
 expect(screen.queryByLabelText('Долгота')).toBeNull();
 expect(screen.queryByRole('link',{name:'Открыть в Яндекс Картах'})).toBeNull();
 fireEvent.change(address,{target:{value:'Ярославль, Спортивная 1 & корпус 2'}});
 const link=screen.getByRole('link',{name:'Открыть в Яндекс Картах'});
 expect(new URL(link.getAttribute('href')!).searchParams.get('text')).toBe('Ярославль, Спортивная 1 & корпус 2');
 expect(link).toHaveAttribute('target','_blank');
 expect(link).toHaveAttribute('rel','noopener noreferrer');
 localStorage.clear();
});

it('drops GPS from an unsent legacy draft and retries exactly the same new payload after a lost body',async()=>{
 const draft={request_id:crypto.randomUUID(),expected_revision:0,attempted:false,name:'Арена',address:'Ярославль, Спортивная 1',pitch_length_m:'41',pitch_width_m:'15.5',ceiling_height_m:'',latitude:'57.6261',longitude:'39.8845',surface:'Паркет',description:'',archived:false};
 localStorage.setItem('aifootball:hall:admin-test:new',JSON.stringify({version:1,value:draft}));
 const sent:string[]=[];
 vi.stubGlobal('fetch',vi.fn(async(_url:unknown,options:RequestInit)=>{
  if(options.method==='POST'){
   sent.push(String(options.body));
   return new Response(sent.length===1?'{':JSON.stringify({...JSON.parse(sent[0]),id:'hall',revision:1,archived:false}),{status:201,headers:{'Content-Type':'application/json'}});
  }
  return new Response(JSON.stringify({items:[],total:0}),{headers:{'Content-Type':'application/json'}});
 }));
 render(<MemoryRouter><HallPage/></MemoryRouter>);
 fireEvent.click(await screen.findByRole('button',{name:'Сохранить зал'}));
 fireEvent.click(await screen.findByRole('button',{name:'Повторить сохранение'}));
 await waitFor(()=>expect(sent).toHaveLength(2));
 expect(sent[1]).toBe(sent[0]);
 expect(JSON.parse(sent[0])).not.toHaveProperty('latitude');
 expect(JSON.parse(sent[0])).not.toHaveProperty('longitude');
});
