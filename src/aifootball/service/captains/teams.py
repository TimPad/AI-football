from uuid import UUID,uuid5
from sqlalchemy import select,func
from aifootball.service.common import get_entity,as_dict
from aifootball.service.errors import DomainError,RevisionConflict
from aifootball.service.catalog.models import Team,Player,TeamMember
from aifootball.service.catalog.profiles import team_profile,check_image
from aifootball.service.catalog.schemas import PlayerDetails,PlayerCreate
from aifootball.service.captains.models import TeamCaptainGrant,PlayerProfileProposal,CaptainImage
from aifootball.service.captains.security import require_captain_team

def captain_team_view(db,team,account):
    result=team_profile(db,team)
    result['profile_proposals']=[as_dict(p) for p in db.scalars(select(PlayerProfileProposal).where(PlayerProfileProposal.team_id==team.id,PlayerProfileProposal.account_id==account.id).order_by(PlayerProfileProposal.created_at.desc()))]
    return result

def allowed_image(db,account,image_id,team=None):
    if image_id is None:return
    if db.scalar(select(CaptainImage.image_id).where(CaptainImage.image_id==image_id,CaptainImage.account_id==account.id)):return
    if team and (team.logo_id==image_id or db.scalar(select(Player.id).join(TeamMember,TeamMember.player_id==Player.id).where(TeamMember.team_id==team.id,TeamMember.active,Player.photo_id==image_id))):return
    raise DomainError('not_found','Изображение недоступно',status=404)

def save_team(db,account,data,team_id=None):
    if team_id:
        team=get_entity(db,Team,team_id,lock=True);require_captain_team(db,account,team_id)
        if team.revision!=data.expected_revision:raise RevisionConflict(team.revision)
        if team.archived:raise DomainError('archived','Команда находится в архиве',status=409)
    else:
        team=Team(id=uuid5(account.id,'team:'+str(data.request_id)),name=data.name);db.add(team);db.flush()
        db.add(TeamCaptainGrant(team_id=team.id,account_id=account.id));db.flush()
    ids=[p.player_id for p in data.players];numbers=[p.shirt_number for p in data.players if p.shirt_number]
    if len(ids)!=len(set(ids)) or len(numbers)!=len(set(numbers)):raise DomainError('duplicate_roster','Игрок или номер повторяется в составе')
    allowed_image(db,account,data.logo_id,team)
    old={p.player_id:p for p in db.scalars(select(TeamMember).where(TeamMember.team_id==team.id))}
    for row in data.players:
        person=db.scalar(select(Player).where(Player.id==row.player_id).with_for_update())
        values={key:getattr(row,key) for key in PlayerDetails.model_fields}|{'name':row.name}
        if person is not None:
            if row.player_id not in old or not old[row.player_id].active:raise DomainError('not_found','Игрок недоступен для этой команды',status=404)
            if person.archived or person.revision!=row.revision:raise DomainError('player_conflict','Карточка игрока изменилась. Обновите состав.',status=409)
            if any(getattr(person,k)!=v for k,v in values.items()):
                allowed_image(db,account,row.photo_id,team)
                proposal=PlayerProfileProposal(account_id=account.id,team_id=team.id,player_id=person.id,expected_player_revision=person.revision,payload=row.model_dump(mode='json',exclude={'player_id','revision'}));db.add(proposal)
        else:
            if row.revision!=0:raise DomainError('not_found','Игрок недоступен',status=404)
            if db.scalar(select(Player.id).where(func.lower(Player.name)==row.name.lower())):raise DomainError('profile_review_required','Добавление этого игрока требует обращения к организатору.',status=409)
            allowed_image(db,account,row.photo_id)
            person=Player(id=row.player_id,**values);db.add(person);db.flush()
    for member in old.values():member.active=False
    db.flush()
    for row in data.players:
        member=old.get(row.player_id)
        if member is None:member=TeamMember(team_id=team.id,player_id=row.player_id);db.add(member)
        member.active=True;member.shirt_number=row.shirt_number or None
    team.name=data.name;team.description=data.description;team.logo_id=data.logo_id;team.revision+=1
    db.flush();return captain_team_view(db,team,account)
