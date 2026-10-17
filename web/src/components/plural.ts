// Число со словом в нужной форме: 1 матч, 2 матча, 5 матчей, 21 матч, 11 матчей.
export function plural(n:number,[one,few,many]:[string,string,string]):string{
 const tens=n%100,units=n%10;
 const word=tens>=11&&tens<=14?many:units===1?one:units>=2&&units<=4?few:many;
 return `${n} ${word}`;
}
