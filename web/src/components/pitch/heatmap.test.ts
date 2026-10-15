import {describe,expect,it} from 'vitest';
import {heatCellOpacity,sharedHeatmapMax,validMatrix} from './heatmap';

describe('heatmap scale',()=>{
 it('compares both teams on one scale and leaves zero neutral',()=>{
  expect(sharedHeatmapMax([[[0,2]],[[0,12]]])).toBe(12);
  expect(heatCellOpacity(0,12)).toBe(0);
  expect(heatCellOpacity(12,12)).toBe(1);
  expect(heatCellOpacity(6,12)).toBe(0.5);
  expect(sharedHeatmapMax([null,[[0,0]]])).toBe(0);
 });
 it('rejects invalid matrices as a whole',()=>{
  expect(validMatrix([[1,2],[3]])).toBeNull();
  expect(validMatrix([[1,-1]])).toBeNull();
  expect(validMatrix([[1,Number.NaN]])).toBeNull();
  expect(validMatrix([[1,Infinity]])).toBeNull();
  expect(validMatrix([])).toBeNull();
  expect(validMatrix([[]])).toBeNull();
  expect(validMatrix(null)).toBeNull();
  expect(validMatrix([[0,1]])).toEqual([[0,1]]);
  expect(sharedHeatmapMax([[[1,Infinity]],[[0,3]]])).toBe(3);
  expect(heatCellOpacity(Number.NaN,3)).toBe(0);
  expect(heatCellOpacity(5,0)).toBe(0);
 });
});
