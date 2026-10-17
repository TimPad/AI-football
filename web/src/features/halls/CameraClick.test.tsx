import {it,expect,vi,afterEach} from 'vitest';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import {MemoryRouter,Routes,Route} from 'react-router-dom';
import {HallPage} from './HallPage';
import {landmarks} from './FramePicker';

vi.mock('../auth/Auth',()=>({useAuth:()=>({session:{id:'admin-test'}})}));
// jsdom не декодирует изображения: размер кадра подставляем, остальная разметка — настоящая.
vi.mock('./FramePicker',async original=>({...await original<typeof import('./FramePicker')>(),readImageSize:vi.fn(async()=>({url:'blob:frame',w:1000,h:500}))}));
afterEach(()=>{vi.unstubAllGlobals();localStorage.clear()});

it('marks points by clicking the frame and uploads that frame as the reference',async()=>{
 const hall={id:'h1',revision:1,name:'Арена',address:'Ярославль',pitch_length_m:40,pitch_width_m:20,ceiling_height_m:null,surface:'',description:'',archived:false};
 const posts:Record<string,unknown>[]=[];const puts:string[]=[];
 vi.stubGlobal('fetch',vi.fn(async(url:unknown,options:RequestInit={})=>{
  const json=(v:unknown,status=200)=>new Response(JSON.stringify(v),{status,headers:{'Content-Type':'application/json'}});
  if(options.method==='POST'){const body=JSON.parse(String(options.body));posts.push(body);return json({...body,id:'c1',version:1},201)}
  if(options.method==='PUT'){puts.push(String(url));expect((options.body as FormData).get('file')).toBeInstanceOf(File);return json({id:'c1'})}
  if(String(url).includes('/camera-profiles'))return json({items:[],total:0});
  return json(hall);
 }));
 render(<MemoryRouter initialEntries={['/halls/h1']}><Routes><Route path="/halls/:id" element={<HallPage/>}/></Routes></MemoryRouter>);
 fireEvent.click(await screen.findByRole('button',{name:'Добавить профиль камеры'}));
 const input=screen.getByText('Загрузить кадр').querySelector('input')!;
 fireEvent.change(input,{target:{files:[new File(['png'],'frame.png',{type:'image/png'})]}});
 expect(await screen.findByRole('status')).toHaveTextContent('Отметьте точку 1: Угол · 0 × 0 м');
 // Кадр 1000×500 показан в 500×250: клик в пикселях экрана переводится в пиксели кадра.
 const stage=screen.getByRole('img',{name:'Разметка точек на кадре'});
 stage.getBoundingClientRect=()=>({left:0,top:0,width:500,height:250,right:500,bottom:250,x:0,y:0,toJSON:()=>null});
 for(const [x,y] of [[0,0],[500,0],[500,250],[0,250]])fireEvent.click(stage,{clientX:x,clientY:y});
 expect(screen.getByRole('status')).toHaveTextContent('Все точки отмечены');
 // Клик, когда все точки отмечены, ничего не перезаписывает.
 fireEvent.click(stage,{clientX:100,clientY:100});
 const centre=landmarks(40,20).findIndex(l=>l.label.startsWith('Центр поля'));
 fireEvent.change(screen.getByLabelText('Добавить точку разметки'),{target:{value:String(centre)}});
 expect(screen.getByRole('status')).toHaveTextContent('Отметьте точку 5: Центр поля · 20 × 10 м');
 fireEvent.click(stage,{clientX:250,clientY:125});
 fireEvent.click(screen.getByRole('button',{name:'Сохранить профиль камеры'}));
 await waitFor(()=>expect(puts).toHaveLength(1));
 expect(posts[0]).toMatchObject({frame_width:1000,frame_height:500,
  points:[{px:[0,0],m:[0,0]},{px:[999,0],m:[40,0]},{px:[999,499],m:[40,20]},{px:[0,499],m:[0,20]},{px:[500,250],m:[20,10]}],
  pitch_polygon_px:[[0,0],[999,0],[999,499],[0,499]]});
 expect(puts[0]).toContain('/halls/h1/camera-profiles/c1/reference-frame');
});

it('names futsal landmarks from the hall size',()=>{
 const marks=landmarks(37.32,17.68);
 expect(marks.map(m=>m.m)).toContainEqual([31.32,8.84]);
 expect(marks.find(m=>m.m[0]===18.66&&m.m[1]===8.84)?.label).toBe('Центр поля · 18,66 × 8,84 м');
});
