"""Seed synthetic understanding through the dedicated localhost E2E API only."""
import argparse
import os
import json
from pathlib import Path
import sys
from uuid import uuid4
import httpx

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from test_understanding_exchange import result_v2

parser=argparse.ArgumentParser();parser.add_argument('--review',action='store_true');args=parser.parse_args()
base_url='http://127.0.0.1:'+str(int(os.environ.get('AIF_E2E_PORT','8181')))
if not os.environ.get('AIF_E2E_DATABASE_NAME','aifootball_e2e').endswith('_e2e'):raise SystemExit('Dedicated E2E database required')
with httpx.Client(base_url=base_url,trust_env=False,timeout=30) as client:
    response=client.post('/api/v1/auth/login',json={'login':'e2e-analyst','password':'e2e-only-password'},headers={'Origin':base_url})
    response.raise_for_status();client.headers.update({'Origin':base_url,'X-CSRF-Token':response.json()['csrf_token']})
    def call(path,data,method='POST'):
        response=client.request(method,'/api/v1'+path,json=data)
        if not response.is_success:raise RuntimeError(f'E2E seed failed: {path} ({response.status_code})')
        return response.json()
    suffix=uuid4().hex[:6]
    hall=call('/halls',{'name':f'Демо CV {suffix}','address':'Синтетический адрес','pitch_length_m':40,'pitch_width_m':20})
    camera=call(f"/halls/{hall['id']}/camera-profiles",{'name':'Тестовая камера','expected_hall_revision':hall['revision'],
        'frame_width':1000,'frame_height':500,'points':[{'px':[0,0],'m':[0,0]},{'px':[999,0],'m':[40,0]},
        {'px':[999,499],'m':[40,20]},{'px':[0,499],'m':[0,20]}],'pitch_polygon_px':[[0,0],[999,0],[999,499],[0,499]]})
    tournament=call('/tournaments',{'name':f'Проверка эпизодов {suffix}','season':'2026','starts_on':'2026-10-01','ends_on':'2026-12-31'})
    regulation=call(f"/tournaments/{tournament['id']}/regulations",{'variant_name':'Демо','rules':{}})
    entries=[];lineup=[];players=[]
    for side,label in [('home','Север'),('away','Юг')]:
        team=call('/teams',{'name':f'{label} {suffix}'})
        entry=call(f"/tournaments/{tournament['id']}/entries",{'team_id':team['id']});entries.append(entry)
        player=call('/players',{'name':f'Демо {label} {suffix}'});players.append(player)
        roster=call(f"/entries/{entry['id']}/players",{'expected_revision':0,'players':[{'player_id':player['id'],'shirt_number':'7'}]},'PUT')
        lineup.extend({'entry_player_id':person['id'],'side':side} for person in roster['players'])
    match=call(f"/tournaments/{tournament['id']}/matches",{'home_entry_id':entries[0]['id'],'away_entry_id':entries[1]['id'],
        'regulation_id':regulation['id'],'scheduled_at':'2026-10-20T18:00:00+03:00','hall_id':hall['id'],'camera_profile_id':camera['id']})
    match=call(f"/matches/{match['id']}/commands",{'request_id':str(uuid4()),'expected_revision':match['revision'],'kind':'set_lineup','payload':{'players':lineup}})
    job=call(f"/matches/{match['id']}/analysis/jobs",{'request_id':str(uuid4())})
    def observations(manifest,document):
        document['observations']=[{'track_id':1,'video_ms':1000,'role':'player','number':'7','team':'A','evidence_ids':['f1'],'visible_features':[],'limitations':['Синтетическая запись']}]
    response=client.post(f"/api/v1/matches/{match['id']}/analysis/imports",files={'file':('result.zip',result_v2(job,mutate=observations),'application/zip')},headers={'X-Request-ID':str(uuid4())})
    response.raise_for_status();run=response.json()
    if args.review:
        call(f"/matches/{match['id']}/analysis/runs/{run['id']}/understanding/reviews",{'request_id':str(uuid4()),
            'expected_revision':0,'event_id':'e1','decision':'accepted','correction':None,'reason':'Синтетическая проверка backup'},'PUT')
    print(json.dumps({'match_id':match['id'],'run_id':run['id'],'tournament_id':tournament['id'],
                      'home_player_id':players[0]['id'],'away_player_id':players[1]['id']},ensure_ascii=False))
