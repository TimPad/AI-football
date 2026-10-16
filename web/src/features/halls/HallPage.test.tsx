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

it('uploads a reference frame once and then shows it with the profile points and outline',async()=>{
 const {Routes,Route}=await import('react-router-dom');
 const hall={id:'h1',revision:1,name:'Арена',address:'Ярославль',pitch_length_m:40,pitch_width_m:20,ceiling_height_m:null,surface:'',description:'',archived:false};
 let profile={id:'c1',hall_id:'h1',name:'Основная камера',version:1,hall_revision:1,pitch_length_m:40,pitch_width_m:20,frame_width:1000,frame_height:500,
  points:[{px:[0,0],m:[0,0]},{px:[999,0],m:[40,0]},{px:[999,499],m:[40,20]},{px:[0,499],m:[0,20]}],pitch_polygon_px:[[0,0],[999,0],[999,499],[0,499]],
  homography:[[1,0,0],[0,1,0],[0,0,1]],calibration:null,reprojection_error_m:0.01,leave_one_out_error_m:null,reference_sha256:null as string|null,matches_current_dimensions:true};
 const puts:FormData[]=[];
 vi.stubGlobal('fetch',vi.fn(async(url:unknown,options:RequestInit={})=>{
  const json=(v:unknown)=>new Response(JSON.stringify(v),{headers:{'Content-Type':'application/json'}});
  if(options.method==='PUT'){puts.push(options.body as FormData);profile={...profile,reference_sha256:'a'.repeat(64)};return json(profile)}
  if(String(url).includes('/camera-profiles'))return json({items:[profile],total:1});
  return json(hall);
 }));
 render(<MemoryRouter initialEntries={['/halls/h1']}><Routes><Route path="/halls/:id" element={<HallPage/>}/></Routes></MemoryRouter>);
 fireEvent.click(await screen.findByText(/Основная камера · версия 1/));
 expect(screen.getByText(/Эталонный кадр не загружен/)).toBeInTheDocument();
 const input=screen.getByText('Загрузить эталонный кадр').querySelector('input')!;
 fireEvent.change(input,{target:{files:[new File(['jpeg'],'frame.jpg',{type:'image/jpeg'})]}});
 const image=await screen.findByRole('img',{name:'Эталонный кадр камеры «Основная камера», версия 1'});
 expect(image).toHaveAttribute('src','/api/v1/halls/h1/camera-profiles/c1/reference-frame');
 expect(puts).toHaveLength(1);expect((puts[0].get('file') as File).name).toBe('frame.jpg');
 expect(document.querySelectorAll('.reference-stage circle')).toHaveLength(4);
});
