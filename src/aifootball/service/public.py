"""Guest schedule: explicit fields, results only from published snapshots."""
from datetime import date, datetime, time, timedelta
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import select, func, exists
from sqlalchemy.orm import Session, aliased
from aifootball.service.db import get_session
from aifootball.service.common import get_entity, as_dict, list_entities
from aifootball.service.errors import DomainError
from aifootball.service.matches.models import Match
from aifootball.service.catalog.models import CatalogImage, Entry, Player, Team
from aifootball.service.tournaments.models import Tournament, RegulationVersion
from aifootball.service.tournaments.rules import resolve_rules
from aifootball.service.protocol.models import ProtocolVersion
from aifootball.service.views import Page, PublicTournament, PublicMatch

router = APIRouter(prefix='/public')


def visible_tournament(db, tid):
    tournament = get_entity(db, Tournament, tid)
    if tournament.archived:
        raise DomainError('not_found', 'Турнир не найден', status=404)
    return tournament


def match_query():
    home_entry, away_entry = aliased(Entry), aliased(Entry)
    home, away = aliased(Team), aliased(Team)
    return (select(Match, Tournament, home.name, away.name, RegulationVersion, ProtocolVersion,
                   home.id, away.id, home.logo_id, away.logo_id)
            .join(Tournament, Match.tournament_id == Tournament.id)
            .join(home_entry, Match.home_entry_id == home_entry.id).join(home, home_entry.team_id == home.id)
            .join(away_entry, Match.away_entry_id == away_entry.id).join(away, away_entry.team_id == away.id)
            .join(RegulationVersion, Match.regulation_id == RegulationVersion.id)
            .outerjoin(ProtocolVersion, Match.published_version_id == ProtocolVersion.id)
            .where(Tournament.archived.is_(False)))


def match_view(row):
    match, tournament, home, away, regulation, published, home_id, away_id, home_logo, away_logo = row
    return {'id': match.id, 'tournament': as_dict(tournament), 'home_name': home, 'away_name': away,
            'home_team_id': home_id, 'away_team_id': away_id, 'home_logo_id': home_logo, 'away_logo_id': away_logo,
            'scheduled_at': match.scheduled_at, 'venue_label': match.venue_label, 'hall': match.hall_snapshot, 'status': match.status,
            'schedule_slot_s': resolve_rules(match, regulation).schedule_slot_s,
            'broadcast_url': match.broadcast_url, 'broadcast_embed_url': match.broadcast_embed_url,
            'public_protocol_id': published.public_id if published else None,
            'score': published.snapshot['projection']['effective_score'] if published else {'home': None, 'away': None}}


@router.get('/tournaments', response_model=Page[PublicTournament])
def tournaments(db: Session = Depends(get_session), limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    return list_entities(db, Tournament, where=[Tournament.archived.is_(False)], limit=limit, offset=offset,
                         order=Tournament.starts_on.desc())


@router.get('/tournaments/{tid}', response_model=PublicTournament)
def tournament(tid: UUID, db: Session = Depends(get_session)):
    return as_dict(visible_tournament(db, tid))


@router.get('/tournaments/{tid}/matches', response_model=Page[PublicMatch])
def calendar(tid: UUID, day: date | None = None, db: Session = Depends(get_session),
             limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    tournament = visible_tournament(db, tid)
    where = [Match.tournament_id == tid]
    if day:
        zone = ZoneInfo(tournament.timezone)
        where += [Match.scheduled_at >= datetime.combine(day, time.min, tzinfo=zone),
                  Match.scheduled_at < datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone)]
    rows = db.execute(match_query().where(*where).order_by(Match.scheduled_at, Match.id).limit(limit).offset(offset))
    return {'items': [match_view(row) for row in rows],
            'total': db.scalar(select(func.count()).select_from(Match).where(*where))}


@router.get('/matches/{mid}', response_model=PublicMatch)
def match(mid: UUID, db: Session = Depends(get_session)):
    row = db.execute(match_query().where(Match.id == mid)).first()
    if row is None:
        raise DomainError('not_found', 'Матч не найден', status=404)
    return match_view(row)


@router.get('/catalog/team-logos/{image_id}')
def team_logo(image_id: UUID, request: Request, db: Session = Depends(get_session)):
    # Только логотип команды неархивного турнира; общий файл с фото игрока остаётся закрытым.
    linked = (select(Team.id).join(Entry, Entry.team_id == Team.id).join(Tournament, Entry.tournament_id == Tournament.id)
              .where(Team.logo_id == image_id, Team.archived.is_(False), Tournament.archived.is_(False)))
    visible = db.scalar(select(exists().where(CatalogImage.id == image_id)
                               .where(exists(linked)).where(~exists().where(Player.photo_id == image_id))))
    path = Path(request.app.state.settings.attachment_root) / 'catalog' / (str(image_id) + '.png')
    if not visible or not path.is_file():
        raise DomainError('not_found', 'Изображение недоступно', status=404)
    return FileResponse(path, media_type='image/png', headers={
        'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store'})
