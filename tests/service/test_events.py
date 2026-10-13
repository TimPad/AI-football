from uuid import uuid4
import pytest


def event(kind='goal',**changes):
    return {'id':str(uuid4()),'kind':kind,'side':'home','period':1,'elapsed_ms':None,'video_ms':None,**changes}


def test_goal_assist_player_and_time_validation(regulation_data):
    from pydantic import TypeAdapter
    from aifootball.service.protocol.events import Event,validate_event
    from aifootball.service.tournaments.schemas import Regulation
    from aifootball.service.errors import DomainError
    home,other=str(uuid4()),str(uuid4())
    lineup=[{'player_id':home,'side':'home'},{'player_id':other,'side':'away'}]
    rules=Regulation.model_validate(regulation_data)
    for changes in [{'player_id':home,'assist_id':home,'assist_known':True},
                    {'player_id':home,'assist_id':other,'assist_known':True},
                    {'elapsed_ms':1200001},{'period':3},{'video_ms':10}]:
        e=TypeAdapter(Event).validate_python(event(**changes))
        with pytest.raises(DomainError): validate_event(e,regulation=rules,lineup=lineup,events=[e])
    e=TypeAdapter(Event).validate_python(event(player_id=None))
    assert validate_event(e,regulation=rules,lineup=lineup,events=[e]).elapsed_ms is None


def test_second_yellow_requires_same_player_previous_card(regulation_data):
    from pydantic import TypeAdapter
    from aifootball.service.protocol.events import Event,validate_event
    from aifootball.service.tournaments.schemas import Regulation
    from aifootball.service.errors import DomainError
    pid=str(uuid4()); lineup=[{'player_id':pid,'side':'home'}]
    yellow=TypeAdapter(Event).validate_python(event('card',player_id=pid,card='yellow'))
    second=TypeAdapter(Event).validate_python(event('card',player_id=pid,card='second_yellow',previous_yellow_id=str(yellow.id)))
    validate_event(second,regulation=Regulation(**regulation_data),lineup=lineup,events=[yellow,second])
    with pytest.raises(DomainError):
        validate_event(second,regulation=Regulation(**regulation_data),lineup=lineup,events=[second])


def test_penalty_links_and_foul_victim(regulation_data):
    from pydantic import TypeAdapter,ValidationError
    from aifootball.service.protocol.events import Event,validate_event
    from aifootball.service.tournaments.schemas import Regulation
    from aifootball.service.errors import DomainError
    rules=Regulation(**regulation_data); pid=str(uuid4()); lineup=[{'player_id':pid,'side':'home'}]
    for raw in [event('foul',victim_id=pid),event('goal',from_penalty=True,penalty_id=str(uuid4())),
                event('penalty_attempt',penalty_id=str(uuid4()),outcome='goal'),
                event('substitution',player_in_id=pid,player_out_id=pid)]:
        e=TypeAdapter(Event).validate_python(raw)
        with pytest.raises(DomainError): validate_event(e,regulation=rules,lineup=lineup,events=[e])
    with pytest.raises(ValidationError): TypeAdapter(Event).validate_python(event(elapsed_ms=-1))


def test_complete_projection_does_not_mutate_document(regulation_data):
    from aifootball.service.protocol.schemas import ProtocolDocument
    from aifootball.service.protocol.projection import project_protocol
    from aifootball.service.tournaments.schemas import Regulation
    doc=ProtocolDocument(events=[event()]); before=doc.model_dump(mode='json')
    project_protocol(doc,Regulation(**regulation_data))
    assert doc.model_dump(mode='json')==before
