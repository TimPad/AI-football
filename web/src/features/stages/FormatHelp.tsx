import {useState} from 'react';
import {CircleHelp} from 'lucide-react';
import {Modal} from '../../components/ui';
import {FORMAT_GUIDE,TEMPLATE_NAME} from './labels';

export function FormatHelp(){
 const [open,setOpen]=useState(false);
 return <><button type="button" className="quiet help-button" onClick={()=>setOpen(true)}><CircleHelp aria-hidden="true"/>Как выбрать формат</button>
  {open&&<Modal title="Как выбрать формат" sheet onClose={()=>setOpen(false)}>
   <dl className="format-guide">{Object.entries(FORMAT_GUIDE).map(([id,g])=><div key={id}><dt>{TEMPLATE_NAME[id]}</dt>
    <dd><b>Подходит:</b> {g.fits}</dd><dd><b>Плюс:</b> {g.pros}</dd><dd><b>Минус:</b> {g.cons}</dd></div>)}</dl>
   <button type="button" className="primary" onClick={()=>setOpen(false)}>Готово</button></Modal>}</>;
}
