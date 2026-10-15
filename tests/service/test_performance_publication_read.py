from uuid import uuid4
from fastapi.testclient import TestClient
from sqlalchemy import event, select, func
from sqlalchemy.orm import Session
from aifootball.service.ratings.models import (TournamentRatingState, RatingMatchPublication,
    RatingPolicyVersion, RatingCommand)
from .test_analysis_jobs import grant, analytics_match
from .test_ratings_snapshots import prepare, publish_sources


def url(match):
    return '/api/v1/matches/' + match['id'] + '/performance-publication'


def counts(client):
    with Session(client.app.state.engine) as db:
        return {model.__name__: db.scalar(select(func.count()).select_from(model))
                for model in (TournamentRatingState, RatingMatchPublication, RatingPolicyVersion, RatingCommand)}


def test_read_absent_publication_creates_nothing(admin_client, match_factory):
    m = match_factory()
    grant(admin_client)
    for _ in range(2):
        r = admin_client.get(url(m))
        assert r.status_code == 200
        assert r.json() == {'revision': 0, 'match_id': m['id'],
            'participation_version_id': None, 'action_version_id': None,
            'policy_approved': False}
    assert set(counts(admin_client).values()) == {0}


def test_read_returns_tournament_revision_and_selected_sources(admin_client, analytics_match, send_command):
    match, protocol, part, actions = prepare(admin_client, analytics_match, send_command)
    match = send_command(match, 'publish', {'version_id': protocol['id']}).json()
    saved = publish_sources(admin_client, match, part, actions)
    assert saved.status_code == 200, saved.text
    with Session(admin_client.app.state.engine) as db:
        db.scalar(select(TournamentRatingState)).revision = 7
        db.scalar(select(RatingMatchPublication)).revision = 2
        db.commit()
    before = counts(admin_client)
    statements = []
    def record(conn, cursor, statement, *args):
        statements.append(statement.lstrip().split(None, 1)[0].upper())
    engine = admin_client.app.state.engine
    event.listen(engine, 'before_cursor_execute', record)
    try:
        response = admin_client.get(url(match))
    finally:
        event.remove(engine, 'before_cursor_execute', record)
    assert response.status_code == 200, response.text
    assert response.json() == {**saved.json(), 'revision': 7}
    assert response.json()['participation_version_id'] == part['id']
    assert response.json()['action_version_id'] == actions['id'] and response.json()['policy_approved'] is True
    assert not {'INSERT', 'UPDATE', 'DELETE'} & set(statements)
    assert counts(admin_client) == before


def test_read_access_and_validation(admin_client, match_factory):
    m = match_factory()
    assert admin_client.get(url(m)).status_code == 403
    with TestClient(admin_client.app) as guest:
        assert guest.get(url(m)).status_code == 401
    grant(admin_client)
    assert admin_client.get('/api/v1/matches/' + str(uuid4()) + '/performance-publication').status_code == 404
    assert admin_client.get('/api/v1/matches/not-a-uuid/performance-publication').status_code == 422
