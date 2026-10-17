import {afterEach,it,expect,vi} from 'vitest';
import {useState} from 'react';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import {AddressField,type AddressValue} from './AddressField';
afterEach(()=>vi.unstubAllGlobals());
it('selects with the keyboard without submitting and clears the old point when typing',async()=>{
 const submit=vi.fn(),changes:AddressValue[]=[];
 vi.stubGlobal('fetch',vi.fn(async input=>new Response(JSON.stringify(String(input).includes('address-resolution')?{address:'Город, Спортивная, 1',latitude:57.62,longitude:39.88,address_selection_token:'signed'}:{available:true,items:[{id:'suggestion',title:'Арена',subtitle:'Город',address:'Город, Спортивная, 1'}]}))));
 function Harness(){const [value,setValue]=useState<AddressValue>({address:'',latitude:null,longitude:null,selectionToken:null,source:'manual'});return <form onSubmit={e=>{e.preventDefault();submit()}}><AddressField value={value} onChange={v=>{changes.push(v);setValue(v)}}/></form>}
 render(<Harness/>);const input=screen.getByRole('combobox',{name:'Адрес зала'});fireEvent.change(input,{target:{value:'Спортивная'}});await screen.findByRole('option',{name:/Арена/});
 fireEvent.keyDown(input,{key:'ArrowDown'});fireEvent.keyDown(input,{key:'Enter'});await waitFor(()=>expect(input).toHaveValue('Город, Спортивная, 1'));expect(submit).not.toHaveBeenCalled();expect(changes.at(-1)).toMatchObject({latitude:57.62,selectionToken:'signed',source:'yandex'});
 fireEvent.change(input,{target:{value:'Другой адрес'}});expect(changes.at(-1)).toMatchObject({latitude:null,longitude:null,selectionToken:null,source:'manual'});
});
it('ignores a late response for the old query',async()=>{
 let release:((r:Response)=>void)|undefined;
 vi.stubGlobal('fetch',vi.fn(async input=>String(input).includes('old')?new Promise<Response>(r=>{release=r}):new Response(JSON.stringify({available:true,items:[{id:'new',title:'Новая улица',subtitle:'Город',address:'Город, Новая'}]}))));
 function Harness(){const [value,setValue]=useState<AddressValue>({address:'',latitude:null,longitude:null,selectionToken:null,source:'manual'});return <AddressField value={value} onChange={setValue}/>}
 render(<Harness/>);fireEvent.change(screen.getByRole('combobox'),{target:{value:'old'}});await waitFor(()=>expect(release).toBeDefined());fireEvent.change(screen.getByRole('combobox'),{target:{value:'new'}});await screen.findByRole('option',{name:/Новая улица/});release!(new Response(JSON.stringify({available:true,items:[{id:'old',title:'Старая улица'}]})));await waitFor(()=>expect(screen.queryByText('Старая улица')).not.toBeInTheDocument());
});
