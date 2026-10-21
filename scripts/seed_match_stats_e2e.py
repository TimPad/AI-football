"""Create a synthetic match with published protocol and reviewed actions ONLY in the dedicated E2E DB.

Never truncates tables. No video, participant images or live VLM calls.
Prints the synthetic resource IDs for Playwright.
"""
import json
import os
import random
from pathlib import Path
from uuid import uuid4
from sqlalchemy.engine import make_url
from fastapi.testclient import TestClient
from aifootball.service.config import Settings
from aifootball.service.app import create_app
from aifootball.service.tournaments.schemas import Regulation

CATEGORIES=('shots','passes','carries','duels','recoveries','shot_blocks','turnovers','saves','distribution','errors')


def seed():
    os.chdir(Path(__file__).resolve().parents[1])
    base=Settings();database=os.environ.get('AIF_E2E_DATABASE_NAME','aifootball_e2e')
    assert database.startswith('aifootball_') and database.endswith('_e2e') and database.replace('_','').isalnum()
    url=make_url(base.database_url).set(database=database)
    assert url.database==database and url.host in ('127.0.0.1','localhost')
    app=create_app(Settings(database_url=url.render_as_string(hide_password=False),attachment_root=Path(f'data/service/{database}-attachments')))
    # Имена уникальны, а числа детерминированы: сценарий E2E проверяет конкретные значения.
    suffix=uuid4().hex[:6];rng=random.Random(20261016)
    with TestClient(app) as client:
        client.headers['Origin']=base.allowed_origin
        auth=client.post('/api/v1/auth/login',json={'login':'e2e-analyst','password':'e2e-only-password'});assert auth.status_code==200
        client.headers['X-CSRF-Token']=auth.json()['csrf_token']
        def call(method,path,body=None):
            response=client.request(method,'/api/v1'+path,json=body)
            assert response.status_code in (200,201),f'{path}: {response.status_code} {response.text}'
            return response.json()
        tournament=call('POST','/tournaments',{'name':f'Демо статистика {suffix}','season':'2026','starts_on':'2026-10-01','ends_on':'2026-11-30','timezone':'Europe/Moscow','visibility':'public'})
        tid=tournament['id'];reg=call('POST',f'/tournaments/{tid}/regulations',{'variant_name':'Основной','rules':Regulation().model_dump(mode='json')})
        hall=call('POST','/halls',{'name':f'Демо арена {suffix}','address':'Синтетический адрес, 1','pitch_length_m':40,'pitch_width_m':20})
        entries=[];lineup=[]
        for side,name in [('home','Север'),('away','Юг')]:
            team=call('POST','/teams',{'name':f'{name} {suffix}'})
            entry=call('POST',f'/tournaments/{tid}/entries',{'team_id':team['id']});entries.append(entry)
            members=[]
            for number in range(1,6):
                player=call('POST','/players',{'name':f'Демо {name} {number}'})
                members.append({'player_id':player['id'],'shirt_number':str(number)})
            roster=call('PUT',f"/entries/{entry['id']}/players",{'expected_revision':0,'players':members})
            lineup.extend({'entry_player_id':p['id'],'side':side} for p in roster['players'])
        m=call('POST',f'/tournaments/{tid}/matches',{'home_entry_id':entries[0]['id'],'away_entry_id':entries[1]['id'],
            'regulation_id':reg['id'],'hall_id':hall['id'],'scheduled_at':'2026-10-05T18:00:00+03:00','stage_label':'Группа A'})
        def command(kind,payload):return call('POST',f"/matches/{m['id']}/commands",{'request_id':str(uuid4()),'expected_revision':m['revision'],'kind':kind,'payload':payload})
        m=command('set_lineup',{'players':lineup})
        players={side:[p['player_id'] for p in m['lineup'] if p['side']==side] for side in ('home','away')}
        def event(kind,side,period,minute,**extra):
            return {'id':str(uuid4()),'kind':kind,'side':side,'period':period,'elapsed_ms':minute*60000,'video_ms':None,**extra}
        goals=[event('goal','home',1,5,player_id=players['home'][1],assist_id=players['home'][2],assist_known=True),
               event('goal','away',1,14,player_id=players['away'][3],assist_known=False),
               event('goal','home',2,7,player_id=players['home'][3],assist_id=players['home'][1],assist_known=True)]
        others=[*(event('foul','home',p,mi,player_id=players['home'][i%5],accumulated=True) for i,(p,mi) in enumerate([(1,3),(1,11),(2,4)])),
                *(event('foul','away',p,mi,player_id=players['away'][i%5],accumulated=True) for i,(p,mi) in enumerate([(1,6),(1,9),(1,17),(2,2),(2,12)])),
                event('card','away',2,12,player_id=players['away'][4],card='yellow'),event('timeout','home',2,15)]
        for e in goals+others:m=command('add_event',{'event':e})
        m=command('set_completeness',{'goals':'complete','assists':'complete','fouls':'complete','cards':'complete'})
        m=command('set_status',{'status':'ended'});m=command('confirm',{'acknowledge_incomplete':True})
        protocol=call('GET',f"/matches/{m['id']}/versions")['items'][0];m=command('publish',{'version_id':protocol['id']})
        doc={'clock_basis':'game','time_basis':'reviewed_effective','analysis_scope':'full_match','duration_ms':2400000,
            'source_protocol_version_id':protocol['id'],'initial_five':{'home':[],'away':[]},'play_intervals':[[0,2400000]],
            'players':[{'player_id':p['player_id'],'presence':[[0,2400000]],'completeness':'complete','appeared':True,
                'roles':[{'role':'goalkeeper' if p['player_id'] in (players['home'][0],players['away'][0]) else 'ala','intervals':[[0,2400000]]}]} for p in m['lineup']]}
        part=call('PUT',f"/matches/{m['id']}/participation",{'request_id':str(uuid4()),'expected_revision':0,'expected_match_revision':m['revision'],'status':'confirmed','document':doc})
        actions=[];links=[]
        def act(kind,side,ms,**extra):
            item={'id':str(uuid4()),'kind':kind,'side':side,'start_ms':ms,'end_ms':ms+500,**extra};actions.append(item);return item
        # Хозяева атакуют вправо (x→40), гости влево (x→0); ворота по центру ширины.
        goal_x={'home':lambda: rng.uniform(28,38),'away':lambda: rng.uniform(2,12)}
        for g in goals:
            ms=((g['period']-1)*1200+g['elapsed_ms']//1000)*1000
            shot=act('shot',g['side'],ms,player_id=g['player_id'],on_target=True,outcome='goal',start_xy=[round(goal_x[g['side']](),1),round(rng.uniform(7,13),1)])
            links.append({'canonical_event_id':g['id'],'source_event_id':shot['id']})
        outcomes=['saved','off_target','failure','off_target','saved']
        for side,count in (('home',9),('away',6)):
            for i in range(count):
                outcome=outcomes[i%len(outcomes)]
                act('shot',side,rng.randrange(0,2400)*1000,player_id=rng.choice(players[side][1:]),on_target=outcome=='saved',
                    outcome=outcome,start_xy=[round(goal_x[side](),1),round(rng.uniform(3,17),1)])
        blocked=next(a for a in actions if a['kind']=='shot' and a['side']=='home' and a['outcome']=='failure')
        act('shot_block','away',blocked['start_ms'],player_id=players['away'][2],shot_id=blocked['id'])
        for side,total,accurate in (('home',74,61),('away',58,44)):
            for i in range(total):act('pass',side,rng.randrange(0,2400)*1000,player_id=rng.choice(players[side]),success=i<accurate if i<total-3 else None)
        for side,won in (('home',11),('away',9)):
            for i in range(20):act('duel',side,rng.randrange(0,2400)*1000,player_id=rng.choice(players[side][1:]),success=i<won)
        for side,n in (('home',12),('away',15)):
            for i in range(n):act('recovery',side,rng.randrange(0,2400)*1000,player_id=rng.choice(players[side][1:]))
        for side,n in (('home',9),('away',11)):
            for i in range(n):act('turnover',side,rng.randrange(0,2400)*1000,player_id=rng.choice(players[side][1:]))
        for side,n in (('home',4),('away',5)):
            for i in range(n):act('save',side,rng.randrange(0,2400)*1000,player_id=players[side][0])
            for i in range(8):act('distribution',side,rng.randrange(0,2400)*1000,player_id=players[side][0],success=i<6)
        actiondoc={'clock_basis':'game','analysis_scope':'full_match','duration_ms':2400000,'source_participation_version_id':part['id'],
            'source_protocol_version_id':protocol['id'],'actions':actions,'links':links,'notes':'PRIVATE-SYNTHETIC-ANNOTATION',
            'completeness':{key:[{'status':'complete'}] for key in CATEGORIES if key!='carries'}}
        saved=call('PUT',f"/matches/{m['id']}/performance-actions",{'request_id':str(uuid4()),'expected_revision':0,'expected_match_revision':m['revision'],'status':'confirmed','document':actiondoc})
        state=call('GET',f'/tournaments/{tid}/analytics')
        call('PUT',f"/matches/{m['id']}/performance-publication",{'request_id':str(uuid4()),'expected_revision':state['revision'],
            'expected_match_revision':m['revision'],'participation_version_id':part['id'],'action_version_id':saved['id'],'approve_policy':True})
        result={'tournament_id':tid,'match_id':m['id'],'home':f'Север {suffix}','away':f'Юг {suffix}'}
    app.state.engine.dispose()
    return result


if __name__=='__main__':print(json.dumps(seed(),ensure_ascii=False))
