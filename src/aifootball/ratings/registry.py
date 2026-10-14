"""Versioned operational definitions; physical workload has zero rating weight."""
from aifootball.ratings.schema import TIME_BASES

REGISTRY_VERSION='futsal-metrics-v1'
_DEFINITIONS={
    'npg_rate10':('Non-penalty, non-own goals','goals','eligible_play_s','good'),
    'assists_rate10':('Explicitly known official assists','assists','eligible_play_s','good'),
    'shots_on_target_pct':('On-target / resolved shots','shots','resolved_shots','good'),
    'key_pass_rate10':('Last controlled pass before shot in one unbroken possession','passes+shots','possession_s','good'),
    'recoveries_rate10':('Established control after loose ball or opponent possession','recoveries','without_possession_s','good'),
    'duel_win_pct':('Won / resolved direct contests for control','duels','resolved_duels','good'),
    'blocks_rate10':('Confirmed obstruction of a linked shot','shot_blocks','without_possession_s','good'),
    'dangerous_turnover_rate10':('Opponent control after loss in own quarter','turnovers','possession_s','bad'),
    'pass_completion_pct':('Controlled receipt / resolved passes','passes','resolved_passes','good'),
    'discipline_cost_rate10':('Maximum foul/card/error cost per linked incident','fouls+cards+errors','eligible_play_s','bad'),
    'save_pct':('Verified GK saves / saves plus goals faced during GK stint (difficulty unadjusted)','saves+goals','shots_faced','good'),
    'distribution_pct':('Controlled receipt / resolved GK distributions','distribution','resolved_distributions','good'),
    'progression_rate10':('Retained ball crosses next attacking quarter of actual hall','passes+carries+distribution','possession_s','good'),
}
REGISTRY={key:{'version':REGISTRY_VERSION,'definition':definition,'sources':sources.split('+'),
    'numerator':key.removesuffix('_rate10').removesuffix('_pct'),'denominator':denominator,
    'unit':'count/10min' if key.endswith('_rate10') else 'percent','direction':direction,
    'time_bases':sorted(TIME_BASES),'profiles':['per10','per10-possession']} for key,(definition,sources,denominator,direction) in _DEFINITIONS.items()}
