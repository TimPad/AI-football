import {describe,expect,it,vi} from 'vitest';
import {useState} from 'react';
import {render,screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {PlayerInspector} from './PlayerInspector';
import {SectionNavigation} from './SectionNavigation';
import {SourceStatus} from './SourceStatus';

function Harness(){
 const [open,setOpen]=useState(false);
 return <><button onClick={()=>setOpen(true)}>Игрок 01</button><button>Другая строка</button>
  {open&&<PlayerInspector title="Игрок 01" onClose={()=>setOpen(false)}><a href="#h">История турнира</a></PlayerInspector>}</>;
}

describe('PlayerInspector',()=>{
 it('moves focus inside, traps Tab while modal, closes on Escape and returns focus',async()=>{
  const fetch=vi.fn();vi.stubGlobal('fetch',fetch);
  vi.stubGlobal('matchMedia',vi.fn(()=>({matches:true,addEventListener(){},removeEventListener(){}})));
  const user=userEvent.setup();
  render(<Harness/>);
  const trigger=screen.getByRole('button',{name:'Игрок 01'});
  await user.click(trigger);
  const dialog=screen.getByRole('dialog',{name:'Игрок 01'});
  expect(dialog).toHaveAttribute('aria-modal','true');
  const close=screen.getByRole('button',{name:'Закрыть карточку игрока'});
  expect(close).toHaveFocus();
  await user.tab();
  expect(screen.getByRole('link',{name:'История турнира'})).toHaveFocus();
  await user.tab();
  expect(close).toHaveFocus();
  await user.keyboard('{Escape}');
  expect(screen.queryByRole('dialog')).toBeNull();
  expect(trigger).toHaveFocus();
  expect(fetch).not.toHaveBeenCalled();
  vi.unstubAllGlobals();
 });
 it('stays a labeled non-modal panel on desktop',async()=>{
  vi.stubGlobal('matchMedia',vi.fn(()=>({matches:false,addEventListener(){},removeEventListener(){}})));
  const user=userEvent.setup();
  render(<Harness/>);
  await user.click(screen.getByRole('button',{name:'Игрок 01'}));
  const panel=screen.getByRole('dialog',{name:'Игрок 01'});
  expect(panel).not.toHaveAttribute('aria-modal');
  await user.tab();await user.tab();
  expect(panel.contains(document.activeElement)).toBe(false);
  vi.unstubAllGlobals();
 });
});

describe('navigation and status',()=>{
 it('marks the selected section and reports status as text',async()=>{
  const onSelect=vi.fn();const user=userEvent.setup();
  render(<><SectionNavigation label="Разделы матча" items={[{id:'overview',label:'Обзор'},{id:'stats',label:'Статистика'}]} selected="stats" onSelect={onSelect}/>
   <SourceStatus label="Протокол ещё не опубликован" detail="Версия появится после публикации"/></>);
  expect(screen.getByRole('link',{name:'Статистика'})).toHaveAttribute('aria-current','page');
  expect(screen.getByRole('link',{name:'Обзор'})).not.toHaveAttribute('aria-current');
  await user.click(screen.getByRole('link',{name:'Обзор'}));
  expect(onSelect).toHaveBeenCalledWith('overview');
  expect(screen.getByRole('status')).toHaveTextContent('Протокол ещё не опубликован');
 });
});
