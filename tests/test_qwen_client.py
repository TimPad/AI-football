import json
from hashlib import sha256
from pathlib import Path
import httpx
import pytest
from understanding_fixtures import make_frame


def sse(chunks,*,done=True):
    raw=''.join('data: '+json.dumps({'id':'request-1','model':'qwen3.8-omni-flash',**chunk},ensure_ascii=False)+'\n\n' for chunk in chunks)
    return (raw+('data: [DONE]\n\n' if done else '')).encode()


def completed(text='{"events":[]}'):
    return [{'choices':[{'delta':{'reasoning_content':'ignore'}}]},
            {'choices':[{'delta':{'content':text},'finish_reason':'stop'}]},
            {'choices':[],'usage':{'prompt_tokens':10,'completion_tokens':5,'total_tokens':15}}]


@pytest.fixture
def frame_window(tmp_path):
    from aifootball.understanding.types import Window
    return Window('w1',0,2000,(make_frame(tmp_path),),None,(1,),'frames')


def client(handler):
    from aifootball.processor.qwen import QwenClient,QwenConfig
    return QwenClient(QwenConfig('test-key','https://example.invalid/v1'),transport=httpx.MockTransport(handler))


def test_endpoint_and_payload_match_omni_contract(frame_window):
    def respond(request):
        assert str(request.url)=='https://example.invalid/v1/chat/completions'
        assert request.headers['Authorization']=='Bearer test-key'
        body=json.loads(request.content)
        assert body['model']=='qwen3.8-omni-flash'
        assert body['modalities']==['text'] and body['stream'] is True
        assert body['stream_options']=={'include_usage':True}
        assert body['reasoning_effort']=='none'
        assert body['response_format']=={'type':'json_object'}
        image=body['messages'][0]['content'][-1]
        assert image['image_url']['url'].startswith('data:image/jpeg;base64,')
        return httpx.Response(200,content=sse(completed('{"events":[],"text":"Мяч"}')))
    result=client(respond).infer(frame_window,'Return JSON',max_output_tokens=512)
    assert result.document=={'events':[],'text':'Мяч'}
    assert result.usage['prompt_tokens']==10
    assert result.request_id=='request-1'


@pytest.mark.parametrize('kind,block',[('video','video_url'),('audio','input_audio')])
def test_native_media_uses_local_bytes_not_public_url(tmp_path,kind,block):
    from aifootball.understanding.types import Window,MediaAsset
    path=tmp_path/('clip.mp4' if kind=='video' else 'clip.wav');path.write_bytes(b'media')
    media=MediaAsset('clip',kind,path,sha256(b'media').hexdigest(),1000,2000,True)
    window=Window('w1',1000,2000,(),media,(),'native')
    def respond(request):
        content=json.loads(request.content)['messages'][0]['content']
        assert content[-1]['type']==block
        if kind=='video':assert content[-1]['video_url']['url'].startswith('data:;base64,')
        else:
            assert content[-1]['input_audio']['format']=='wav'
            assert content[-1]['input_audio']['data']=='bWVkaWE='
        return httpx.Response(200,content=sse(completed()))
    assert client(respond).infer(window,'JSON',max_output_tokens=512).document=={'events':[]}


@pytest.mark.parametrize('chunks,done',[
    (completed(),False),
    ([{'choices':[{'delta':{'content':'{}'},'finish_reason':'length'}]}],True),
    ([{'choices':[{'delta':{'content':'{}'}}]}],True),
    ([{'choices':[{'delta':{'content':''},'finish_reason':'stop'}]}],True),
    (completed('{bad}'),True),
    (completed('{"events":[],"events":[]}'),True),
])
def test_incomplete_or_malformed_stream_is_not_success(frame_window,chunks,done):
    from aifootball.processor.qwen import QwenError
    with pytest.raises(QwenError) as raised:
        client(lambda req:httpx.Response(200,content=sse(chunks,done=done))).infer(frame_window,'JSON',max_output_tokens=512)
    assert raised.value.usage_unknown is True
    assert 'test-key' not in str(raised.value)


@pytest.mark.parametrize('status,retryable',[(401,False),(402,False),(429,True),(500,True),(503,True)])
def test_http_failures_do_not_leak_provider_body(frame_window,status,retryable):
    from aifootball.processor.qwen import QwenError
    with pytest.raises(QwenError) as raised:
        client(lambda req:httpx.Response(status,text='test-key private-data',headers={'Retry-After':'2'})).infer(frame_window,'JSON',max_output_tokens=512)
    assert raised.value.retryable is retryable
    assert raised.value.code==f'http_{status}'
    assert 'private-data' not in str(raised.value) and 'test-key' not in repr(raised.value)
    if status==429:assert raised.value.retry_after==2


@pytest.mark.parametrize('url',['http://example.invalid/v1','https://user:secret@example.invalid/v1',
    'https://example.invalid/v1?token=secret','https://example.invalid/v1#key','https:///v1'])
def test_unsafe_endpoint_rejected(url):
    from aifootball.processor.qwen import QwenConfig
    with pytest.raises(ValueError):QwenConfig('test-key',url)


def test_key_redacted_from_config_repr(monkeypatch):
    from aifootball.processor.qwen import QwenConfig
    monkeypatch.setenv('DASHSCOPE_API_KEY','test-key')
    monkeypatch.setenv('DASHSCOPE_BASE_URL','https://example.invalid/v1')
    config=QwenConfig.from_env()
    assert config.base_url=='https://example.invalid/v1'
    assert 'test-key' not in repr(config)


def test_media_limits_enforced_before_network(frame_window):
    from dataclasses import replace
    from aifootball.processor.qwen import QwenError
    def forbidden(request):raise AssertionError('network called for invalid local media')
    with pytest.raises(QwenError):client(forbidden).infer(replace(frame_window,frames=frame_window.frames*33),'JSON',max_output_tokens=512)
    frame_window.frames[0].path.write_bytes(b'x'*13*1024*1024)
    with pytest.raises(QwenError):client(forbidden).infer(frame_window,'JSON',max_output_tokens=512)


def test_read_timeout_is_redacted(frame_window):
    from aifootball.processor.qwen import QwenError
    def timeout(request):raise httpx.ReadTimeout('test-key',request=request)
    with pytest.raises(QwenError,match='transport') as raised:client(timeout).infer(frame_window,'JSON',max_output_tokens=512)
    assert raised.value.retryable and raised.value.usage_unknown


def test_bounded_scene_metadata_can_exceed_short_text_limit(frame_window):
    result=client(lambda req:httpx.Response(200,content=sse(completed()))).infer(
        frame_window,'Return JSON '+('x'*12000),max_output_tokens=512)
    assert result.document=={'events':[]}


def test_frame_labels_give_only_window_time_to_avoid_absolute_answers(frame_window):
    labels=[]
    def respond(request):
        body=json.loads(request.content)
        labels.extend(json.loads(part['text']) for part in body['messages'][0]['content'][1:] if part['type']=='text')
        return httpx.Response(200,content=sse(completed('{"events":[]}')))
    client(respond).infer(frame_window,'Return JSON',max_output_tokens=512)
    assert labels and all('video_ms' not in label and 'window_ms' in label for label in labels)
