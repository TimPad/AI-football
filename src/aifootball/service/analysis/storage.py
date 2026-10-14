from io import BytesIO
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED
import os
from aifootball.analytics.exchange import Limits, ExchangeError
from aifootball.service.errors import DomainError


def limits(settings):
    return Limits(settings.analysis_zip_limit, settings.analysis_unpacked_limit, settings.analysis_file_limit,
                  settings.analysis_json_limit, settings.analysis_thumb_limit)


def read_upload(stream, settings):
    raw = stream.read(settings.analysis_zip_limit + 1)
    if len(raw) > settings.analysis_zip_limit:
        raise DomainError('size', 'Пакет результата превышает допустимый размер ZIP', status=413)
    return raw


def put_package(root, result):
    root = Path(root) / 'analysis'; root.mkdir(parents=True, exist_ok=True, mode=0o700)
    key = f"{result.manifest['run_id']}-{result.content_hash[:16]}.zip"
    path = root / key
    # Store validated files only; timestamps/order do not depend on the submitted container.
    buffer = BytesIO()
    with ZipFile(buffer, 'w') as archive:
        for name, raw in sorted(result.files.items()):
            info = ZipInfo(name, (2026, 1, 1, 0, 0, 0)); info.compress_type = ZIP_DEFLATED
            archive.writestr(info, raw)
    raw = buffer.getvalue()
    if path.exists():
        if path.read_bytes() != raw:
            raise DomainError('storage_conflict', 'Сохранённый пакет повреждён', status=409)
        return key, None
    with path.open('xb') as target:
        os.chmod(path, 0o600); target.write(raw)
    return key, path


def read_file(root, key, filename):
    # Names come from the validated index, not an arbitrary request path.
    try:
        with ZipFile(Path(root) / 'analysis' / key) as archive:
            return archive.read(filename)
    except (OSError, KeyError):
        raise DomainError('not_found', 'Файл результата недоступен', status=404) from None
