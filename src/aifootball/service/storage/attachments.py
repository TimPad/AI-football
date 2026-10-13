from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile
from aifootball.service.errors import DomainError

MAX_DOCUMENT_BYTES=20*1024*1024  # Достаточно для скана протокола, не для видеозаписи.


@dataclass
class AttachmentInfo:
    key:str
    size:int
    sha256:str
    mime:str
    created:bool


class AttachmentStore:
    def __init__(self,root): self.root=Path(root)

    def put(self,identifier,stream,mime):
        self.root.mkdir(parents=True,exist_ok=True)
        key=str(identifier); target=self.root/key; total=0; digest=sha256(); prefix=b''
        with NamedTemporaryFile(dir=self.root,delete=False) as file:
            temporary=Path(file.name)
            try:
                while chunk:=stream.read(1024*1024):
                    total+=len(chunk)
                    if total>MAX_DOCUMENT_BYTES: raise DomainError('file_size','Размер документа превышает 20 МБ')
                    if not prefix: prefix=chunk[:16]
                    digest.update(chunk); file.write(chunk)
                detected='application/pdf' if prefix.startswith(b'%PDF-') else (
                    'image/png' if prefix.startswith(b'\x89PNG\r\n\x1a\n') else (
                    'image/jpeg' if prefix.startswith(b'\xff\xd8\xff') else None))
                if detected is None or mime!=detected:
                    raise DomainError('file_type','Допустимы документы PDF, PNG и JPEG с соответствующим типом')
                file.flush()
                value=digest.hexdigest()
                if target.exists():
                    with target.open('rb') as existing:
                        old=sha256()
                        while part:=existing.read(1024*1024): old.update(part)
                    if target.stat().st_size!=total or old.hexdigest()!=value:
                        raise DomainError('idempotency_conflict','Этот ключ загрузки уже использован для другого файла',status=409)
                    return AttachmentInfo(key,total,value,detected,False)
                # hard link не перезаписывает существующий файл при параллельном повторе.
                import os
                try: os.link(temporary,target)
                except FileExistsError:
                    with temporary.open('rb') as repeated:
                        return self.put(identifier,repeated,mime)
                target.chmod(0o600)
                return AttachmentInfo(key,total,value,detected,True)
            finally:
                temporary.unlink(missing_ok=True)

    def open(self,key):
        from uuid import UUID
        return (self.root/str(UUID(key))).open('rb')
