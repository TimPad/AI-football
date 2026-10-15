import {describe,expect,it,vi} from 'vitest';
import {render,screen} from '@testing-library/react';
import {PitchMap} from './PitchMap';

const base={lengthM:41,widthM:15.5,orientation:'camera',maxSeconds:12,scaleLabel:'суммарное время игроков'};

describe('PitchMap',()=>{
 it('draws real pitch geometry with an external seconds legend',()=>{
  const fetch=vi.fn();vi.stubGlobal('fetch',fetch);
  const {container}=render(<PitchMap {...base} cells={[[0,12],[6,0]]} label="Север"/>);
  const svg=container.querySelector('svg')!;
  expect(svg.getAttribute('viewBox')).toBe('0 0 41 15.5');
  expect(container.querySelectorAll('rect.heat-cell')).toHaveLength(2);
  expect(screen.getByText('0 — 12 с · суммарное время игроков')).toBeInTheDocument();
  expect(screen.getByRole('img',{name:/Север/})).toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalled();
  vi.unstubAllGlobals();
 });
 it.each([
  ['all zero',[[0,0],[0,0]],'Нет наблюдений'],
  ['null',null,'Карта недоступна'],
  ['ragged',[[1,2],[3]],'Карта недоступна'],
  ['negative',[[1,-2]],'Карта недоступна'],
  ['nonfinite',[[1,Number.POSITIVE_INFINITY]],'Карта недоступна'],
 ])('%s cells draw no colored map',(_name,cells,text)=>{
  const {container}=render(<PitchMap {...base} cells={cells as number[][]|null}/>);
  expect(screen.getByText(text)).toBeInTheDocument();
  expect(container.querySelectorAll('rect.heat-cell')).toHaveLength(0);
 });
 it('does not draw when the shared scale is empty',()=>{
  const {container}=render(<PitchMap {...base} maxSeconds={0} cells={[[1]]}/>);
  expect(screen.getByText('Нет наблюдений')).toBeInTheDocument();
  expect(container.querySelectorAll('rect.heat-cell')).toHaveLength(0);
 });
 it('labels unknown orientation without mirroring',()=>{
  const {container}=render(<PitchMap {...base} orientation="attack" cells={[[3,0]]}/>);
  expect(screen.getByText('Ориентация не задана')).toBeInTheDocument();
  const cell=container.querySelector('rect.heat-cell')!;
  expect(cell.getAttribute('x')).toBe('0');
 });
});
