"""Normalize reviewed rows without mutating players, teams or applications."""
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from uuid import UUID, uuid5
from pydantic import ValidationError
from sqlalchemy import select, func
from aifootball.service.common import get_entity
from aifootball.service.db import utcnow
from aifootball.service.errors import DomainError
from aifootball.service.catalog.models import Team, Player, Entry, EntryPlayer, TeamMember
from aifootball.service.catalog.schemas import ProfilePlayer
from aifootball.service.tournaments.models import Tournament, RegulationVersion
from .models import RosterImport

FIELDS = {'team', 'name', 'last_name', 'first_name', 'patronymic', 'shirt_number',
          'position', 'birth_date', 'height_cm', 'weight_kg'}
POSITIONS = {'вратарь': 'goalkeeper', 'вр': 'goalkeeper', 'gk': 'goalkeeper',
             'защитник': 'defender', 'фиксо': 'defender', 'ала': 'winger', 'фланговый': 'winger',
             'нападающий': 'forward', 'пивот': 'forward', 'универсал': 'universal'}


def text(value):
    if value is None:
        return ''
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def normalized(value):
    return ' '.join(text(value).split()).lower()


def target_entity(db, scope, target_id):
    entity = get_entity(db, Team if scope == 'team' else Tournament, target_id)
    if entity.archived:
        raise DomainError('archived', 'Команда или турнир в архиве')
    return entity


def owned_import(db, identifier, actor_id, actor_kind='admin', *, lock=False):
    statement = select(RosterImport).where(RosterImport.id == identifier,
        RosterImport.actor_id == actor_id, RosterImport.actor_kind == actor_kind)
    if lock:
        statement = statement.with_for_update()
    session = db.scalar(statement)
    if session is None:
        raise DomainError('not_found', 'Предпросмотр не найден', status=404)
    if actor_kind=='captain':
        from aifootball.service.captains.models import CaptainAccount
        from aifootball.service.captains.security import require_captain_team
        if session.scope!='team':raise DomainError('not_found','Предпросмотр недоступен',status=404)
        if lock:get_entity(db,Team,session.target_id,lock=True)
        require_captain_team(db,get_entity(db,CaptainAccount,actor_id),session.target_id)
    if session.status != 'committed' and session.expires_at < utcnow():
        raise DomainError('import_expired', 'Срок предпросмотра истёк. Загрузите Excel ещё раз.', status=410)
    return session


def import_view(session):
    sheets = [{'name': sheet['name'], 'headers': [text(v) for v in sheet['rows'][0]['cells']],
               'row_count': len(sheet['rows']) - 1} for sheet in session.source.get('sheets', [])]
    return {'id': session.id, 'revision': session.revision, 'scope': session.scope,
        'target_id': session.target_id, 'status': session.status, 'expires_at': session.expires_at,
        'entry_id': session.source.get('entry_id'),
        'sheets': sheets, 'rows': session.rows, 'summary': session.summary,
        'configuration': session.configuration,
        'can_commit': bool(session.rows and not session.summary.get('errors')
                           and any(not row['excluded'] for row in session.rows) and session.status != 'committed'),
        'result': session.result}


def _details(values):
    birth = text(values.get('birth_date'))
    if birth:
        parsed = None
        for fmt in ('%Y-%m-%d', '%d.%m.%Y'):
            try:
                parsed = datetime.strptime(birth, fmt).date()
                break
            except ValueError:
                pass
        if parsed is None:
            raise ValueError('Дата рождения: используйте ДД.ММ.ГГГГ или ГГГГ-ММ-ДД')
        birth = parsed.isoformat()
    height = text(values.get('height_cm'))
    weight = text(values.get('weight_kg'))
    position = normalized(values.get('position'))
    return {'birth_date': birth or None,
            'position': POSITIONS.get(position, position) or None,
            'height_cm': int(height) if height else None,
            'weight_kg': float(weight.replace(',', '.')) if weight else None}


def build_preview(db, session, data):
    if session.status == 'committed':
        raise DomainError('already_committed', 'Импорт уже применён', status=409)
    if session.revision != data.expected_revision:
        raise DomainError('revision_conflict', 'Предпросмотр изменился. Обновите его.', status=409)
    target = target_entity(db, session.scope, session.target_id)
    fixed_team=None
    if session.scope=='tournament' and session.source.get('entry_id'):
        entry=get_entity(db,Entry,UUID(session.source['entry_id']))
        if entry.tournament_id!=session.target_id:
            raise DomainError('import_entry','Заявка относится к другому турниру',status=404)
        fixed_team=get_entity(db,Team,entry.team_id)
    sheet = next((s for s in session.source['sheets'] if s['name'] == data.sheet), None)
    if sheet is None or not data.mapping or set(data.mapping) - FIELDS:
        raise DomainError('import_mapping', 'Выберите лист и сопоставьте столбцы')
    if not ('name' in data.mapping or {'last_name', 'first_name'} <= set(data.mapping)):
        raise DomainError('import_mapping', 'Укажите столбец ФИО или отдельные фамилию и имя')
    if any(index < 0 or index >= 64 for index in data.mapping.values()):
        raise DomainError('import_mapping', 'Некорректный номер столбца')
    identifiers = {row['id'] for row in sheet['rows'][1:]}
    if (set(data.edits) | set(data.decisions) | set(data.excluded_rows)) - identifiers:
        raise DomainError('import_row', 'Правка относится к другой строке или листу')
    raw_rows = []
    for source in sheet['rows'][1:]:
        values = {field: source['cells'][index] if index < len(source['cells']) else None
                  for field, index in data.mapping.items()}
        edits = data.edits.get(source['id'], {})
        if set(edits) - FIELDS:
            raise DomainError('import_field', 'Неизвестное поле строки')
        values.update(edits)
        if not text(values.get('name')):
            values['name'] = ' '.join(text(values.get(k)) for k in ('last_name', 'first_name', 'patronymic')
                                      if text(values.get(k)))
        raw_rows.append((source, values, edits))
    names = {normalized(v.get('name')) for _, v, _ in raw_rows}
    team_names = {normalized(v.get('team')) for _, v, _ in raw_rows}
    explicit_players = [d.player_id for d in data.decisions.values() if d.player_id]
    explicit_teams = []
    for value in data.team_decisions.values():
        if value != 'new':
            try:
                explicit_teams.append(UUID(value))
            except ValueError:
                raise DomainError('import_team', 'Выберите существующую команду или новую')
    people_query=select(Player).where((func.lower(Player.name).in_(names)) | (Player.id.in_(explicit_players)))
    foreign_names=set()
    if session.actor_kind=='captain':
        allowed=select(TeamMember.player_id).where(TeamMember.team_id==session.target_id,TeamMember.active)
        foreign_names=set(db.scalars(select(func.lower(Player.name)).where(func.lower(Player.name).in_(names),~Player.id.in_(allowed))))
        people_query=people_query.where(Player.id.in_(allowed))
    people = list(db.scalars(people_query))
    teams = list(db.scalars(select(Team).where(
        (func.lower(Team.name).in_(team_names)) | (Team.id.in_(explicit_teams)))))
    by_person = {str(person.id): person for person in people}
    by_team = {str(team.id): team for team in teams}
    people_names, team_names_map = defaultdict(list), defaultdict(list)
    for person in people:
        people_names[normalized(person.name)].append(person)
    for team in teams:
        team_names_map[normalized(team.name)].append(team)
    expected = {'target_revision': target.revision, 'players': {}, 'teams': {}, 'entries': {},
                'new_player_candidates': {}, 'new_team_candidates': {}}
    rows = []
    for source, values, edits in raw_rows:
        issues = []
        excluded = source['id'] in data.excluded_rows
        name = text(values.get('name'))
        team_name = target.name if session.scope == 'team' else fixed_team.name if fixed_team else text(values.get('team'))
        number = text(values.get('shirt_number')) or None
        decision = data.decisions.get(source['id'])
        candidates = people_names[normalized(name)]
        person = by_person.get(str(decision.player_id)) if decision and decision.player_id else None
        is_new = person is None
        if session.actor_kind=='captain' and is_new and normalized(name) in foreign_names:
            issues.append('Добавление этого игрока требует обращения к организатору')
        if decision and decision.player_id and person is None:
            issues.append('Выбранный игрок больше не доступен')
        if decision and decision.player_id and decision.create_new:
            issues.append('Выберите существующего игрока или создание нового')
        if candidates and not person and not (decision and decision.create_new):
            issues.append('Есть похожий игрок. Выберите его или явно создайте нового')
        if person and person.archived:
            issues.append('Игрок в архиве. Восстановите его отдельно')
        player_id = str(person.id) if person else str(uuid5(session.id, 'player:' + source['id']))
        if person and not excluded:
            expected['players'][str(person.id)] = person.revision
        elif not excluded:
            expected['new_player_candidates'][normalized(name)] = sorted(str(p.id) for p in candidates)
        team_candidates = [] if session.scope == 'team' else team_names_map[normalized(team_name)]
        team_decision = data.team_decisions.get(team_name)
        team = target if session.scope == 'team' else fixed_team or by_team.get(team_decision or '')
        if session.scope == 'tournament' and not fixed_team and team_candidates and not team_decision:
            issues.append('Команда уже есть в справочнике. Выберите её или новую')
        if team_decision and team_decision != 'new' and team is None:
            issues.append('Выбранная команда больше не доступна')
        if team and team.archived:
            issues.append('Команда в архиве. Восстановите её отдельно')
        team_id = str(team.id) if team else str(uuid5(session.id, 'team:' + normalized(team_name)))
        if team and not excluded:
            expected['teams'][team_id] = team.revision
        elif not team and not excluded:
            expected['new_team_candidates'][normalized(team_name)] = sorted(str(t.id) for t in team_candidates)
        if not team_name or len(team_name) > 200:
            issues.append('Укажите название команды (до 200 символов)')
        details = {}
        try:
            details = _details(values)
            valid = ProfilePlayer(player_id=player_id, name=name, shirt_number=number, **details)
            details = valid.model_dump(mode='json', exclude={'player_id', 'revision', 'name', 'shirt_number'})
        except (ValueError, ValidationError) as exc:
            issues.append(str(exc) if not isinstance(exc, ValidationError) else 'Проверьте ФИО, номер, амплуа, дату рождения, рост и вес')
        if any(index in source.get('formulas', []) and field not in edits for field, index in data.mapping.items()):
            issues.append('В выбранных столбцах есть формула. Замените её значением')
        if any(index in source.get('errors', []) and field not in edits for field, index in data.mapping.items()):
            issues.append('В выбранных столбцах есть ошибка Excel. Исправьте значение или исключите строку')
        rows.append({'id': source['id'], 'source_row': source['source_row'], 'name': name,
            'team_name': team_name, 'shirt_number': number, 'player_id': player_id, 'team_id': team_id,
            'is_new_player': is_new, 'is_new_team': team is None, 'details': details,
            'player_candidates': [{'id': str(p.id), 'name': p.name, 'archived': p.archived} for p in candidates],
            'team_candidates': [{'id': str(t.id), 'name': t.name, 'archived': t.archived} for t in team_candidates],
            'issues': issues if not excluded else [], 'excluded': excluded,
            'values': {key:text(value) or None for key,value in values.items()},
            'action': 'Создать игрока' if is_new else 'Использовать игрока'})
    active = [row for row in rows if not row['excluded']]
    duplicate_names = Counter(normalized(row['name']) for row in active if row['is_new_player'])
    for row in active:
        decision = data.decisions.get(row['id'])
        if row['is_new_player'] and duplicate_names[normalized(row['name'])] > 1 and not (decision and decision.create_new):
            row['issues'].append('ФИО повторяется в файле. Подтвердите создание разных людей')
    groups = defaultdict(list)
    for row in active:
        groups[row['team_id']].append(row)
    if len(groups) > 64:
        raise DomainError('import_teams', 'Не более 64 команд в одной загрузке')
    rules = db.scalar(select(RegulationVersion).where(RegulationVersion.tournament_id == target.id)
        .order_by(RegulationVersion.created_at.desc(), RegulationVersion.id).limit(1)) if session.scope == 'tournament' else None
    limit = rules.rules['tournament_roster_limit'] if rules else 1000
    for team_id, grouped in groups.items():
        if session.scope == 'team':
            old = db.scalars(select(TeamMember).where(TeamMember.team_id == target.id, TeamMember.active)).all()
        else:
            entry = db.scalar(select(Entry).where(Entry.tournament_id == target.id, Entry.team_id == UUID(team_id)))
            if entry:
                expected['entries'][str(entry.id)] = entry.revision
            old = db.scalars(select(EntryPlayer).where(EntryPlayer.entry_id == entry.id, EntryPlayer.active)).all() if entry else []
        combined = {str(member.player_id): member.shirt_number for member in old}
        seen = set()
        for row in grouped:
            if row['player_id'] in seen:
                row['issues'].append('Игрок повторяется в заявке')
            seen.add(row['player_id'])
            combined[row['player_id']] = row['shirt_number'] or combined.get(row['player_id'])
        numbers = Counter(n for n in combined.values() if n)
        for row in grouped:
            if row['shirt_number'] and numbers[row['shirt_number']] > 1:
                row['issues'].append('Номер повторяется в составе команды')
            if len(combined) > limit:
                row['issues'].append(f'Превышен лимит заявки: {limit} игроков')
    session.rows = rows
    session.expected = expected
    session.configuration = data.model_dump(mode='json', exclude={'expected_revision'})
    session.summary = {'teams_created': len({r['team_id'] for r in active if r['is_new_team']}),
        'players_created': len({r['player_id'] for r in active if r['is_new_player']}),
        'players_reused': len({r['player_id'] for r in active if not r['is_new_player']}),
        'entries_updated': len(groups) if session.scope == 'tournament' else 0,
        'skipped_rows': len(rows) - len(active), 'errors': sum(bool(r['issues']) for r in active)}
    session.revision += 1
    session.status = 'ready' if active and not session.summary['errors'] else 'draft'
    session.expires_at = utcnow() + timedelta(days=7)
    db.flush()
    return import_view(session)
