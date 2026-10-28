import {describe,expect,it} from 'vitest';
import {render,screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MemoryRouter} from 'react-router-dom';
import {GroupTable} from './GroupTable';
import {Bracket} from './Bracket';
import {group,row,sections} from './fixtures.test-data';
import {criteriaText} from './labels';

describe('таблица и сетка',()=>{
 it('раскрывает строку и подписывает критерии одной фразой',async()=>{
  render(<MemoryRouter><GroupTable group={group} criteria={['points','h2h_points','h2h_goal_diff','goal_diff','lot']} advanceNote="Отмеченные команды выходят в плей-офф"/></MemoryRouter>);
  expect(screen.getByText('Места: очки → личные встречи → разница мячей → жребий')).toBeInTheDocument();
  expect(screen.getByText('Отмеченные команды выходят в плей-офф')).toBeInTheDocument();
  const toggle=screen.getByRole('button',{name:'Север'});
  expect(toggle).toHaveAttribute('aria-expanded','false');
  await userEvent.click(toggle);
  expect(toggle).toHaveAttribute('aria-expanded','true');
  expect(screen.getByText('В 2 · Н 0 · П 1 · Мячи 7:3')).toBeInTheDocument();
  expect(screen.getAllByRole('row')[1]).toHaveAttribute('data-zone','advance');
 });
 it('просит жребий при равенстве',()=>{
  render(<MemoryRouter><GroupTable group={{...group,needs_lot:true,rows:[row('Север',1,null,true),row('Юг',1,null,true)]}} criteria={['points','lot']}/></MemoryRouter>);
  expect(screen.getByRole('status')).toHaveTextContent('Нужен жребий');
 });
 it('открывает текущий раунд, переключает раунды стрелками и показывает пары без даты',async()=>{
  render(<MemoryRouter><Bracket sections={sections} timezone="Europe/Moscow" matchHref={id=>`/watch/matches/${id}`} wide={false}/></MemoryRouter>);
  const final=screen.getByRole('tab',{name:'Финал'});
  expect(final).toHaveAttribute('aria-selected','true');
  expect(screen.getByRole('article',{name:/^Финал\. Север — Победитель пары 2\. Матч: дата не назначена$/})).toHaveTextContent('Дата не назначена');
  final.focus();await userEvent.keyboard('{ArrowLeft}');
  expect(screen.getByRole('tab',{name:'Полуфинал'})).toHaveAttribute('aria-selected','true');
  expect(screen.getByRole('tab',{name:'Полуфинал'})).toHaveFocus();
 });
 it('пишет швейцарские критерии понятными словами',()=>{
  expect(criteriaText(['points','buchholz','goal_diff'])).toBe('Места: очки → очки соперников → разница мячей');
 });
});
