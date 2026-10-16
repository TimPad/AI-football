import json
from hashlib import sha256
from sqlalchemy import select
from aifootball.service.common import get_entity
from aifootball.service.matches.models import Match, LineupMember
from aifootball.service.catalog.models import Entry, Team
from aifootball.service.halls.models import CameraProfile
from aifootball.service.halls.operations import same_dimensions
from aifootball.service.errors import DomainError


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def context_hash(context):
    return sha256(canonical_json(context)).hexdigest()


def build_context(db, match_id):
    match = get_entity(db, Match, match_id, lock=True)
    if not match.camera_profile_id or not match.hall_snapshot:
        raise DomainError('camera_required', 'Выберите калиброванную камеру в информации о матче')
    camera = get_entity(db, CameraProfile, match.camera_profile_id)
    if camera.hall_id != match.hall_id or not same_dimensions(camera, match.hall_snapshot):
        raise DomainError('camera_geometry', 'Камера не соответствует геометрии матча')
    rosters = [{'player_id': str(p.player_id), 'side': p.side, 'display_name': p.display_name,
                'shirt_number': p.shirt_number} for p in db.scalars(
                    select(LineupMember).where(LineupMember.match_id == match_id).order_by(LineupMember.side, LineupMember.player_id))]
    if not all(any(p['side'] == side for p in rosters) for side in ['home', 'away']):
        raise DomainError('lineup_required', 'Добавьте игроков обеих команд в состав матча')
    teams = {}
    for side, eid in [('home', match.home_entry_id), ('away', match.away_entry_id)]:
        entry = get_entity(db, Entry, eid)
        team = get_entity(db, Team, entry.team_id)
        teams[side] = {'id': str(team.id), 'name': team.name}
    return {'match_id': str(match.id), 'hall_id': str(match.hall_id), 'teams': teams, 'rosters': rosters,
            'pitch': {'length_m': camera.pitch_length_m, 'width_m': camera.pitch_width_m},
            'camera': {'id': str(camera.id), 'version': camera.version, 'frame_width': camera.frame_width,
                       'frame_height': camera.frame_height, 'homography': camera.homography,
                       'polygon_px': camera.pitch_polygon_px, 'calibration': camera.calibration,
                       # Только если кадр задан: контекст профилей без кадра и их задания не меняются.
                       **({'reference_sha256': camera.reference_sha256} if camera.reference_sha256 else {})},
            'units': {'distance': 'm', 'speed': 'm/s', 'time': 's', 'heatmap': 's'}}
