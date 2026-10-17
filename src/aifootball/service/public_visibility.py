"""One visibility boundary shared by all guest readers."""
from aifootball.service.common import get_entity
from aifootball.service.errors import DomainError
from aifootball.service.tournaments.models import Tournament


def require_public_tournament(db, tournament_id):
    tournament = get_entity(db, Tournament, tournament_id)
    if tournament.archived or tournament.visibility != 'public':
        raise DomainError('not_found', 'Турнир не найден', status=404)
    return tournament


def require_public_match(db, match_id):
    from aifootball.service.matches.models import Match
    match = get_entity(db, Match, match_id)
    require_public_tournament(db, match.tournament_id)
    return match
