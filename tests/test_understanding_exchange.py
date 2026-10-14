from hashlib import sha256
from io import BytesIO
from zipfile import ZipFile,ZipInfo
import json
import stat
import pytest
from PIL import Image
from test_analysis_exchange import result_zip
from understanding_fixtures import understanding_document,event
from aifootball.analytics.exchange import canonical,validate_result,ExchangeError,Limits


def result_v2(job=None,*,mutate=None):
    with ZipFile(BytesIO(result_zip(job))) as source:files={name:source.read(name) for name in source.namelist()}
    manifest=json.loads(files.pop('manifest.json'));manifest['contract_version']='2'
    tracks=json.loads(files['track-index.json'])
    raw=BytesIO();Image.new('RGB',(32,24),(30,60,90)).save(raw,format='JPEG');image=raw.getvalue()
    evidence={'id':'f1','frame_id':1,'video_ms':1000,'path':'evidence/f1.jpg','sha256':sha256(image).hexdigest(),'crop':None,'kind':'overview'}
    doc=understanding_document(manifest,tracks,duration_ms=round(manifest['source_video']['duration_s']*1000),evidence=[evidence])
    doc['events']=[event(track_ids=[1],evidence_ids=['f1'],limitations=['Синтетический пример'])]
    doc['coverage']={'covered_intervals':[[0,2000]],'unknown_intervals':[[2000,doc['source']['duration_ms']]],'status':'partial'}
    if mutate:mutate(manifest,doc)
    files['understanding.json']=canonical(doc);files['evidence/f1.jpg']=image
    return archive(manifest,files)


def archive(manifest,files):
    manifest['files']={name:{'size':len(raw),'sha256':sha256(raw).hexdigest()} for name,raw in files.items()}
    out=BytesIO()
    with ZipFile(out,'w') as target:
        target.writestr('manifest.json',canonical(manifest))
        for name,raw in files.items():target.writestr(name,raw)
    return out.getvalue()


def rewrite(raw,mutate):
    with ZipFile(BytesIO(raw)) as source:files={name:source.read(name) for name in source.namelist()}
    manifest=json.loads(files.pop('manifest.json'));mutate(manifest,files);return archive(manifest,files)


def test_legacy_result_has_no_understanding():
    assert validate_result(result_zip()).understanding is None


def test_v2_preserves_measured_report_and_exposes_bounded_observations():
    result=validate_result(result_v2())
    assert result.understanding['events'][0]['kind']=='goal_candidate'
    assert result.report['schema_version']=='1'
    assert result.report['periods'][0]['players'][0]['distance_m']==120
    assert result.files['evidence/f1.jpg'].startswith(b'\xff\xd8')


@pytest.mark.parametrize('mutate',[
    lambda m,d:m.update(contract_version='1'),
    lambda m,d:m.update(contract_version='9'),
    lambda m,d:d['source'].update(sha256='f'*64),
    lambda m,d:d['context'].update(context_hash='f'*64),
    lambda m,d:d['events'][0].update(evidence_ids=['missing']),
    lambda m,d:d['events'][0].update(track_ids=[999]),
])
def test_incompatible_or_foreign_understanding_is_rejected(mutate):
    with pytest.raises(ExchangeError):validate_result(result_v2(mutate=mutate))


@pytest.mark.parametrize('mutate',[
    lambda m,f:f.pop('understanding.json'),
    lambda m,f:f.update({'evidence/unused.jpg':f['evidence/f1.jpg']}),
    lambda m,f:f.update({'evidence/f1.jpg':b'not a jpeg'}),
    lambda m,f:f.update({'evidence/../../escape.jpg':b'x'}),
])
def test_v2_file_registry_and_images_are_strict(mutate):
    with pytest.raises(ExchangeError):validate_result(rewrite(result_v2(),mutate))


def test_new_evidence_limits_are_independent_of_legacy_thumbs():
    raw=result_v2()
    with pytest.raises(ExchangeError):validate_result(raw,Limits(evidence=10))
    with pytest.raises(ExchangeError):validate_result(raw,Limits(understanding_json=100))


def test_summary_cannot_reference_an_absent_measured_metric():
    def mutate(manifest,doc):
        doc['summary']=[{'text':'Измерение','event_ids':[],'metric_refs':[{'period_key':'absent','track_id':1,'metric_name':'distance_m'}]}]
    with pytest.raises(ExchangeError):validate_result(result_v2(mutate=mutate))


def test_v2_evidence_symlink_is_rejected():
    raw=result_v2();out=BytesIO()
    with ZipFile(BytesIO(raw)) as source,ZipFile(out,'w') as target:
        for name in source.namelist():
            info=ZipInfo(name)
            if name.startswith('evidence/'):info.external_attr=(stat.S_IFLNK|0o777)<<16
            target.writestr(info,source.read(name))
    with pytest.raises(ExchangeError):validate_result(out.getvalue())
