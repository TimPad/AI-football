import {it,expect,vi} from 'vitest';
import {render,screen,fireEvent} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {MatchInfo} from './MatchPage';
import type {Match,DraftCommand} from '../../api/domain';
vi.mock('../../api/client',()=>({api:vi.fn(async()=>({timezone:'Europe/Moscow'})),all:vi.fn(async()=>[]),post:vi.fn(),errorText:(e:Error)=>e.message}));
it('allows unrelated information changes on a legacy match without assigning an empty hall UUID',async()=>{
 const match={id:'old',tournament_id:'cup',hall_id:null,hall_snapshot:null,camera_profile_id:null,
  scheduled_at:'2026-10-20T16:00:00Z',venue_label:'Старый зал',referees:[],status:'scheduled',
  broadcast_url:null,broadcast_embed_url:null,regulation_override:null,override_reason:null,
  protocol:{draft:true},regulation:{variant_name:'Обычный',version:1}} as unknown as Match;
 const dispatch=vi.fn(async(_command:DraftCommand)=>{});
 render(<MemoryRouter><MatchInfo match={match} dispatch={dispatch}/></MemoryRouter>);
 expect(await screen.findByLabelText('Зал')).not.toBeRequired();
 fireEvent.change(screen.getByLabelText('Судьи, через запятую'),{target:{value:'Иванов'}});
 fireEvent.click(screen.getByRole('button',{name:'Сохранить информацию'}));
 expect(dispatch).toHaveBeenCalledWith(expect.objectContaining({kind:'update_match',payload:expect.objectContaining({referees:['Иванов']})}));
 const payload=dispatch.mock.calls[0][0].payload;
 expect(payload).not.toHaveProperty('hall_id');expect(payload).not.toHaveProperty('camera_profile_id');
});
