from uuid import uuid4
from .test_analysis_jobs import analytics_match,grant
from .test_events import event
from .test_ratings_snapshots import publish_sources


def _setup(client,match,send,actions,completeness):
    """Протокол с одним голом, подтверждённые участие и действия с заданными записями."""
    home=[p['player_id'] for p in match['lineup'] if p['side']=='home'];away=[p['player_id'] for p in match['lineup'] if p['side']=='away']
    goal=event(player_id=home[0],assist_known=True,elapsed_ms=300000)
    for kind,payload in [('add_event',{'event':goal}),('set_completeness',{'goals':'complete','assists':'complete','fouls':'complete','cards':'complete'}),
        ('set_status',{'status':'ended'}),('confirm',{'acknowledge_incomplete':True})]:
        response=send(match,kind,payload);assert response.status_code==200,response.text;match=response.json()
    protocol=client.get(f"/api/v1/matches/{match['id']}/versions").json()['items'][0]
    doc={'clock_basis':'game','time_basis':'reviewed_effective','analysis_scope':'full_match','duration_ms':2400000,
        'source_protocol_version_id':protocol['id'],'initial_five':{'home':[],'away':[]},'play_intervals':[[0,2400000]],
        'players':[{'player_id':p['player_id'],'presence':[[0,2400000]],'roles':[{'role':'ala','intervals':[[0,2400000]]}],
            'completeness':'complete','appeared':True} for p in match['lineup']]}
    part=client.put(f"/api/v1/matches/{match['id']}/participation",json={'request_id':str(uuid4()),'expected_revision':0,
        'expected_match_revision':match['revision'],'status':'confirmed','document':doc});assert part.status_code==200,part.text
    adoc={'clock_basis':'game','analysis_scope':'full_match','duration_ms':2400000,'source_participation_version_id':part.json()['id'],
        'source_protocol_version_id':protocol['id'],'actions':actions(home,away),'completeness':completeness}
    saved=client.put(f"/api/v1/matches/{match['id']}/performance-actions",json={'request_id':str(uuid4()),'expected_revision':0,
        'expected_match_revision':match['revision'],'status':'confirmed','document':adoc});assert saved.status_code==200,saved.text
    return match,protocol,part.json(),saved.json()


def _actions(home,away):
    shot=lambda **c:{'id':str(uuid4()),'kind':'shot','player_id':home[1],'side':'home','start_ms':60000,**c}
    blocked=shot(on_target=False,outcome='failure',start_xy=[30.0,8.0])
    return [shot(on_target=True,outcome='saved',start_xy=[34.0,9.0]),shot(on_target=False,outcome='off_target',start_ms=1500000),blocked,
        {'id':str(uuid4()),'kind':'shot_block','player_id':away[0],'side':'away','start_ms':60000,'shot_id':blocked['id']},
        *[{'id':str(uuid4()),'kind':'pass','player_id':home[0],'side':'home','start_ms':100000,'success':s} for s in (True,True,False,None)],
        {'id':str(uuid4()),'kind':'duel','player_id':away[0],'side':'away','start_ms':1300000,'success':True},
        {'id':str(uuid4()),'kind':'save','player_id':away[0],'side':'away','start_ms':60000}]


def _row(stats,key):return next(r for r in stats['rows'] if r['key']==key)


def test_team_stats_count_outcomes_keep_unknown_and_skip_undeclared(admin_client,analytics_match,send_command):
    match,_,_,_=_setup(admin_client,analytics_match,send_command,_actions,
        {'shots':[{'status':'complete'}],'passes':[{'status':'partial','intervals':[[0,600000]]}]})
    response=admin_client.get(f"/api/v1/matches/{match['id']}/action-stats");assert response.status_code==200,response.text
    stats=response.json();assert stats['source']['published'] is False and stats['source']['status']=='confirmed'
    # Гол протокола — тоже удар в створ; заблокированный удар не считается «мимо».
    assert _row(stats,'shots_total')['home']['value']==4 and _row(stats,'shots_on_target')['home']['value']==2
    assert _row(stats,'shots_off_target')['home']['value']==1 and _row(stats,'shots_blocked')['home']['value']==1
    assert _row(stats,'shots_total')['coverage']=='complete'
    passes=_row(stats,'passes_accurate')['home'];assert (passes['numerator'],passes['denominator'],passes['unknown'])==(2,3,1)
    assert passes['value']==66.7 and _row(stats,'passes_accurate')['coverage']=='partial'
    # Запись без объявленной полноты показывается, категория без записей и объявления — нет.
    assert _row(stats,'duels_won')['away']['value']==100.0 and _row(stats,'duels_won')['coverage']=='unknown'
    assert all(r['key']!='recoveries' for r in stats['rows'])
    assert {s['outcome'] for s in stats['shots']}=={'saved','failure'} and all(s['side']=='home' for s in stats['shots'])
    assert stats['pitch'] is not None and [p['key'] for p in stats['periods']]==['all','1','2']


def test_period_filter_and_invalid_period(admin_client,analytics_match,send_command):
    match,_,_,_=_setup(admin_client,analytics_match,send_command,_actions,{'shots':[{'status':'complete'}]})
    first=admin_client.get(f"/api/v1/matches/{match['id']}/action-stats",params={'period':'1'}).json()
    second=admin_client.get(f"/api/v1/matches/{match['id']}/action-stats",params={'period':'2'}).json()
    assert _row(first,'shots_total')['home']['value']==3 and _row(second,'shots_total')['home']['value']==1
    assert _row(second,'duels_won')['away']['value']==100.0 and all(r['key']!='duels_won' for r in first['rows'])
    assert admin_client.get(f"/api/v1/matches/{match['id']}/action-stats",params={'period':'7'}).status_code==422
    assert admin_client.get(f"/api/v1/matches/{match['id']}/action-stats",params={'period':'x'}).status_code==422


def test_guest_sees_only_published_action_version(admin_client,analytics_match,send_command):
    match,protocol,part,actions=_setup(admin_client,analytics_match,send_command,_actions,{'shots':[{'status':'complete'}]})
    path=f"/api/v1/public/matches/{match['id']}/action-stats"
    assert admin_client.get(path).status_code==404
    match=send_command(match,'publish',{'version_id':protocol['id']}).json()
    assert publish_sources(admin_client,match,part,actions).status_code==200
    admin_client.headers.pop('X-CSRF-Token',None);admin_client.cookies.clear()
    public=admin_client.get(path);assert public.status_code==200,public.text
    assert public.json()['source']['published'] is True and _row(public.json(),'shots_total')['home']['value']==4
    assert admin_client.get(f"/api/v1/matches/{match['id']}/action-stats").status_code in (401,403)


def test_ordinary_admin_cannot_read_private_stats(admin_client,analytics_match):
    grant(admin_client,False)
    assert admin_client.get(f"/api/v1/matches/{analytics_match['id']}/action-stats").status_code==403
