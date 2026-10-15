import type {ReactNode} from 'react';
// Статус источника всегда текстом; цвет — только дополнение.
export function SourceStatus({label,detail,tone='neutral',children}:{label:string;detail?:string;
 tone?:'neutral'|'ok'|'warn'|'error';children?:ReactNode}){
 return <div className={`source-status source-${tone}`} role="status"><b>{label}</b>{detail&&<span>{detail}</span>}{children}</div>;
}
