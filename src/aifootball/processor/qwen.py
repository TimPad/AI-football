"""One bounded Omni API attempt; durable retry/budget policy belongs to the caller."""
import base64
from dataclasses import dataclass,field
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import time
from urllib.parse import urlsplit

from aifootball.analytics.exchange import load_json
from aifootball.understanding.types import InferenceResult,Window


class QwenError(ValueError):
    def __init__(self,code,retryable=False,retry_after=None,usage_unknown=False):
        self.code=code;self.retryable=retryable;self.retry_after=retry_after;self.usage_unknown=usage_unknown
        super().__init__(f'Qwen: {code}')


@dataclass(frozen=True)
class QwenConfig:
    key: str=field(repr=False)
    base_url: str
    model: str='qwen3.8-omni-flash'
    timeout: float=180

    def __post_init__(self):
        url=urlsplit(self.base_url)
        if (not self.key or url.scheme!='https' or not url.hostname or url.username is not None or
            url.password is not None or url.query or url.fragment or not self.model or
            type(self.timeout) not in (int,float) or not math.isfinite(self.timeout) or not 0<self.timeout<=180):
            raise ValueError('Invalid Qwen configuration')
        object.__setattr__(self,'base_url',self.base_url.rstrip('/'))

    @classmethod
    def from_env(cls):
        # Load the same local .env convention as the service. Environment takes precedence.
        from dotenv import dotenv_values
        values={**dotenv_values('.env'),**os.environ}
        key=values.get('DASHSCOPE_API_KEY');url=values.get('DASHSCOPE_BASE_URL')
        if not key or not url:raise ValueError('Set DASHSCOPE_API_KEY and DASHSCOPE_BASE_URL locally')
        return cls(key,url)


class QwenClient:
    def __init__(self,config,*,transport=None):
        self.config=config;self.transport=transport

    @staticmethod
    def _media(path,expected_hash,*,maximum):
        path=Path(path)
        if not path.is_file() or path.stat().st_size>maximum:raise QwenError('media_limit')
        with path.open('rb') as stream:raw=stream.read(maximum+1)
        if len(raw)>maximum:raise QwenError('media_limit')
        if sha256(raw).hexdigest()!=expected_hash:raise QwenError('media_hash')
        return base64.b64encode(raw).decode('ascii')

    def _body(self,window,prompt,max_output_tokens):
        if (not isinstance(prompt,str) or len(prompt)>10000 or 'json' not in prompt.lower() or
            type(max_output_tokens) is not int or not 1<=max_output_tokens<=131072 or
            not 0<=window.start_ms<window.end_ms or len(window.frames)>32 or
            window.mode not in ('native','frames')):raise QwenError('request_config')
        content=[{'type':'text','text':prompt}]
        for frame in window.frames:
            if not window.start_ms<=frame.video_ms<window.end_ms:raise QwenError('frame_bounds')
            data=self._media(frame.path,frame.sha256,maximum=6*1024*1024)
            content.append({'type':'text','text':json.dumps({'evidence_id':frame.id,'frame_id':frame.frame_id,
                'video_ms':frame.video_ms,'window_ms':frame.video_ms-window.start_ms,'crop':frame.crop})})
            content.append({'type':'image_url','image_url':{'url':'data:image/jpeg;base64,'+data}})
        if window.media is not None:
            media=window.media
            if (window.mode!='native' or media.kind not in ('video','audio') or media.start_ms!=window.start_ms or
                media.end_ms!=window.end_ms or media.end_ms-media.start_ms>20000):raise QwenError('clip_bounds')
            data=self._media(media.path,media.sha256,maximum=6*1024*1024-1)
            if len(data)>=8*1024*1024:raise QwenError('media_limit')
            if media.kind=='video':content.append({'type':'video_url','video_url':{'url':'data:;base64,'+data}})
            else:content.append({'type':'input_audio','input_audio':{'data':data,'format':'wav'}})
        if len(content)==1:raise QwenError('empty_media')
        body={'model':self.config.model,'messages':[{'role':'user','content':content}],
              'modalities':['text'],'stream':True,'stream_options':{'include_usage':True},
              'reasoning_effort':'none','response_format':{'type':'json_object'},'max_tokens':max_output_tokens}
        raw=json.dumps(body,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
        if len(raw)>12*1024*1024:raise QwenError('request_size')
        return raw

    def infer(self,window:Window,prompt:str,*,max_output_tokens:int)->InferenceResult:
        import anyio
        raw=self._body(window,prompt,max_output_tokens)
        # Async timeout bounds the entire operation, including a slow/never-ending stream.
        return anyio.run(self._infer,raw)

    async def _infer(self,raw):
        import httpx
        import anyio
        timeout=httpx.Timeout(60,connect=15,write=30,pool=10)
        try:
            with anyio.fail_after(self.config.timeout):
                async with httpx.AsyncClient(transport=self.transport,timeout=timeout,follow_redirects=False,trust_env=False) as client:
                    async with client.stream('POST',self.config.base_url+'/chat/completions',content=raw,
                        headers={'Authorization':'Bearer '+self.config.key,'Content-Type':'application/json','Accept':'text/event-stream'}) as response:
                        if response.status_code!=200:
                            status=response.status_code;retry_after=None
                            try:retry_after=min(60,max(0,float(response.headers.get('retry-after',''))))
                            except (ValueError,OverflowError):pass
                            if retry_after is not None and not math.isfinite(retry_after):retry_after=None
                            raise QwenError(f'http_{status}',retryable=status==429 or status>=500,retry_after=retry_after,
                                            usage_unknown=status>=500)
                        return await self._parse(response)
        except QwenError:raise
        except (httpx.HTTPError,TimeoutError):raise QwenError('transport',retryable=True,usage_unknown=True) from None

    async def _parse(self,response):
        buffer=b'';data_lines=[];pieces=[];size=0;chunks=0;finished=False;done=False;usage=None;request_id=None;model=self.config.model
        def consume(data):
            nonlocal chunks,finished,done,usage,request_id,model
            chunks+=1
            if chunks>50000:raise QwenError('stream_limit',usage_unknown=True)
            if data==b'[DONE]':done=True;return
            if done:raise QwenError('after_done',usage_unknown=True)
            try:item=load_json(data,'Qwen SSE')
            except ValueError:raise QwenError('stream_json',usage_unknown=True) from None
            if 'error' in item:raise QwenError('provider_stream_error',usage_unknown=True)
            if item.get('id') is not None:
                if not isinstance(item['id'],str) or len(item['id'])>200:raise QwenError('request_id',usage_unknown=True)
                request_id=item['id']
            if item.get('model') is not None:
                if not isinstance(item['model'],str) or len(item['model'])>200:raise QwenError('response_model',usage_unknown=True)
                model=item['model']
            if item.get('usage') is not None:
                value=item['usage']
                if not isinstance(value,dict) or any(type(value.get(k)) is not int or value[k]<0 for k in ('prompt_tokens','completion_tokens')):
                    raise QwenError('usage',usage_unknown=True)
                usage=value
            choices=item.get('choices',[])
            if not isinstance(choices,list) or len(choices)>1:raise QwenError('choices',usage_unknown=True)
            for choice in choices:
                if not isinstance(choice,dict) or not isinstance(choice.get('delta',{}),dict):raise QwenError('delta',usage_unknown=True)
                delta=choice.get('delta',{});text=delta.get('content')
                if text is not None:
                    if not isinstance(text,str) or (finished and text):raise QwenError('content',usage_unknown=True)
                    pieces.append(text)
                reason=choice.get('finish_reason')
                if reason is not None:
                    if reason!='stop' or finished:raise QwenError('incomplete_completion',usage_unknown=True)
                    finished=True
        async for part in response.aiter_bytes(chunk_size=16384):
            size+=len(part)
            if size>2*1024*1024:raise QwenError('stream_limit',usage_unknown=True)
            buffer+=part
            while b'\n' in buffer:
                line,buffer=buffer.split(b'\n',1);line=line.rstrip(b'\r')
                if line.startswith(b'data:'):data_lines.append(line[5:].lstrip(b' '))
                elif not line and data_lines:consume(b'\n'.join(data_lines));data_lines=[]
        if buffer.strip() or data_lines or not done or not finished:raise QwenError('incomplete_stream',usage_unknown=True)
        try:document=load_json(''.join(pieces).encode(),'Qwen content')
        except ValueError:raise QwenError('response_json',usage_unknown=True) from None
        return InferenceResult(document,usage,request_id,model)
