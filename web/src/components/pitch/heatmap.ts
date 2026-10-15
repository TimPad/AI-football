// Матрица heatmap_s: [ячейка по длине][ячейка по ширине], секунды наблюдения.
export function validMatrix(cells:readonly (readonly number[])[]|null|undefined):number[][]|null{
 if(!Array.isArray(cells)||!cells.length)return null;
 const width=Array.isArray(cells[0])?cells[0].length:0;
 if(!width)return null;
 for(const row of cells){
  if(!Array.isArray(row)||row.length!==width)return null;
  for(const v of row)if(typeof v!=='number'||!Number.isFinite(v)||v<0)return null;
 }
 return cells.map(row=>[...row]);
}

export function sharedHeatmapMax(maps:readonly (readonly (readonly number[])[]|null)[]):number{
 let max=0;
 for(const map of maps){const valid=validMatrix(map);if(valid)for(const row of valid)for(const v of row)max=Math.max(max,v);}
 return max;
}

export function heatCellOpacity(seconds:number,max:number):number{
 return max>0&&Number.isFinite(seconds)&&seconds>0?Math.min(1,seconds/max):0;
}
