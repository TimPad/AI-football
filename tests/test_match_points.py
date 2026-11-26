from aifootball.ratings.match_points import load_policy, match_points

POLICY = load_policy()
H1, H2, HG, A1, AG = 'h1', 'h2', 'hg', 'a1', 'ag'
LINEUP = [
    {'player_id': H1, 'side': 'home', 'display_name': 'Хозяин 1'},
    {'player_id': H2, 'side': 'home', 'display_name': 'Хозяин 2'},
    {'player_id': HG, 'side': 'home', 'display_name': 'Вратарь хозяев'},
    {'player_id': A1, 'side': 'away', 'display_name': 'Гость 1'},
    {'player_id': AG, 'side': 'away', 'display_name': 'Вратарь гостей'},
    {'player_id': 'bench', 'side': 'away', 'display_name': 'Запасной'},
]
GOALKEEPERS = {'home': [{'player_id': HG, 'intervals': None}], 'away': [{'player_id': AG, 'intervals': None}]}


def goal(id_, side, player, t, assist=None, own=False):
    return {'id': id_, 'side': side, 'player_id': player, 'assist_id': assist, 'own_goal': own, 't': t}


def act(kind, side, player, t, **kw):
    return {'kind': kind, 'side': side, 'player_id': player, 't': t, 'on_target': None, 'outcome': None} | kw


def compute(**kw):
    args = {
        'lineup': LINEUP,
        'goals': [],
        'cards': [],
        'actions': [],
        'passes': {},
        'goalkeepers': GOALKEEPERS,
        'presence': {},
        'partial': [],
        'policy': POLICY,
    } | kw
    return match_points(**args)


def by_player(result):
    return {i['player_id']: i for i in result['items']}


def parts(item):
    return {p['key']: (p['count'], p['points']) for p in item['parts']}


def test_points_for_goals_shots_defence_passes_cards_and_goalkeepers():
    result = compute(
        goals=[
            goal('g1', 'home', H1, 100, assist=H2),
            goal('g2', 'away', A1, 200, own=True),  # автогол гостя — гол хозяев
            goal('g3', 'away', A1, 300),
        ],
        cards=[{'player_id': A1, 'card': 'yellow'}],
        actions=[
            act('shot', 'home', H1, 50, on_target=True, outcome='saved'),
            act('save', 'away', None, 50),  # сейв без игрока — вратарю гостей
            act('duel', 'home', H2, 60, success=True),
            act('recovery', 'home', None, 60),  # часть того же отбора, не перехват
            act('duel', 'away', None, 60, success=False),
            act('recovery', 'away', A1, 70),
            act('shot_block', 'home', H2, 80),
            act('save', 'home', HG, 90),
            act('shot', 'away', A1, 95, on_target=False, outcome='off_target'),
        ],
        passes={H2: 50},
        presence={H1: [[0, 250]], H2: [[0, 400]]},
    )
    items = by_player(result)
    assert parts(items[H1]) == {'goal': (1, 1.0), 'shot_on_target': (1, 0.15), 'team_goal': (2, 0.2)}
    assert items[H1]['rating'] == 7.4
    assert parts(items[H2]) == {
        'assist': (1, 0.6),
        'tackle': (1, 0.15),
        'shot_block': (1, 0.15),
        'pass': (50, 0.4),
        'team_goal': (2, 0.2),
        'team_conceded': (1, -0.1),
    }
    assert items[H2]['rating'] == 7.4
    assert parts(items[HG]) == {'save': (1, 0.2), 'goal_conceded': (1, -0.4)}
    assert items[HG]['rating'] == 5.8 and items[HG]['goalkeeper']
    assert parts(items[A1]) == {'goal': (1, 1.0), 'interception': (1, 0.1), 'yellow': (1, -0.3), 'own_goal': (1, -0.5)}
    assert items[A1]['rating'] == 6.3
    assert parts(items[AG]) == {'save': (1, 0.2), 'goal_conceded': (2, -0.8)}
    assert items[AG]['rating'] == 5.4
    # Без действий и без времени на площадке оценки нет.
    assert 'bench' not in items
    # Лучший — по неокруглённой сумме: 7,40 у второго против 7,35 у первого.
    assert result['best_player_id'] == H2
    assert result['ready'] is True
    assert result['missing']['goals_without_author'] == 0
    assert result['missing']['actions_without_player'] == 0
    # У гостя 1 неизвестно время на площадке — плюс-минус посчитан не у всех.
    assert result['missing']['without_on_court'] == 1
    assert result['complete'] is False


def test_unknown_authors_block_the_rating_and_are_counted():
    result = compute(goals=[goal('g1', 'home', None, 100), goal('g2', 'home', None, 200)], passes={H1: 10})
    assert result['ready'] is False
    assert result['missing']['goals_without_author'] == 2
    assert result['missing']['goals_total'] == 2


def test_goalkeeper_by_time_and_unattributed_save():
    keepers = {
        'home': [{'player_id': HG, 'intervals': [[0, 150]]}, {'player_id': H2, 'intervals': [[150, 400]]}],
        'away': [],
    }
    result = compute(
        goals=[goal('g1', 'away', A1, 100), goal('g2', 'away', A1, 300)],
        actions=[act('save', 'home', None, None), act('save', 'home', None, 120)],
        goalkeepers=keepers,
    )
    items = by_player(result)
    assert parts(items[HG]) == {'save': (1, 0.2), 'goal_conceded': (1, -0.4)}
    assert parts(items[H2]) == {'goal_conceded': (1, -0.4)}
    assert items[H2]['goalkeeper'] is True
    assert result['missing']['actions_without_player'] == 1
    assert result['missing']['goalkeeper_unknown'] == ['away']


def test_rating_is_clamped_and_a_red_card_costs():
    result = compute(
        goals=[goal(f'g{i}', 'home', H1, i) for i in range(8)] + [goal('o1', 'away', A1, 50, own=True)],
        cards=[{'player_id': A1, 'card': 'red'}, {'player_id': A1, 'card': 'yellow'}],
    )
    items = by_player(result)
    assert items[H1]['rating'] == 10.0
    assert parts(items[A1]) == {'yellow': (1, -0.3), 'red': (1, -1.5), 'own_goal': (1, -0.5)}
    assert items[A1]['rating'] == 3.7
    # Девять пропущенных: 6,0 − 3,6 = 2,4 → нижняя граница 3,0.
    assert items[AG]['rating'] == 3.0


def test_recovery_without_player_outside_a_tackle_is_missing():
    result = compute(
        actions=[act('recovery', 'home', None, 500), act('shot', 'home', None, 10, on_target=True)],
        goalkeepers={'home': [], 'away': []},
    )
    assert result['missing']['actions_without_player'] == 2
    assert result['items'] == []
