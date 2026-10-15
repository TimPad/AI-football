"""Atomic, checksummed local state with a process/thread exclusive lock."""
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
import fcntl
import os
import tempfile
import threading
from aifootball.analytics.exchange import canonical,load_json


class Workspace:
    MAX_CACHE=16*1024*1024

    def __init__(self,root:Path,fingerprint:dict):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.fingerprint_hash=sha256(canonical(fingerprint)).hexdigest()
        self._owner=None;self._depth=0
        with self.exclusive():
            (self.root/'cache').mkdir(exist_ok=True)

    @contextmanager
    def exclusive(self):
        owner=threading.get_ident()
        if self._owner==owner:
            self._depth+=1
            try:yield self
            finally:self._depth-=1
            return
        with (self.root/'.lock').open('a+b') as lock:
            try:fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise ValueError('workspace locked by another process/thread') from None
            self._owner=owner;self._depth=1
            try:
                meta=self.root/'workspace.json'
                expected={'version':'1','fingerprint_sha256':self.fingerprint_hash}
                if meta.exists():
                    try:actual=load_json(meta.read_bytes(),'workspace')
                    except (OSError,ValueError):raise ValueError('corrupt workspace metadata') from None
                    if actual!=expected:raise ValueError('workspace fingerprint mismatch')
                else:self._atomic(meta,canonical(expected))
                yield self
            finally:
                self._owner=None;self._depth=0;fcntl.flock(lock.fileno(),fcntl.LOCK_UN)

    @staticmethod
    def _atomic(path,raw):
        temporary=None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent,prefix='.',suffix='.tmp',delete=False) as stream:
                temporary=Path(stream.name);stream.write(raw);stream.flush();os.fsync(stream.fileno())
            os.replace(temporary,path)
            fd=os.open(path.parent,os.O_RDONLY)
            try:os.fsync(fd)
            finally:os.close(fd)
        finally:
            if temporary is not None:temporary.unlink(missing_ok=True)

    def _cache_path(self,key):
        if type(key) is not str or not key or len(key)>10000:raise ValueError('invalid cache key')
        return self.root/'cache'/(sha256(key.encode()).hexdigest()+'.json')

    def get_json(self,key):
        with self.exclusive():
            path=self._cache_path(key)
            if not path.exists():return None
            try:
                if path.stat().st_size>self.MAX_CACHE:raise ValueError('size')
                envelope=load_json(path.read_bytes(),'cache')
                if set(envelope)!={'sha256','value'} or type(envelope['value']) is not dict:raise ValueError('fields')
                if sha256(canonical(envelope['value'])).hexdigest()!=envelope['sha256']:raise ValueError('hash')
                return envelope['value']
            except (OSError,ValueError,KeyError,TypeError):raise ValueError('corrupt workspace cache') from None

    def put_json(self,key,value):
        if type(value) is not dict:raise ValueError('cache value must be an object')
        raw=canonical(value)
        envelope=canonical({'sha256':sha256(raw).hexdigest(),'value':value})
        if len(envelope)>self.MAX_CACHE:raise ValueError('cache size limit')
        with self.exclusive():self._atomic(self._cache_path(key),envelope)
