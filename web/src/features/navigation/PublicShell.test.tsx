import {it,expect} from 'vitest';
import {render,screen,fireEvent} from '@testing-library/react';
import {MemoryRouter,Routes,Route} from 'react-router-dom';
import {PublicShell} from './PublicShell';
it('offers one sign-in entry that leads to either cabinet',()=>{
 render(<MemoryRouter><Routes><Route element={<PublicShell/>}><Route path="/" element={<p>Главная</p>}/></Route></Routes></MemoryRouter>);
 expect(screen.queryByRole('link',{name:/Кабинет/})).toBeNull();
 const button=screen.getByRole('button',{name:'Войти'});expect(button).toHaveAttribute('aria-expanded','false');
 fireEvent.click(button);expect(button).toHaveAttribute('aria-expanded','true');
 expect(screen.getByRole('link',{name:/Капитан команды/})).toHaveAttribute('href','/captain');expect(screen.getByRole('link',{name:/Организатор/})).toHaveAttribute('href','/tournaments');
 fireEvent.keyDown(document,{key:'Escape'});expect(screen.queryByRole('link',{name:/Организатор/})).toBeNull();
 fireEvent.click(button);fireEvent.pointerDown(screen.getByText('Главная'));expect(screen.queryByRole('link',{name:/Организатор/})).toBeNull();
});
