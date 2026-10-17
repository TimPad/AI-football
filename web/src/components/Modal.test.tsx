import {it,expect} from 'vitest';
import {render,screen,fireEvent} from '@testing-library/react';
import {useState} from 'react';
import {Modal} from './ui';
it('holds keyboard focus and returns it to the opener',()=>{
 function Harness(){const [open,setOpen]=useState(false);return <><button onClick={()=>setOpen(true)}>Открыть</button>{open&&<Modal title="Редактор" onClose={()=>setOpen(false)}><input aria-label="Название"/><button>Готово</button></Modal>}</>}
 render(<Harness/>);const opener=screen.getByText('Открыть');opener.focus();fireEvent.click(opener);
 const close=screen.getByRole('button',{name:'Закрыть'});expect(close).toHaveFocus();
 screen.getByText('Готово').focus();fireEvent.keyDown(document,{key:'Tab'});expect(close).toHaveFocus();
 fireEvent.keyDown(document,{key:'Escape'});expect(opener).toHaveFocus();
});
