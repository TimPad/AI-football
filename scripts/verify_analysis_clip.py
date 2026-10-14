"""Explicit acceptance on the isolated E2E DB, using a real recording.

Creates a clearly labelled demonstration match; never touches organizer data.
The roster labels are review placeholders, not claims about people's identities.
"""
from pathlib import Path
import json
from uuid import uuid4
from sqlalchemy import create_engine, text, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from aifootball.service.config import Settings
from aifootball.service.app import create_app
from aifootball.service.auth.cli import create_admin
from aifootball.service.auth.models import Admin
from aifootball.service.tournaments.schemas import Regulation
from aifootball.processor.job import process_job

root=Path('output/analysis-acceptance');root.mkdir(parents=True,exist_ok=True)
base=Settings();url=make_url(base.database_url).set(database='aifootball_e2e')
assert url.database=='aifootball_e2e'
engine=create_engine(base.database_url,isolation_level='AUTOCOMMIT')
with engine.connect() as db:
    if not db.scalar(text("SELECT 1 FROM pg_database WHERE datname='aifootball_e2e'")):
        db.execute(text('CREATE DATABASE aifootball_e2e'))
engine.dispose()
settings=Settings(database_url=url.render_as_string(hide_password=False),attachment_root=Path('data/service/e2e-attachments'))
cfg=Config('alembic.ini');cfg.attributes['database_url']=settings.database_url;command.upgrade(cfg,'head')
app=create_app(settings)
with Session(app.state.engine) as db:
    admin=db.scalar(select(Admin).where(Admin.login=='e2e-analyst'))
    if not admin:admin=create_admin(db,'e2e-analyst','e2e-only-password')
    admin.can_manage_analytics=True;db.commit()
with TestClient(app,headers={'Origin':settings.allowed_origin}) as client:
    logged=client.post('/api/v1/auth/login',json={'login':'e2e-analyst','password':'e2e-only-password'})
    assert logged.status_code==200,logged.text
    client.headers['X-CSRF-Token']=logged.json()['csrf_token']
    def post(path,body):
        r=client.post('/api/v1'+path,json=body);assert r.status_code in (200,201),r.text;return r.json()
    hall=post('/halls',{'name':'Демо: реальная запись Ярославль','address':'Демонстрационный зал, адрес не установлен',
        'pitch_length_m':37.32,'pitch_width_m':17.68})
    geo=json.loads(Path('configs/venues/yaroslavl/homography.json').read_text())
    lens=json.loads(Path('configs/venues/yaroslavl/calib.json').read_text())
    camera=post(f"/halls/{hall['id']}/camera-profiles",{'name':'Камера записи 2592×1944',
        'expected_hall_revision':hall['revision'],'frame_width':2592,'frame_height':1944,
        'points':[{'px':p['px'],'m':[min(37.32,max(0,p['m'][0])),min(17.68,max(0,p['m'][1]))]} for p in geo['points']],
        'pitch_polygon_px':json.loads(Path('configs/venues/yaroslavl/pitch_polygon.json').read_text())['points_px'],
        'calibration':{k:lens[k] for k in ('K','dist')}})
    t=post('/tournaments',{'name':'Демонстрация импорта реальной записи','season':'2026',
        'starts_on':'2026-10-01','ends_on':'2026-12-31'})
    reg=post(f"/tournaments/{t['id']}/regulations",{'variant_name':'Демо','rules':Regulation().model_dump()})
    entries=[];lineup=[]
    for side,name in [('home','Демо A'),('away','Демо B')]:
        team=post('/teams',{'name':name,'description':'Тестовые обозначения; личности игроков не установлены'})
        entry=post(f"/tournaments/{t['id']}/entries",{'team_id':team['id']});entries.append(entry)
        people=[post('/players',{'name':f'Демо {side} · игрок {n} (личность не установлена)'}) for n in range(1,6)]
        r=client.put(f"/api/v1/entries/{entry['id']}/players",json={'expected_revision':0,'players':[{'player_id':p['id'],'shirt_number':None} for p in people]});assert r.status_code==200,r.text
        lineup.extend({'entry_player_id':p['id'],'side':side} for p in r.json()['players'])
    m=post(f"/tournaments/{t['id']}/matches",{'home_entry_id':entries[0]['id'],'away_entry_id':entries[1]['id'],
        'regulation_id':reg['id'],'scheduled_at':'2026-10-20T18:00:00+03:00','hall_id':hall['id'],'camera_profile_id':camera['id']})
    m=post(f"/matches/{m['id']}/commands",{'request_id':str(uuid4()),'expected_revision':m['revision'],
        'kind':'set_lineup','payload':{'players':lineup}})
    job=post(f"/matches/{m['id']}/analysis/jobs",{'request_id':str(uuid4())})
    r=client.get(f"/api/v1/matches/{m['id']}/analysis/jobs/{job['id']}/package");assert r.status_code==200,r.text
    (root/'job.zip').write_bytes(r.content);(root/'context.json').write_text(json.dumps({'match':m,'job':job},ensure_ascii=False,indent=2))
print('Задание сохранено; начинаем реальную обработку',flush=True)
process_job(root/'job.zip',Path('data/raw/yaroslavl_futsal_n4WAFg0FfV4_60-240.webm'),root/'result.zip',partial_recording=True)
