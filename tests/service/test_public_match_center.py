from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from aifootball.service.matches.models import Match
from .test_confirmation import finish

URL='/api/v1/public/matches'

def test_moscow_day_groups_and_narrow_results(admin_client,match_factory,send_command):
    m=match_factory(scheduled_at='2026-10-19T21:00:00Z')
    second=match_factory(scheduled_at='2026-10-20T20:59:59Z')
    match_factory(scheduled_at='2026-10-20T21:00:00Z')
    data=admin_client.get(URL+'?day=2026-10-20').json()
    assert data['timezone']=='Europe/Moscow'
    assert data['total']==2 and len(data['tournament_totals'])==2
    assert {x['id'] for x in data['items']}=={m['id'],second['id']}
    assert all(x['score']=={'home':None,'away':None} for x in data['items'])
    assert not {'clock','lineup','notes','revision'}&data['items'][0].keys()
    # Two tournaments with identical names remain separate.
    assert data['items'][0]['tournament']['id']!=data['items'][1]['tournament']['id']

def test_hidden_counts_search_and_upcoming(admin_client,match_factory,monkeypatch):
    from aifootball.service import public_match_center as center
    monkeypatch.setattr(center,'now',lambda:datetime(2026,10,20,10,tzinfo=timezone.utc))
    m=match_factory(scheduled_at='2026-10-20T18:00:00Z')
    hidden=match_factory(scheduled_at='2026-10-20T19:00:00Z')
    admin_client.patch('/api/v1/tournaments/'+hidden['tournament_id'],json={'expected_revision':0,'visibility':'draft'})
    match_factory(scheduled_at='2026-10-19T18:00:00Z')
    match_factory(scheduled_at='2026-11-10T18:00:00Z')
    day=admin_client.get(URL+'?day=2026-10-20&q=Север').json()
    assert day['total']==1 and list(day['tournament_totals'])==[m['tournament_id']]
    upcoming=admin_client.get(URL+'/upcoming').json()
    assert [x['id'] for x in upcoming['items']]==[m['id']]
    assert admin_client.get(URL+f"?day=2026-10-20&team_id={m['home']['team_id']}").json()['total']==1
    assert admin_client.get(URL+'?day=2026-10-20&q=несуществующий').json()['total']==0

def test_public_score_and_status_filters(admin_client,match_factory,send_command):
    m=finish(send_command,match_factory())
    m=send_command(m,'confirm',{'acknowledge_incomplete':True}).json()
    version=admin_client.get(f"/api/v1/matches/{m['id']}/versions").json()['items'][0]
    m=send_command(m,'publish',{'version_id':version['id']}).json()
    m=send_command(m,'reopen',{}).json()
    send_command(m,'set_totals',{'reported_totals':{'home':{'score':99},'away':{'score':0}}})
    item=admin_client.get(URL+'?day=2026-10-20').json()['items'][0]
    assert item['score']=={'home':3,'away':2}
    assert admin_client.get(URL+'?day=2026-10-20&status=finished').json()['total']==1
    assert admin_client.get(URL+'?day=2026-10-20&status=live').json()['total']==0

def test_keyset_pages_group_counts_and_filter_binding(admin_client,match_factory):
    m=match_factory()
    with Session(admin_client.app.state.engine) as db,db.begin():
        original=db.get(Match,m['id'])
        values={c.key:getattr(original,c.key) for c in Match.__table__.columns if c.key not in {'id','created_at','updated_at'}}
        for i in range(119):
            db.add(Match(**{**values,'scheduled_at':original.scheduled_at+timedelta(seconds=i+1)}))
    cursor=None;ids=[]
    for expected in [50,50,20]:
        response=admin_client.get(URL,params={'day':'2026-10-20',**({'cursor':cursor} if cursor else {})})
        assert response.status_code==200,response.text
        data=response.json();assert len(data['items'])==expected and data['total']==120
        assert data['tournament_totals'][m['tournament_id']]==120
        ids.extend(x['id'] for x in data['items']);cursor=data['next_cursor']
        if cursor:assert admin_client.get(URL,params={'day':'2026-10-21','cursor':cursor}).status_code==422
    assert cursor is None and len(set(ids))==120
    assert admin_client.get(URL+'?limit=1000').status_code==422
    assert admin_client.get(URL+'?day=bad').status_code==422
    assert admin_client.get(URL+'?cursor=broken').status_code==422

def test_neighbour_game_days_follow_filters(admin_client,match_factory):
    before=match_factory(scheduled_at='2026-10-16T21:30:00Z')
    after=match_factory(scheduled_at='2026-10-25T18:00:00Z')
    hidden=match_factory(scheduled_at='2026-10-18T18:00:00Z')
    admin_client.patch('/api/v1/tournaments/'+hidden['tournament_id'],json={'expected_revision':0,'visibility':'draft'})
    data=admin_client.get(URL+'?day=2026-10-20').json()
    # 16 Oct 21:30 UTC is already 17 Oct in Moscow; a hidden tournament is not a game day.
    assert data['total']==0 and data['previous_day']=='2026-10-17' and data['next_day']=='2026-10-25'
    only=admin_client.get(URL+f"?day=2026-10-20&tournament_id={after['tournament_id']}").json()
    assert only['previous_day'] is None and only['next_day']=='2026-10-25'
    assert admin_client.get(URL+'?day=2026-10-17').json()['previous_day'] is None
    assert before['id']

def test_recent_results_newest_first(admin_client,match_factory,send_command,monkeypatch):
    from aifootball.service import public_match_center as center
    monkeypatch.setattr(center,'now',lambda:datetime(2026,10,26,10,tzinfo=timezone.utc))
    old=finish(send_command,match_factory(scheduled_at='2026-10-10T18:00:00Z'))
    new=finish(send_command,match_factory(scheduled_at='2026-10-20T18:00:00Z'))
    match_factory(scheduled_at='2026-10-21T18:00:00Z')
    hidden=finish(send_command,match_factory(scheduled_at='2026-10-22T18:00:00Z'))
    admin_client.patch('/api/v1/tournaments/'+hidden['tournament_id'],json={'expected_revision':0,'visibility':'draft'})
    recent=admin_client.get(URL+'/recent').json()
    assert [x['id'] for x in recent['items']]==[new['id'],old['id']]
    assert [x['id'] for x in admin_client.get(URL+f"/recent?tournament_id={old['tournament_id']}").json()['items']]==[old['id']]
    assert admin_client.get(URL+'/recent?limit=6').status_code==422
