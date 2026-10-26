"""Этапы турнира: вычисление таблиц и сетки, жеребьёвка, назначение пар, жребий, туры швейцарки."""
from dataclasses import dataclass, field
from sqlalchemy import select, func
from aifootball.service.common import get_entity
from aifootball.service.errors import DomainError
from aifootball.service.catalog.models import Entry, Team
from aifootball.service.matches.models import Match, LineupMember
from aifootball.service.tournaments.models import RegulationVersion
from aifootball.service.stages.models import Stage, StageDraw, Fixture
from aifootball.service.stages.schemas import StageConfig, ELIMINATION, template_stages
from aifootball.service.stages.generate import participants_placement, fixtures_for, scheme_for, qualifier_count
from aifootball.service.stages.results import load_results, confirmed_match_ids
from aifootball.service.stages.labels import group_name, pair_label, source_label, round_name
from aifootball.service.stages.rules.brackets import FixtureSpec, bracket_size
from aifootball.service.stages.rules.progress import Outcome, resolve_bracket, resolve_source, group_outcome, _stage_order
from aifootball.service.stages.rules.standings import Result, rank, rank_across
from aifootball.service.stages.rules.swiss import swiss_pairs
from aifootball.service.stages.rules.draws import group_sizes



def stage_conflict(stage):
    return DomainError('revision_conflict', 'Этап изменён в другом окне. Обновите страницу.', status=409,
                       current_revision=stage.revision)


# Загрузка.

def stages_of(db, tid, lock=False):
    query = select(Stage).where(Stage.tournament_id == tid).order_by(Stage.position)
    return list(db.scalars(query.with_for_update() if lock else query))


def current_draw(db, stage_id):
    return db.scalar(select(StageDraw).where(StageDraw.stage_id == stage_id).order_by(StageDraw.version.desc()).limit(1))


def draw_fixtures(db, draw):
    if draw is None: return []
    return list(db.scalars(select(Fixture).where(Fixture.draw_id == draw.id).order_by(Fixture.round_no, Fixture.key, Fixture.leg)))


def team_refs(db, tid):
    rows = db.execute(select(Entry.id, Team.id, Team.name, Team.logo_id).join(Team, Entry.team_id == Team.id)
                      .where(Entry.tournament_id == tid).order_by(Entry.created_at, Entry.id)).all()
    return {str(e): {'entry_id': e, 'team_id': t, 'name': n, 'logo_id': logo} for e, t, n, logo in rows}


def config_of(stage): return StageConfig.model_validate(stage.config)


def spec_of(fixture, fixed=True):
    """Пара для правил; назначенный матч играет зафиксированными командами, иначе — по источникам."""
    home = {'entry': str(fixture.home_entry_id)} if fixed and fixture.home_entry_id else fixture.home_source
    away = {'entry': str(fixture.away_entry_id)} if fixed and fixture.away_entry_id else fixture.away_source
    return FixtureSpec(fixture.key, fixture.round_no, home, away, fixture.bracket, fixture.slot, fixture.leg,
                       fixture.group_no, fixture.bye)


# Вычисление состояния.

@dataclass
class StageEval:
    stage: Stage
    config: StageConfig
    draw: StageDraw | None
    fixtures: list
    legs: dict = field(default_factory=dict)             # fixture.id -> Leg
    pairs: dict = field(default_factory=dict)            # key -> PairState (сетки)
    computed: dict = field(default_factory=dict)         # fixture.id -> (home, away) по источникам
    tables: list = field(default_factory=list)
    outcome: Outcome = field(default_factory=Outcome)
    prior: Outcome | None = None
    status: str = 'draft'
    rounds_total: int = 0
    group_done: list = field(default_factory=list)   # группа доиграна — только тогда равенство требует жребия


def evaluate(db, tournament, scope, stages=None):
    stages = stages if stages is not None else stages_of(db, tournament.id)
    draws = {s.id: current_draw(db, s.id) for s in stages}
    fixtures = {s.id: draw_fixtures(db, draws[s.id]) for s in stages}
    match_ids = [f.match_id for items in fixtures.values() for f in items if f.match_id]
    results = load_results(db, match_ids, scope)
    confirmed = confirmed_match_ids(db, match_ids)
    win_points = {}
    for s in stages:
        rules = get_entity(db, RegulationVersion, s.regulation_id).rules
        win_points[s.id] = rules['points']['win']
    evaluated = []; prior = None
    for stage in stages:
        ev = StageEval(stage, config_of(stage), draws[stage.id], fixtures[stage.id])
        ev.prior = prior if ev.config.source.get('previous') else None
        ev.legs = {f.id: results[f.match_id] for f in ev.fixtures if f.match_id in results}
        if ev.draw is not None:
            _evaluate_stage(ev, win_points[stage.id])
        ev.status = _status(ev, confirmed)
        evaluated.append(ev); prior = ev.outcome
    return evaluated


def _evaluate_stage(ev, win_points):
    kind = ev.config.kind; lots = ev.stage.lots or {}
    criteria = ev.config.effective_criteria()
    if kind in ('groups', 'round_robin'):
        groups = ev.draw.placement if kind == 'groups' else [ev.draw.placement]
        results = {}; expected = []
        for g in range(1, len(groups) + 1):
            items = [f for f in ev.fixtures if (f.group_no or 1) == g and not f.bye] if kind == 'groups' else \
                [f for f in ev.fixtures if not f.bye]
            expected.append(len(items))
            results[g] = [_result(ev.legs[f.id]) for f in items if f.id in ev.legs]
        per_group = ev.config.advance.per_group if kind == 'groups' else 0
        best = [b.model_dump() for b in ev.config.advance.best] if kind == 'groups' else []
        ev.group_done = [len(results[g]) >= expected[g - 1] for g in range(1, len(groups) + 1)]
        ev.tables, ev.outcome = group_outcome(groups, results, criteria, {int(k) if k.isdigit() else k: v for k, v in lots.items()},
                                              per_group, best, expected)
        ev.rounds_total = max((f.round_no for f in ev.fixtures), default=0)
    elif kind == 'swiss':
        teams = [str(t) for t in ev.draw.placement]
        ev.rounds_total = ev.config.rounds or max(1, (len(teams) - 1).bit_length())
        results = [_result(ev.legs[f.id]) for f in ev.fixtures if f.id in ev.legs]
        byes = [(str(f.home_entry_id or _entry(f.home_source)), win_points) for f in ev.fixtures if f.bye]
        rows = rank(teams, results, criteria, lots.get('1', ()), byes)
        ev.tables = [rows]
        played_rounds = max((f.round_no for f in ev.fixtures), default=0)
        done = all(f.bye or f.id in ev.legs for f in ev.fixtures)
        ev.outcome = Outcome(complete=done and played_rounds >= ev.rounds_total)
        if ev.outcome.complete: ev.outcome.final = {r.place: r.team for r in rows if not r.tied}
        ev.group_done = [ev.outcome.complete]
    else:
        specs = [spec_of(f) for f in ev.fixtures]
        legs_by_key = {}
        for f in sorted(ev.fixtures, key=lambda f: f.leg):
            if f.id in ev.legs: legs_by_key.setdefault(f.key, []).append(ev.legs[f.id])
        ev.pairs = resolve_bracket(specs, legs_by_key, ev.prior)
        final_key = 'F' if kind == 'double_elim' else f'U{max((f.round_no for f in ev.fixtures if f.bracket == "upper"), default=1)}-1'
        final = ev.pairs.get(final_key)
        reset = ev.pairs.get('F2')
        champion = reset.winner if reset and reset.home else (final.winner if final else None)
        ev.outcome = Outcome(complete=champion is not None)
        if champion: ev.outcome.final = {1: champion}
    # Вычисленные по источникам команды — для «Результат изменился» и назначения.
    pairs = ev.pairs
    prior = _separated(ev) if kind in ELIMINATION else None
    for f in ev.fixtures:
        if kind in ELIMINATION:
            ev.computed[f.id] = (resolve_source(f.home_source, pairs, prior), resolve_source(f.away_source, pairs, prior))
        else:
            ev.computed[f.id] = (_entry(f.home_source), _entry(f.away_source))


def _separated(ev):
    from aifootball.service.stages.rules.progress import _separate_best
    return _separate_best([spec_of(f, fixed=False) for f in ev.fixtures], ev.prior)


def _entry(source): return source.get('entry') if source else None


def _result(leg): return Result(leg.home, leg.away, leg.home_goals, leg.away_goals, leg.points)


def _status(ev, confirmed):
    if ev.draw is None: return 'draft'
    if ev.outcome.complete: return 'completed'
    return 'started' if any(f.match_id in confirmed for f in ev.fixtures) else 'drawn'


# Представления.

def _team(refs, team):
    return refs.get(str(team)) if team else None


def _numbers(fixtures):
    keys = []
    for f in sorted(fixtures, key=lambda f: (_stage_order(spec_of(f, False)), f.key)):
        if not f.bye and f.key not in keys: keys.append(f.key)
    return {k: i for i, k in enumerate(keys, 1)}


def _side(refs, team, source, numbers):
    ref = _team(refs, team)
    return {'team': ref, 'label': ref['name'] if ref else source_label(source, numbers)}


def stage_view(ev, refs, matches, scope):
    stage, config = ev.stage, ev.config
    view = {'id': stage.id, 'position': stage.position, 'name': stage.name, 'kind': config.kind, 'status': ev.status,
            'criteria': list(config.effective_criteria()), 'groups': [], 'sections': []}
    if scope == 'cabinet':
        view.update(config=stage.config, regulation_id=stage.regulation_id, revision=stage.revision,
                    draw={'id': ev.draw.id, 'version': ev.draw.version, 'method': ev.draw.method, 'seed': ev.draw.seed,
                          'seeding': ev.draw.seeding, 'placement': ev.draw.placement, 'confirmed_at': ev.draw.confirmed_at}
                    if ev.draw else None)
    if ev.draw is None: return view
    view['groups'] = _group_views(ev, refs)
    view['sections'] = _sections(ev, refs, matches, scope)
    if config.kind == 'swiss' and scope == 'cabinet':
        last = max((f.round_no for f in ev.fixtures), default=0)
        view['can_next_round'] = last < ev.rounds_total and all(f.bye or f.id in ev.legs for f in ev.fixtures)
    return view


def _group_views(ev, refs):
    config = ev.config; groups = []
    advance = config.advance.per_group if config.kind == 'groups' else (config.playoff_teams or 0)
    best_rows = {}
    if config.kind == 'groups':
        for item in config.advance.best:
            candidates = [r for rows in ev.tables for r in rows if r.place == item.place]
            ordered, _ = rank_across(candidates)
            best_rows.update({r.team: 'best' for r in ordered[:item.count]})
    for g, rows in enumerate(ev.tables, 1):
        name = group_name(g) if config.kind == 'groups' else 'Таблица'
        done = ev.group_done[g - 1] if g <= len(ev.group_done) else False
        groups.append({'group_no': g, 'name': name, 'needs_lot': done and any(r.tied for r in rows), 'rows': [
            {'place': r.place, 'team': refs[r.team], 'played': r.played, 'won': r.won, 'drawn': r.drawn, 'lost': r.lost,
             'goals_for': r.goals_for, 'goals_against': r.goals_against, 'goal_diff': r.goal_diff, 'points': r.points,
             'tied': done and r.tied, 'zone': 'advance' if r.place <= advance else best_rows.get(r.team)}
            for r in rows if r.team in refs]})
    return groups


def _pair_views(ev, refs, matches, scope):
    config = ev.config; numbers = _numbers(ev.fixtures)
    upper_total = max((f.round_no for f in ev.fixtures if f.bracket == 'upper'), default=0)
    by_key = {}
    for f in ev.fixtures: by_key.setdefault(f.key, []).append(f)
    views = []
    for key, items in by_key.items():
        items.sort(key=lambda f: f.leg); main = items[-1]
        state = ev.pairs.get(key)
        if config.kind in ELIMINATION:
            if key == 'F2' and not (state and state.home): continue
            home, away = (state.home, state.away) if state else (None, None)
            # Матчи пары, назначенные зафиксированными командами, показывают их.
            if main.home_entry_id: home = str(main.home_entry_id)
            if main.away_entry_id: away = str(main.away_entry_id)
        else:
            home, away = _entry(main.home_source), _entry(main.away_source)
        legs = []; complete = True
        for f in items:
            leg = ev.legs.get(f.id); match = matches.get(f.match_id)
            score = shootout = None
            if leg:
                flip = str(f.home_entry_id or _entry(f.home_source) or '') == leg.away
                score = {'home': leg.away_goals if flip else leg.home_goals, 'away': leg.home_goals if flip else leg.away_goals}
                if leg.home_pens is not None:
                    shootout = {'home': leg.away_pens if flip else leg.home_pens, 'away': leg.home_pens if flip else leg.away_pens}
            elif not f.bye: complete = False
            legs.append({'match_id': f.match_id, 'fixture_id': f.id if scope == 'cabinet' else None, 'leg': f.leg,
                         'scheduled_at': match.scheduled_at if match else None, 'status': match.status if match else None,
                         'score': score, 'shootout': shootout})
        winner = None; note = None
        if config.kind in ELIMINATION and state:
            if state.winner and state.winner == home: winner = 'home'
            elif state.winner and state.winner == away: winner = 'away'
            elif complete and home and away and not main.bye: note = 'Победитель не определён'
        changed = scope == 'cabinet' and any(f.match_id and _changed(ev, f) for f in items)
        if changed: note = 'Результат изменился'
        can_schedule = scope == 'cabinet' and any(_can_schedule(ev, f) for f in items)
        views.append({'key': key, 'round_no': main.round_no, 'slot': main.slot, 'bracket': main.bracket, 'group_no': main.group_no,
                      'label': pair_label(config.kind, main, upper_total), 'bye': main.bye,
                      'home': _side(refs, home, main.home_source, numbers), 'away': _side(refs, away, main.away_source, numbers),
                      'legs': legs, 'winner': winner, 'note': note, 'can_schedule': can_schedule, 'changed': changed})
    return views


def _changed(ev, f):
    home, away = ev.computed.get(f.id, (None, None))
    return (str(f.home_entry_id) if f.home_entry_id else None, str(f.away_entry_id) if f.away_entry_id else None) != (home, away)


def _can_schedule(ev, f):
    if f.match_id or f.bye: return False
    home, away = ev.computed.get(f.id, (None, None))
    if f.key == 'F2':
        state = ev.pairs.get('F2')
        if not (state and state.home): return False
    return bool(home and away and home != away)


def _sections(ev, refs, matches, scope):
    pairs = _pair_views(ev, refs, matches, scope); kind = ev.config.kind
    def rounds(items, namer):
        by_round = {}
        for p in items: by_round.setdefault(p['round_no'], []).append(p)
        return [{'round_no': r, 'name': namer(r, by_round[r]), 'pairs': sorted(by_round[r], key=lambda p: (p['group_no'] or 0, p['slot']))}
                for r in sorted(by_round)]
    if kind not in ELIMINATION:
        return [{'key': 'rounds', 'name': 'Туры', 'rounds': rounds(pairs, lambda r, _: f'Тур {r}')}]
    upper_total = max((p['round_no'] for p in pairs if p['bracket'] == 'upper'), default=0)
    upper = [p for p in pairs if p['bracket'] in ('upper', 'third')]
    def upper_name(r, items):
        return round_name(kind, 'upper', r, upper_total, ) if any(p['bracket'] == 'upper' for p in items) else 'Матч за 3-е место'
    sections = [{'key': 'upper', 'name': 'Верхняя сетка' if kind == 'double_elim' else 'Сетка', 'rounds': rounds(upper, upper_name)}]
    if kind == 'double_elim':
        lower = [p for p in pairs if p['bracket'] == 'lower']
        sections.append({'key': 'lower', 'name': 'Нижняя сетка', 'rounds': rounds(lower, lambda r, _: f'Раунд {r}')})
        finals = [p for p in pairs if p['bracket'] in ('final', 'final_reset')]
        sections.append({'key': 'final', 'name': 'Финал', 'rounds': [
            {'round_no': p['round_no'], 'name': p['label'], 'pairs': [p]} for p in sorted(finals, key=lambda p: p['round_no'])]})
    return sections


def _matches(db, evaluated):
    ids = [f.match_id for ev in evaluated for f in ev.fixtures if f.match_id]
    return {m.id: m for m in db.scalars(select(Match).where(Match.id.in_(ids)))} if ids else {}


def standings(db, tournament, scope, implicit=True):
    """implicit=False — только настоящие этапы (кабинетный список этапов без общей таблицы)."""
    stages = stages_of(db, tournament.id)
    refs = team_refs(db, tournament.id)
    if not stages:
        return implicit_standings(db, tournament, scope, refs) if implicit else {'implicit': False, 'stages': []}
    evaluated = evaluate(db, tournament, scope, stages)
    matches = _matches(db, evaluated)
    views = [stage_view(ev, refs, matches, scope) for ev in evaluated]
    if scope == 'public': views = [v for v in views if v['status'] != 'draft']
    return {'implicit': False, 'stages': views}


def implicit_standings(db, tournament, scope, refs):
    """Турнир без формата: одна таблица по всем матчам с результатом."""
    if scope == 'public' and not tournament.standings_public: return {'implicit': True, 'stages': []}
    if not refs: return {'implicit': True, 'stages': []}
    ids = list(db.scalars(select(Match.id).where(Match.tournament_id == tournament.id)))
    legs = load_results(db, ids, scope).values()
    rows = rank(list(refs), [_result(l) for l in legs])
    group = {'group_no': 1, 'name': 'Турнирная таблица', 'needs_lot': False, 'rows': [
        {'place': r.place, 'team': refs[r.team], 'played': r.played, 'won': r.won, 'drawn': r.drawn, 'lost': r.lost,
         'goals_for': r.goals_for, 'goals_against': r.goals_against, 'goal_diff': r.goal_diff, 'points': r.points,
         'tied': False, 'zone': None} for r in rows]}
    return {'implicit': True, 'stages': [{'position': 1, 'name': 'Турнирная таблица', 'kind': 'round_robin',
                                          'status': 'started' if legs else 'drawn',
                                          'criteria': ['points', 'h2h_points', 'h2h_goal_diff', 'h2h_goals', 'goal_diff', 'goals_for', 'wins'],
                                          'groups': [group], 'sections': []}]}


def fixture_list(db, tournament, scope, unscheduled=False):
    stages = stages_of(db, tournament.id); refs = team_refs(db, tournament.id)
    evaluated = evaluate(db, tournament, scope, stages); items = []
    for ev in evaluated:
        numbers = _numbers(ev.fixtures)
        upper_total = max((f.round_no for f in ev.fixtures if f.bracket == 'upper'), default=0)
        legs_of = {}
        for f in ev.fixtures: legs_of[f.key] = max(legs_of.get(f.key, 1), f.leg)
        for f in ev.fixtures:
            if f.bye or (unscheduled and f.match_id): continue
            if f.key == 'F2' and not (ev.pairs.get('F2') and ev.pairs['F2'].home): continue
            home, away = ev.computed.get(f.id, (None, None))
            if f.home_entry_id: home = str(f.home_entry_id)
            if f.away_entry_id: away = str(f.away_entry_id)
            items.append({'id': f.id, 'stage_id': ev.stage.id, 'stage_name': ev.stage.name, 'key': f.key, 'leg': f.leg,
                          'round_no': f.round_no, 'group_no': f.group_no, 'bracket': f.bracket,
                          'label': pair_label(ev.config.kind, f, upper_total, legs_of[f.key]),
                          'home': _side(refs, home, f.home_source, numbers), 'away': _side(refs, away, f.away_source, numbers),
                          'match_id': f.match_id, 'can_schedule': scope == 'cabinet' and _can_schedule(ev, f)})
    return {'items': items, 'total': len(items)}


# Формат.

def _assert_open(tournament):
    if tournament.archived: raise DomainError('archived', 'Турнир в архиве')


def _regulation(db, tournament, rid):
    reg = get_entity(db, RegulationVersion, rid)
    if reg.tournament_id != tournament.id: raise DomainError('foreign_tournament', 'Выберите регламент этого турнира')
    return reg


def create_format(db, tournament, data):
    _assert_open(tournament)
    stages = stages_of(db, tournament.id, lock=True)
    if any(current_draw(db, s.id) for s in stages):
        raise DomainError('format_locked', 'Формат нельзя изменить: жеребьёвка уже проведена', status=409)
    _regulation(db, tournament, data.regulation_id)
    playoff_reg = data.playoff_regulation_id or data.regulation_id
    _regulation(db, tournament, playoff_reg)
    for s in stages: db.delete(s)
    db.flush()
    created = []
    for i, item in enumerate(template_stages(data.template, data.model_dump()), 1):
        row = Stage(tournament_id=tournament.id, position=i, name=item['name'], kind=item['kind'],
                    regulation_id=playoff_reg if item.get('playoff') else data.regulation_id,
                    config=StageConfig.model_validate(item['config']).model_dump(mode='json'), lots={}, revision=0)
        db.add(row); created.append(row)
    db.flush()
    return standings(db, tournament, 'cabinet')


def patch_stage(db, tournament, stage, data):
    _assert_open(tournament)
    if stage.revision != data.expected_revision: raise stage_conflict(stage)
    if data.config is not None:
        if current_draw(db, stage.id):
            raise DomainError('draw_exists', 'Настройки этапа меняются до жеребьёвки', status=409)
        if data.config.kind != stage.kind: raise DomainError('validation', 'Вид этапа меняется сменой формата')
        stage.config = data.config.model_dump(mode='json')
    if data.regulation_id is not None:
        _regulation(db, tournament, data.regulation_id); stage.regulation_id = data.regulation_id
    if data.name is not None: stage.name = data.name
    stage.revision += 1
    db.flush()
    return standings(db, tournament, 'cabinet')


# Жеребьёвка.

def _previous(db, tournament, stage):
    stages = stages_of(db, tournament.id)
    index = next(i for i, s in enumerate(stages) if s.id == stage.id)
    return (stages[index - 1] if index else None), stages


def _participants(db, tournament, stage, config):
    """Заявки, которые разыгрываются в этапе, в порядке посева по умолчанию; None — участники пока неизвестны."""
    refs = team_refs(db, tournament.id)
    if not config.source.get('previous'): return list(refs)
    prior_stage, stages = _previous(db, tournament, stage)
    if prior_stage is None: raise DomainError('validation', 'У первого этапа нет предыдущего')
    ev = next(e for e in evaluate(db, tournament, 'cabinet', stages) if e.stage.id == prior_stage.id)
    prior_config = ev.config; outcome = ev.outcome
    if prior_config.kind == 'groups':
        order = [outcome.places.get((g, p)) for p in range(1, prior_config.advance.per_group + 1)
                 for g in range(1, prior_config.group_count + 1)]
        order += [outcome.best.get((b.place, r)) for b in prior_config.advance.best for r in range(1, b.count + 1)]
    else:
        order = [outcome.final.get(n) for n in range(1, qualifier_count(prior_config) + 1)]
    return None if not order or None in order else order


def _placement(db, tournament, stage, data):
    config = config_of(stage)
    if data.method == 'scheme':
        prior_stage, _ = _previous(db, tournament, stage)
        if not config.source.get('previous') or prior_stage is None:
            raise DomainError('validation', 'Схема доступна для этапа после групп или лиги')
        base = scheme_for(config, config_of(prior_stage))
        return config, base, [], base if data.placement is None else _same_items(data.placement, base)
    participants = _participants(db, tournament, stage, config)
    if participants is None: raise DomainError('previous_incomplete', 'Предыдущий этап ещё не завершён', status=409)
    seeding = [str(s) for s in data.seeding] or participants
    if sorted(seeding) != sorted(participants) or len(set(seeding)) != len(seeding):
        raise DomainError('validation', 'Посев должен содержать каждую команду этапа ровно один раз')
    if len(seeding) < 2: raise DomainError('validation', 'Для жеребьёвки нужны минимум две команды')
    if data.method == 'manual':
        if data.placement is None: raise DomainError('validation', 'Передайте расстановку')
        if config.kind == 'groups':
            groups = [[str(t) for t in g] for g in data.placement]
            if len(groups) != config.group_count or any(len(g) < 2 for g in groups) or \
                    sorted(t for g in groups for t in g) != sorted(seeding):
                raise DomainError('validation', 'Каждая команда должна попасть ровно в одну группу, в группе минимум две команды')
            return config, groups, seeding, groups
        base = participants_placement(config, 'seeded', seeding, 0)
        return config, base, seeding, _same_items(data.placement, base)
    placement = participants_placement(config, data.method, seeding, data.seed)
    return config, placement, seeding, placement


def _same_items(given, base):
    norm = lambda items: sorted(repr(sorted(i.items())) if isinstance(i, dict) else repr(i) for i in items)
    given = [({k: (str(v) if k == 'entry' else v) for k, v in i.items()} if isinstance(i, dict) else (str(i) if i is not None else None))
             for i in given]
    if norm(given) != norm(base): raise DomainError('validation', 'Расстановка должна содержать те же команды')
    return given


def _consequences(db, stage, specs):
    old = draw_fixtures(db, current_draw(db, stage.id))
    new = {(s.key, s.leg): (_entry(s.home), _entry(s.away)) for s in specs}
    matches = {m.id: m for m in db.scalars(select(Match).where(Match.id.in_([f.match_id for f in old if f.match_id])))} \
        if any(f.match_id for f in old) else {}
    kept, cancelled = [], []
    for f in old:
        match = matches.get(f.match_id)
        if not match or match.status == 'cancelled': continue
        teams = (str(match.home_entry_id), str(match.away_entry_id))
        (kept if new.get((f.key, f.leg)) == teams else cancelled).append((f, match))
    return kept, cancelled


def _preview_pairs(config, specs, refs):
    numbers = {}; i = 0
    for s in sorted(specs, key=lambda s: (_stage_order(s), s.key)):
        if not s.bye and s.key not in numbers: i += 1; numbers[s.key] = i
    upper_total = max((s.round_no for s in specs if s.bracket == 'upper'), default=0)
    seen = set(); pairs = []
    for s in specs:
        if s.key in seen: continue
        seen.add(s.key)
        main = max((x for x in specs if x.key == s.key), key=lambda x: x.leg)
        side = lambda src: _side(refs, _entry(src), src, numbers)
        pairs.append({'key': main.key, 'round_no': main.round_no, 'slot': main.slot, 'bracket': main.bracket,
                      'group_no': main.group_no, 'label': pair_label(config.kind, main, upper_total), 'bye': main.bye,
                      'home': side(main.home), 'away': side(main.away), 'legs': []})
    return pairs


def preview_draw(db, tournament, stage, data):
    refs = team_refs(db, tournament.id)
    config, _, seeding, placement = _placement(db, tournament, stage, data)
    specs = fixtures_for(config, placement)
    kept, cancelled = _consequences(db, stage, specs)
    groups = [[refs[t] for t in g] for g in placement] if config.kind == 'groups' else []
    pots = {t: i // config.group_count + 1 for i, t in enumerate(seeding)} if config.kind == 'groups' else {}
    return {'method': data.method, 'seed': data.seed, 'seeding': seeding, 'placement': placement, 'groups': groups,
            'pairs': _preview_pairs(config, specs, refs), 'pots': pots, 'kept': len(kept), 'cancelled': len(cancelled)}


def _stage_has_result(db, stage):
    ids = [f.match_id for f in draw_fixtures(db, current_draw(db, stage.id)) if f.match_id]
    return bool(confirmed_match_ids(db, ids))


def confirm_draw(db, actor, tournament, stage, data):
    _assert_open(tournament)
    stage = get_entity(db, Stage, stage.id, lock=True)
    if stage.revision != data.expected_revision: raise stage_conflict(stage)
    if _stage_has_result(db, stage):
        raise DomainError('draw_locked', 'Жеребьёвку нельзя изменить: в этапе уже есть подтверждённый результат', status=409)
    config, _, seeding, placement = _placement(db, tournament, stage, data)
    specs = fixtures_for(config, placement)
    kept, cancelled = _consequences(db, stage, specs)
    version = (db.scalar(select(func.max(StageDraw.version)).where(StageDraw.stage_id == stage.id)) or 0) + 1
    draw = StageDraw(stage_id=stage.id, version=version, method=data.method, seed=data.seed, seeding=seeding,
                     placement=placement, confirmed_by=actor.id)
    db.add(draw); db.flush()
    moved = {(f.key, f.leg): (f, m) for f, m in kept}
    for f, _ in kept: f.match_id = None
    db.flush()
    for spec in specs:
        row = _fixture_row(stage, draw, spec)
        if (spec.key, spec.leg) in moved:
            old, match = moved[(spec.key, spec.leg)]
            row.match_id = match.id; row.home_entry_id = match.home_entry_id; row.away_entry_id = match.away_entry_id
        db.add(row)
    for f, match in cancelled:
        match.status = 'cancelled'; match.revision += 1
    stage.revision += 1
    db.flush()
    return standings(db, tournament, 'cabinet')


def _fixture_row(stage, draw, spec):
    return Fixture(stage_id=stage.id, draw_id=draw.id, key=spec.key, leg=spec.leg, group_no=spec.group_no,
                   round_no=spec.round_no, bracket=spec.bracket, slot=spec.slot, bye=spec.bye,
                   home_source=spec.home, away_source=spec.away)


# Жребий и швейцарка.

def set_lot(db, tournament, stage, data):
    _assert_open(tournament)
    ev = next(e for e in evaluate(db, tournament, 'cabinet') if e.stage.id == stage.id)
    order = [str(t) for t in data.order]
    if data.group.startswith('best-'):
        members = {r.team for rows in ev.tables for r in rows}
    else:
        if not data.group.isdigit() or not 1 <= int(data.group) <= len(ev.tables):
            raise DomainError('validation', 'Нет такой группы')
        members = {r.team for r in ev.tables[int(data.group) - 1]}
    if not set(order) <= members or len(set(order)) != len(order):
        raise DomainError('validation', 'Жребий вводится для команд этой группы')
    stage.lots = {**(stage.lots or {}), data.group: order}
    stage.revision += 1
    db.flush()
    return standings(db, tournament, 'cabinet')


def next_swiss_round(db, actor, tournament, stage, data):
    _assert_open(tournament)
    stage = get_entity(db, Stage, stage.id, lock=True)
    if stage.revision != data.expected_revision: raise stage_conflict(stage)
    ev = next(e for e in evaluate(db, tournament, 'cabinet') if e.stage.id == stage.id)
    if ev.config.kind != 'swiss' or ev.draw is None: raise DomainError('validation', 'Следующий тур — только для швейцарской системы')
    last = max((f.round_no for f in ev.fixtures), default=0)
    if last >= ev.rounds_total: raise DomainError('swiss_done', 'Все туры уже составлены', status=409)
    if not all(f.bye or f.id in ev.legs for f in ev.fixtures):
        raise DomainError('round_incomplete', 'Сначала подтвердите результаты всех матчей тура', status=409)
    ranked = [r.team for r in ev.tables[0]]
    played = {frozenset((str(f.home_entry_id or _entry(f.home_source)), str(f.away_entry_id or _entry(f.away_source))))
              for f in ev.fixtures if not f.bye}
    had_bye = {str(f.home_entry_id or _entry(f.home_source)) for f in ev.fixtures if f.bye}
    homes = {}
    for f in ev.fixtures:
        if not f.bye: team = str(f.home_entry_id or _entry(f.home_source)); homes[team] = homes.get(team, 0) + 1
    found = swiss_pairs(ranked, played, had_bye, homes)
    if found is None: raise DomainError('swiss_exhausted', 'Пары без повторов больше не составить', status=409)
    pairs, bye = found; r = last + 1
    for i, (home, away) in enumerate(pairs, 1):
        db.add(_fixture_row(stage, ev.draw, FixtureSpec(f'S{r}-{i}', r, {'entry': home}, {'entry': away}, slot=i)))
    if bye:
        db.add(_fixture_row(stage, ev.draw, FixtureSpec(f'S{r}-{len(pairs) + 1}', r, {'entry': bye}, None,
                                                        slot=len(pairs) + 1, bye=True)))
    stage.revision += 1
    db.flush()
    return standings(db, tournament, 'cabinet')


# Назначение и замена.

def _fixture_context(db, fixture_id):
    fixture = get_entity(db, Fixture, fixture_id, lock=True)
    stage = get_entity(db, Stage, fixture.stage_id)
    draw = current_draw(db, stage.id)
    if draw is None or draw.id != fixture.draw_id: raise DomainError('not_found', 'Пара не найдена', status=404)
    return fixture, stage


def schedule_fixture(db, actor, tournament, fixture_id, data):
    from aifootball.service.matches.schemas import MatchCreate
    from aifootball.service.matches.operations import create_match
    _assert_open(tournament)
    fixture, stage = _fixture_context(db, fixture_id)
    if fixture.match_id: raise DomainError('already_scheduled', 'Матч этой пары уже назначен', status=409)
    if fixture.bye: raise DomainError('validation', 'В паре пропуск хода, матча не будет')
    ev = next(e for e in evaluate(db, tournament, 'cabinet') if e.stage.id == stage.id)
    current = next(f for f in ev.fixtures if f.id == fixture.id)
    if not _can_schedule(ev, current):
        raise DomainError('opponent_unknown', 'Соперник ещё не известен')
    home, away = ev.computed[fixture.id]
    legs = max(f.leg for f in ev.fixtures if f.key == fixture.key)
    upper_total = max((f.round_no for f in ev.fixtures if f.bracket == 'upper'), default=0)
    body = MatchCreate(home_entry_id=home, away_entry_id=away, regulation_id=stage.regulation_id,
                       stage_label=pair_label(ev.config.kind, fixture, upper_total, legs),
                       **data.model_dump(exclude={'request_id', 'stage_label'}))
    view = create_match(db, tournament.id, body, actor)
    fixture.match_id = view['id']; fixture.home_entry_id = home; fixture.away_entry_id = away
    db.flush()
    return view


def replace_team(db, tournament, fixture_id, data):
    from aifootball.service.matches.operations import get_match_view
    _assert_open(tournament)
    fixture, stage = _fixture_context(db, fixture_id)
    entry = get_entity(db, Entry, data.entry_id)
    if entry.tournament_id != tournament.id: raise DomainError('foreign_tournament', 'Выберите команду этого турнира')
    if fixture.match_id and confirmed_match_ids(db, [fixture.match_id]):
        raise DomainError('result_confirmed', 'У матча уже есть подтверждённый протокол', status=409)
    match = get_entity(db, Match, fixture.match_id, lock=True) if fixture.match_id else None
    if match and match.protocol.get('events'):
        raise DomainError('protocol_started', 'Сначала очистите события протокола матча', status=409)
    other = fixture.away_entry_id if data.side == 'home' else fixture.home_entry_id
    if other == entry.id: raise DomainError('same_team', 'Команды пары должны отличаться')
    source = fixture.home_source if data.side == 'home' else fixture.away_source
    if source is None or 'entry' in source:
        setattr(fixture, f'{data.side}_source', {'entry': str(entry.id)})
    setattr(fixture, f'{data.side}_entry_id', entry.id)
    if match:
        if (match.away_entry_id if data.side == 'home' else match.home_entry_id) == entry.id:
            raise DomainError('same_team', 'Команды матча должны отличаться')
        for member in db.scalars(select(LineupMember).where(LineupMember.match_id == match.id, LineupMember.side == data.side)):
            db.delete(member)
        setattr(match, f'{data.side}_entry_id', entry.id); match.revision += 1
    db.flush()
    return get_match_view(db, match.id) if match else {'id': fixture.id}
