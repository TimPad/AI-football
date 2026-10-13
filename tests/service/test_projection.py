from uuid import uuid4
import pytest


def goal(**changes):
    return {'id':str(uuid4()),'kind':'goal','side':'home','period':1,'elapsed_ms':None,
            'own_goal':False,'assist_known':False,**changes}


def test_partial_score_not_added_to_events(regulation_data):
    from aifootball.service.protocol.schemas import ProtocolDocument
    from aifootball.service.protocol.projection import project_protocol
    from aifootball.service.tournaments.schemas import Regulation
    doc=ProtocolDocument(events=[goal(),goal()],reported_totals={'home':{'score':3},'away':{'score':2}},
        completeness={'goals':'partial','assists':'unknown','fouls':'unknown','cards':'unknown','lineup':'unknown','time':'unknown'})
    p=project_protocol(doc,Regulation(**regulation_data))
    assert p.event_score=={'home':2,'away':0}
    assert p.effective_score=={'home':3,'away':2}
    assert p.event_totals['home']['fouls']==0
    assert p.effective_totals['home']['fouls'] is None
    assert 'goals' in p.incomplete_sections


def test_own_goal_shootout_and_unknown_score(regulation_data):
    from aifootball.service.protocol.schemas import ProtocolDocument
    from aifootball.service.protocol.projection import project_protocol
    from aifootball.service.tournaments.schemas import Regulation
    rules=Regulation(**{**regulation_data,'shootout':{'enabled':True,'initial_attempts':5}})
    doc=ProtocolDocument(events=[goal(own_goal=True,assist_known=True),
        {'id':str(uuid4()),'kind':'shootout_attempt','side':'home','attempt_number':1,'outcome':'goal'}])
    p=project_protocol(doc,rules)
    assert p.event_score=={'home':0,'away':1}
    assert p.effective_score=={'home':None,'away':None}
    assert p.shootout_score=={'home':1,'away':0}


def test_complete_mismatch_confirmation_and_technical_result(regulation_data):
    from aifootball.service.protocol.schemas import ProtocolDocument
    from aifootball.service.protocol.projection import project_protocol
    from aifootball.service.protocol.validation import validate_confirmation
    from aifootball.service.tournaments.schemas import Regulation
    from aifootball.service.errors import DomainError
    rules=Regulation(**regulation_data)
    doc=ProtocolDocument(events=[goal()],reported_totals={'home':{'score':3},'away':{'score':0}})
    doc.completeness.goals='complete'
    with pytest.raises(DomainError):
        validate_confirmation(doc,project_protocol(doc,rules),acknowledge_incomplete=True)
    doc.result_type='technical'; doc.technical_reason='Неявка'
    validate_confirmation(doc,project_protocol(doc,rules),acknowledge_incomplete=True)


def test_penalty_attempt_not_double_counted_and_cards(regulation_data):
    from aifootball.service.protocol.schemas import ProtocolDocument
    from aifootball.service.protocol.projection import project_protocol
    from aifootball.service.tournaments.schemas import Regulation
    award=str(uuid4()); first=str(uuid4())
    doc=ProtocolDocument(events=[{'id':award,'kind':'penalty_awarded','side':'home','period':1},
        {'id':str(uuid4()),'kind':'penalty_attempt','side':'home','period':1,'penalty_id':award,'outcome':'goal'},
        goal(from_penalty=True,penalty_id=award),
        {'id':first,'kind':'card','side':'away','period':1,'card':'yellow'},
        {'id':str(uuid4()),'kind':'card','side':'away','period':1,'card':'second_yellow','previous_yellow_id':first}])
    p=project_protocol(doc,Regulation(**regulation_data))
    assert p.event_score['home']==1
    assert p.event_totals['away']['yellow_cards']==2
    assert p.event_totals['away']['dismissals']==1
