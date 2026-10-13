from aifootball.service.tournaments.schemas import Regulation


def validate_regulation(rules):
    return Regulation.model_validate(rules.model_dump() if isinstance(rules,Regulation) else rules)


def resolve_rules(match,version):
    return validate_regulation(match.regulation_override or version.rules)
