from uuid import UUID
from sqlalchemy.orm import Session
from aifootball.service.stages.results import load_results, confirmed_match_ids
from .test_confirmation import finish


def test_cabinet_sees_confirmed_public_sees_published(admin_client, match_factory, send_command):
    m = send_command(finish(send_command, match_factory()), 'confirm', {'acknowledge_incomplete': True}).json()
    mid = UUID(m['id'])
    with Session(admin_client.app.state.engine) as db:
        assert load_results(db, [mid], 'public') == {}
        leg = load_results(db, [mid], 'cabinet')[mid]
        assert (leg.home, leg.home_goals, leg.away_goals, leg.points) == (m['home_entry_id'], 3, 2, (3, 1, 0))
        assert confirmed_match_ids(db, [mid]) == {mid}
    version = admin_client.get(f"/api/v1/matches/{m['id']}/versions").json()['items'][0]
    m = send_command(m, 'publish', {'version_id': version['id']}).json()
    m = send_command(send_command(m, 'reopen', {}).json(), 'set_totals', {'reported_totals': {'home': {'score': 5}, 'away': {'score': 2}}}).json()
    m = send_command(m, 'confirm', {'acknowledge_incomplete': True}).json()
    with Session(admin_client.app.state.engine) as db:
        assert load_results(db, [mid], 'public')[mid].home_goals == 3
        assert load_results(db, [mid], 'cabinet')[mid].home_goals == 5
