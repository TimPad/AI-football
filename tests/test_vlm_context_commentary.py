from copy import deepcopy
from dataclasses import replace
import json

import pytest

from test_joint_vlm_pilot import environment
from test_vlm_match_context import SOURCE,passport,document


def response():
    return {'schema_version':'joint-context-v2','time_basis':'window',**document()}


def test_prompt_contains_passport_and_bounded_memory_without_free_commentary(tmp_path):
    from aifootball.understanding.context_pilot import context_prompt
    from aifootball.understanding.match_context import MatchChronology
    window,_,_=environment(tmp_path);p=passport();history=MatchChronology(SOURCE,p)
    prompt=json.loads(context_prompt(window,context={'scope':'continuous_excerpt'},passport=p,memory=history.snapshot(0)))
    assert prompt['schema_version']=='joint-context-v2'
    assert prompt['match_passport']['facts']['match_status']['value']=='in_progress'
    assert 'commentary' not in prompt['response'] and 'visual_signals' in prompt['fields']['events']
    assert prompt['response']['open_questions']==[]


def test_supported_response_is_valid_and_raw_is_unchanged(tmp_path):
    from aifootball.understanding.context_pilot import project_context
    window,_,_=environment(tmp_path);raw=response();before=deepcopy(raw)
    projected,repairs=project_context(raw,window)
    assert raw==before and projected['events'][0]['visual_signals']==raw['events'][0]['visual_signals']
    assert projected['states'][0]['kind']=='playing' and repairs==[]


def test_invalid_visual_signals_and_future_open_question_refs_are_rejected(tmp_path):
    from aifootball.understanding.context_pilot import project_context
    window,_,_=environment(tmp_path);raw=response();raw['events'][0]['visual_signals']=['inferred_from_mood']
    with pytest.raises(ValueError):project_context(raw,window)
    raw=response();raw['open_questions']=[{'kind':'unknown-question','detail':'???'}]
    with pytest.raises(ValueError):project_context(raw,window)


@pytest.mark.parametrize('kind,signals',[('playing',[]),('playing',['players_stopped']),
                                      ('stoppage',['whistle_only']),('stoppage',['players_stopped'])])
def test_no_ball_and_static_players_do_not_establish_game_state(tmp_path,kind,signals):
    from aifootball.understanding.context_pilot import project_context
    window,_,_=environment(tmp_path);raw=response();raw['states'][0].update(kind=kind,visual_signals=signals)
    projected,repairs=project_context(raw,window)
    assert projected['states'][0]['kind']=='unknown' and repairs
    assert raw['states'][0]['kind']==kind


def test_approach_to_goal_does_not_create_shot_or_highlight_line(tmp_path):
    from aifootball.understanding.context_pilot import project_context
    from aifootball.understanding.match_context import MatchChronology
    from aifootball.understanding.commentary import compile_commentary
    window,_,_=environment(tmp_path);raw=response();raw['events'][0]['visual_signals']=['players_approach_goal']
    projected,_=project_context(raw,window);history=MatchChronology(SOURCE,passport());history.add(window,projected,'r')
    feed=compile_commentary(history.document(),passport())
    assert feed['entries']==[] and feed['rejected_events'][0]['reason']=='insufficient_visual_signals'
    assert len(history.document()['events'])==1


def test_save_without_observed_kick_does_not_assert_shot_or_create_highlight(tmp_path):
    from aifootball.understanding.context_pilot import project_context
    from aifootball.understanding.match_context import MatchChronology
    from aifootball.understanding.commentary import compile_commentary
    window,_,_=environment(tmp_path);raw=response()
    raw['events'][0].update(kind='save_candidate',
        visual_signals=['ball_visible','ball_toward_goal','keeper_contact'],
        limitations=['Контакт бьющего с мячом не виден'])
    projected,_=project_context(raw,window);history=MatchChronology(SOURCE,passport());history.add(window,projected,'save')
    feed=compile_commentary(history.document(),passport())
    assert feed['entries']==[] and feed['highlight_candidates']==[]
    assert feed['rejected_events'][0]['reason']=='insufficient_visual_signals'
    assert history.document()['events'][0]['kind']=='save_candidate'
    raw['events'][0]['visual_signals'].append('kick_contact')
    projected,_=project_context(raw,window);supported=MatchChronology(SOURCE,passport());supported.add(window,projected,'observed-save')
    assert len(compile_commentary(supported.document(),passport())['entries'])==1


def test_observed_shot_becomes_stable_video_timed_entry_exactly_once(tmp_path):
    from aifootball.understanding.context_pilot import project_context
    from aifootball.understanding.match_context import MatchChronology
    from aifootball.understanding.commentary import compile_commentary
    window,_,_=environment(tmp_path);window=replace(window,start_ms=30000,end_ms=42000)
    projected,_=project_context(response(),window);history=MatchChronology(SOURCE,passport())
    history.add(window,projected,'r');history.add(window,projected,'r')
    feed=compile_commentary(history.document(),passport());entry=feed['entries'][0]
    assert len(feed['entries'])==1 and entry['video_ms']==31000 and entry['end_ms']==32000
    assert entry['status']=='unverified' and entry['timestamp_basis']=='video'
    assert entry['evidence_ids']==['clip'] and 'удар' in entry['text'].lower()
    assert compile_commentary(history.document(),passport())==feed


def test_goal_is_still_candidate_and_match_start_is_never_invented(tmp_path):
    from aifootball.understanding.context_pilot import project_context
    from aifootball.understanding.match_context import MatchChronology
    from aifootball.understanding.commentary import compile_commentary
    window,_,_=environment(tmp_path);raw=response();raw['events'][0].update(kind='goal_candidate',
        visual_signals=['ball_visible','goal_frame_visible','ball_enters_goal'])
    projected,_=project_context(raw,window);history=MatchChronology(SOURCE,passport());history.add(window,projected,'r')
    texts=' '.join(e['text'] for e in compile_commentary(history.document(),passport())['entries']).lower()
    assert 'возможный гол' in texts and 'начал' not in texts and 'счёт' not in texts


def test_restart_line_requires_adjacent_observed_stoppage_and_no_gap(tmp_path):
    from aifootball.understanding.context_pilot import project_context
    from aifootball.understanding.match_context import MatchChronology
    from aifootball.understanding.commentary import compile_commentary
    window,_,_=environment(tmp_path);raw=response();raw['events']=[]
    raw['states'][0].update(kind='stoppage',visual_signals=['ball_outside_pitch'])
    stop,_=project_context(raw,window);raw['states'][0].update(kind='playing',visual_signals=['ball_visible','active_ball_play'])
    play,_=project_context(raw,window)
    history=MatchChronology(SOURCE,passport());history.add(window,stop,'stop')
    history.add(replace(window,id='second',start_ms=12000,end_ms=24000),play,'play')
    assert any(e['text']=='Игра возобновилась.' for e in compile_commentary(history.document(),passport())['entries'])
    history.gap(11900,12100,'unavailable')
    assert not any(e['text']=='Игра возобновилась.' for e in compile_commentary(history.document(),passport())['entries'])


def test_schema_metadata_can_be_repaired_but_not_bad_time_or_wrong_evidence(tmp_path):
    from aifootball.understanding.context_pilot import project_context
    window,_,_=environment(tmp_path);raw=response();raw.pop('schema_version');raw.pop('time_basis')
    assert project_context(raw,window)[0]['schema_version']=='joint-context-v2'
    raw=response();raw['events'][0]['end_ms']=12001
    with pytest.raises(ValueError):project_context(raw,window)
    raw=response();raw['events'][0]['evidence_ids']=['fake']
    with pytest.raises(ValueError):project_context(raw,window)


def test_feed_does_not_trust_legacy_states_without_observed_signals(tmp_path):
    from aifootball.understanding.match_context import MatchChronology
    from aifootball.understanding.commentary import compile_commentary
    window,_,_=environment(tmp_path);raw=response();raw['events']=[]
    raw['states'][0]['kind']='stoppage';raw['states'][0]['visual_signals']=[]
    history=MatchChronology(SOURCE,passport());history.add(window,raw,'legacy')
    assert compile_commentary(history.document(),passport())['entries']==[]
