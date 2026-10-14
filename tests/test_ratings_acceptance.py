import importlib.util
from pathlib import Path


def test_independent_synthetic_acceptance_covers_all_roles_and_small_samples():
    path=Path('scripts/verify_tournament_ratings.py')
    spec=importlib.util.spec_from_file_location('rating_acceptance',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    report=module.verify()
    assert report['player_matches']==100 and report['players_per_role']==5 and report['player_matches_per_role']==20
    assert report['independent_formula_checks']==100
    assert report['sporting_accuracy_verified'] is False
    assert report['sensitivity']['max_score_change']>0
