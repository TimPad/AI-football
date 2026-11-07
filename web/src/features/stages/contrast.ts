// Контраст по WCAG 2.2: относительная яркость sRGB.
export function luminance(hex:string){
 const h=hex.replace('#','');const full=h.length===3?[...h].map(c=>c+c).join(''):h.slice(0,6);
 const [r,g,b]=[0,2,4].map(i=>parseInt(full.slice(i,i+2),16)/255).map(c=>c<=0.03928?c/12.92:((c+0.055)/1.055)**2.4);
 return 0.2126*r+0.7152*g+0.0722*b;
}
export function contrast(a:string,b:string){const [x,y]=[luminance(a),luminance(b)].sort((m,n)=>n-m);return (x+0.05)/(y+0.05)}
