from copy import deepcopy
from aifootball.ratings.explanation import explain_rating


def score(**changes):return {'score':70,'display_rating':7.3,'player_id':'p1','role':'ala','reasons':[],
    'components':{'Creation':75,'Security':40},'contributions':{'Creation':22.5,'Security':6},**changes}


def action(kind='pass',**changes):return {'id':'a1','kind':kind,'player_id':'p1','role':'ala','verified':True,'success':True,'start_ms':1000,
    'source_refs':[{'kind':'understanding','id':'e1','run_id':'r1','evidence_ids':['f1']}],**changes}


def test_no_rating_explains_reason_and_empty_actions_do_not_claim_no_errors():
    value=explain_rating(score(score=None,display_rating=None,reasons=['missing:recoveries_rate10']),{},[])
    assert value['rating'] is None and value['reasons']==['missing:recoveries_rate10']
    assert value['positive']==[] and value['errors']==[] and value['selection_is_exhaustive'] is False


def test_only_verified_correct_player_and_role_actions_are_selected_deterministically():
    actions=[action(id=f'a{i}') for i in range(5)]+[action(id='foreign',player_id='p2'),action(id='rejected',decision='rejected'),
        action(id='other-role',role='pivot'),action(id='unverified',verified=False),action('turnover',id='loss',success=False)]
    before=deepcopy(actions);one=explain_rating(score(),{},actions)
    assert len(one['positive'])==3 and [x['canonical_action_id'] for x in one['errors']]==['loss']
    assert one==explain_rating(score(),{},list(reversed(actions))) and actions==before
    assert all(v['canonical_action_id'] not in ('foreign','rejected','other-role','unverified') for v in one['positive'])


def test_public_moments_never_link_unpublished_evidence_and_text_is_plain():
    private=explain_rating(score(),{},[action(notes='<img src=x onerror=alert(1)>')])
    assert private['positive'][0]['evidence'][0]['run_id']=='r1'
    public=explain_rating(score(scope='public'),{},[action(notes='PRIVATE-NOTE')])
    assert public['positive'][0]['evidence']==[] and 'PRIVATE-NOTE' not in str(public)
    assert '<img' not in private['text']


def test_own_goal_never_appears_as_a_positive_goal():
    own=action('goal',own_goal=True,counts_as_player_goal=False)
    value=explain_rating(score(),{},[own])
    assert value['positive']==[]
    assert value['errors'][0]['text']=='Автогол'
