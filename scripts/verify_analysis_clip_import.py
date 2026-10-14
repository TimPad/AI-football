"""Finish the isolated real-clip acceptance; demo UUIDs are not actual identities."""
from pathlib import Path
from uuid import uuid4
import json
from sqlalchemy.engine import make_url
from fastapi.testclient import TestClient
from aifootball.service.app import create_app
from aifootball.service.config import Settings
from aifootball.processor.job import process_job
from aifootball.analytics.exchange import validate_result

root=Path('output/analysis-acceptance')
context=json.loads((root/'context.json').read_text());mid=context['match']['id']
work=next(root.glob('processor-*'))
process_job(root/'job.zip',Path('data/raw/yaroslavl_futsal_n4WAFg0FfV4_60-240.webm'),root/'result.zip',artifacts=work,partial_recording=True)
result=validate_result(root/'result.zip')
base=Settings();url=make_url(base.database_url).set(database='aifootball_e2e')
settings=Settings(database_url=url.render_as_string(hide_password=False),attachment_root=Path('data/service/e2e-attachments'))
assert url.database=='aifootball_e2e'
app=create_app(settings)
with TestClient(app,headers={'Origin':settings.allowed_origin}) as client:
    response=client.post('/api/v1/auth/login',json={'login':'e2e-analyst','password':'e2e-only-password'});assert response.status_code==200,response.text
    client.headers['X-CSRF-Token']=response.json()['csrf_token']
    base_path=f'/api/v1/matches/{mid}/analysis'
    identifier=str(uuid4());raw=(root/'result.zip').read_bytes()
    response=client.post(base_path+'/imports',headers={'X-Request-ID':identifier},files={'file':('result.zip',raw,'application/zip')});assert response.status_code==200,response.text
    run=response.json();again=client.post(base_path+'/imports',headers={'X-Request-ID':identifier},files={'file':('result.zip',raw,'application/zip')});assert again.json()==run
    # Choose continuous goalkeepers by role/team, inspect their original thumbnail separately.
    # This links tracks to explicitly named demonstration roster entries only.
    primary=result.report['periods'][0]
    keepers=[p for p in primary['players'] if p['role']=='goalkeeper']
    assignments=[]
    for side,team in [('home','A'),('away','B')]:
        candidates=[p for p in keepers if p['team']==team];person=next(p for p in run['context']['rosters'] if p['side']==side)
        selected=max(candidates,key=lambda p:p['observed_s'])
        assignments.append({'track_id':selected['track_id'],'player_id':person['player_id']})
    response=client.put(base_path+f"/runs/{run['id']}/assignments",json={'request_id':str(uuid4()),'expected_revision':run['revision'],
        'side_map':{'A':'home','B':'away'},'assignments':assignments});assert response.status_code==200,response.text
    run=response.json()
    for kind in ['confirm','publish']:
        overview=client.get(base_path).json()
        response=client.post(base_path+f"/runs/{run['id']}/{kind}",json={'request_id':str(uuid4()),'expected_revision':run['revision'],
            'expected_analysis_revision':overview['analysis_revision']});assert response.status_code==200,response.text
        run=response.json()
    for person in run['players']:
        history=client.get(f"/api/v1/players/{person['player_id']}/analysis").json()
        assert history['match_count']==1
        assert history['totals']['distance_m']==person['metrics']['distance_m']
    response=client.get(f'/api/v1/public/matches/{mid}/analysis');assert response.status_code==200,response.text
    assert response.json()['partial'] is True
    (root/'accepted.json').write_text(json.dumps({'match_id':mid,'run_id':run['id'],'players':run['players'],
        'checks':run['checks'],'camera_error_m':context['job']['context']['camera'].get('reprojection_error_m')},ensure_ascii=False,indent=2))
    print(f"Real recording imported, demo identities confirmed, histories and publication checked: {mid}")
