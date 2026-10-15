"""Create a fresh synthetic ratings tournament ONLY in the dedicated E2E DB.

Never truncates tables. No video, participant images or live VLM calls.
Prints the synthetic resource IDs for Playwright.
"""
import json
import os
from pathlib import Path
from uuid import uuid4
from sqlalchemy.engine import make_url
from fastapi.testclient import TestClient
from aifootball.service.config import Settings
from aifootball.service.app import create_app
from aifootball.service.tournaments.schemas import Regulation


def seed():
    os.chdir(Path(__file__).resolve().parents[1])
    base=Settings();url=make_url(base.database_url).set(database='aifootball_e2e')
    assert url.database=='aifootball_e2e' and url.host in ('127.0.0.1','localhost')
    app=create_app(Settings(database_url=url.render_as_string(hide_password=False),attachment_root=Path('data/service/e2e-attachments')))
    suffix=uuid4().hex[:6]
    with TestClient(app) as client:
        client.headers['Origin']=base.allowed_origin
        auth=client.post('/api/v1/auth/login',json={'login':'e2e-analyst','password':'e2e-only-password'});assert auth.status_code==200
        client.headers['X-CSRF-Token']=auth.json()['csrf_token']
        def call(method,path,body=None):
            response=client.request(method,'/api/v1'+path,json=body)
            assert response.status_code in (200,201),f'{path}: {response.status_code} {response.text}'
            return response.json()
        tournament=call('POST','/tournaments',{'name':f'Демо рейтинг {suffix}','season':'2026','starts_on':'2026-10-01','ends_on':'2026-11-30','timezone':'Europe/Moscow'})
        tid=tournament['id'];reg=call('POST',f'/tournaments/{tid}/regulations',{'variant_name':'Основной','rules':Regulation().model_dump(mode='json')})
        hall=call('POST','/halls',{'name':f'Демо арена {suffix}','address':'Синтетический адрес, 1','pitch_length_m':42,'pitch_width_m':18})
        entries=[];lineup=[];players=[]
        for side,name in [('home','Альфа'),('away','Бета')]:
            team=call('POST','/teams',{'name':f'{name} {suffix}'})
            entry=call('POST',f'/tournaments/{tid}/entries',{'team_id':team['id']});entries.append(entry)
            members=[]
            for number in range(1,4):
                player=call('POST','/players',{'name':f'Демо {name} {number} {suffix}'});players.append(player)
                members.append({'player_id':player['id'],'shirt_number':str(number)})
            roster=call('PUT',f"/entries/{entry['id']}/players",{'expected_revision':0,'players':members})
            lineup.extend({'entry_player_id':p['id'],'side':side} for p in roster['players'])
        matches=[]
        for index in range(4):
            m=call('POST',f'/tournaments/{tid}/matches',{'home_entry_id':entries[0]['id'],'away_entry_id':entries[1]['id'],
                'regulation_id':reg['id'],'hall_id':hall['id'],'scheduled_at':f'2026-10-0{index+1}T18:00:00+03:00','stage_label':'Группа A'})
            def command(kind,payload):return call('POST',f"/matches/{m['id']}/commands",{'request_id':str(uuid4()),'expected_revision':m['revision'],'kind':kind,'payload':payload})
            m=command('set_lineup',{'players':lineup});m=command('set_completeness',{'goals':'complete','assists':'complete','fouls':'complete','cards':'complete'})
            m=command('set_status',{'status':'ended'});m=command('confirm',{'acknowledge_incomplete':True})
            protocol=call('GET',f"/matches/{m['id']}/versions")['items'][0];m=command('publish',{'version_id':protocol['id']})
            doc={'clock_basis':'game','time_basis':'reviewed_effective','analysis_scope':'full_match','duration_ms':2400000,
                'source_protocol_version_id':protocol['id'],'initial_five':{'home':[],'away':[]},'play_intervals':[[0,2400000]],
                'players':[{'player_id':p['player_id'],'presence':[[0,600000]],'completeness':'complete','appeared':True,
                    'roles':[{'role':'ala','intervals':[[0,600000]]}]} for p in m['lineup']]}
            part=call('PUT',f"/matches/{m['id']}/participation",{'request_id':str(uuid4()),'expected_revision':0,'expected_match_revision':m['revision'],'status':'confirmed','document':doc})
            actiondoc={'clock_basis':'game','analysis_scope':'full_match','duration_ms':2400000,'source_participation_version_id':part['id'],
                'actions':[],'notes':'PRIVATE-SYNTHETIC-ANNOTATION','completeness':{key:[{'status':'complete'}] for key in ('shots','passes','carries','duels','recoveries','shot_blocks','turnovers','saves','distribution','errors')}}
            actions=call('PUT',f"/matches/{m['id']}/performance-actions",{'request_id':str(uuid4()),'expected_revision':0,'expected_match_revision':m['revision'],'status':'confirmed','document':actiondoc})
            state=call('GET',f'/tournaments/{tid}/analytics')
            call('PUT',f"/matches/{m['id']}/performance-publication",{'request_id':str(uuid4()),'expected_revision':state['revision'],
                'expected_match_revision':m['revision'],'participation_version_id':part['id'],'action_version_id':actions['id'],'approve_policy':True})
            matches.append(m)
        state=call('GET',f'/tournaments/{tid}/analytics')
        snapshot=call('POST',f'/tournaments/{tid}/analytics/calculate',{'request_id':str(uuid4()),'expected_revision':state['revision'],'cutoff':'2026-10-14T23:59:59Z'})
        result={'tournament_id':tid,'match_id':matches[0]['id'],'player_id':players[0]['id'],'player_name':players[0]['name'],'snapshot_id':snapshot['snapshot_id']}
    app.state.engine.dispose()
    return result


if __name__=='__main__':print(json.dumps(seed(),ensure_ascii=False))
