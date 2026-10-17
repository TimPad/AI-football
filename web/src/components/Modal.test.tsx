import {it,expect,vi} from 'vitest';
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
it('keeps an inline editor form independent from its surrounding form',()=>{
 const outer=vi.fn(),inner=vi.fn();render(<form onSubmit={e=>{e.preventDefault();outer()}}><input aria-label="Дата матча" defaultValue="2026-10-20"/><Modal title="Создать зал" onClose={()=>{}}><form aria-label="Зал" onSubmit={e=>{e.preventDefault();inner()}}><button>Сохранить зал</button></form></Modal></form>);
 fireEvent.submit(screen.getByRole('form',{name:'Зал'}));expect(inner).toHaveBeenCalledOnce();expect(outer).not.toHaveBeenCalled();expect(screen.getByLabelText('Дата матча')).toHaveValue('2026-10-20');
});
