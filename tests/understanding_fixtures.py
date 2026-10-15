from hashlib import sha256
from io import BytesIO
from PIL import Image


def understanding_document(manifest, tracks, *, duration_ms, evidence=None):
    return {
        'schema_version': '1',
        'source': {'sha256': manifest['source_video']['sha256'], 'duration_ms': duration_ms,
                   'width': manifest['source_video']['width'], 'height': manifest['source_video']['height'],
                   'analysis_scope': 'unknown'},
        'context': {k: manifest[k] for k in ['job_id','match_id','context_hash','camera_profile_id']},
        'provider': {'name':'qwen','model':'qwen3.8-omni-flash','response_model':None,
                     'endpoint':'https://example.invalid/compatible-mode/v1','region':None,
                     'prompt_version':'futsal-v1','settings':{'mode':'frames'}},
        'budget': {'max_requests':200,'max_input_tokens':300000,'max_output_tokens':100000,
                   'requests':0,'input_tokens':0,'output_tokens':0,'usage_unknown':False},
        'coverage': {'covered_intervals':[],'unknown_intervals':[[0,duration_ms]],'status':'unavailable'},
        'evidence': evidence or [], 'observations': [], 'identity_suggestions': [],
        'states': [], 'phases': [], 'events': [], 'summary': [],
    }


def make_frame(tmp_path, *, frame_id=25, video_ms=1000):
    from aifootball.understanding.types import FrameAsset
    raw=BytesIO(); Image.new('RGB',(64,48),(30,60,90)).save(raw,format='JPEG')
    path=tmp_path / f'f{frame_id}.jpg'; path.write_bytes(raw.getvalue())
    return FrameAsset(f'f{frame_id}',frame_id,video_ms,path,sha256(raw.getvalue()).hexdigest(),None)


def event(**changes):
    return {'id':'e1','kind':'goal_candidate','start_ms':1000,'end_ms':2000,
            'team':None,'track_ids':[],'evidence_ids':[], 'audio_observations':[],
            'limitations':['Мяч не виден'],**changes}
