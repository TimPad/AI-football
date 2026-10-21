"""Bound the whole request before Starlette spools multipart files."""
import re
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

class AnalysisBodyLimit:
    def __init__(self, app, settings):
        self.app, self.settings = app, settings

    async def __call__(self, scope, receive, send):
        path=scope.get('path','')
        roster=path in {'/api/v1/roster-imports','/api/v1/captain/roster-imports','/api/v1/captain/images'} or bool(re.fullmatch(r'/api/v1/captain/teams/[^/]+/roster-imports',path))
        if scope['type'] != 'http' or scope.get('method') != 'POST' or not (roster or re.fullmatch(r'/api/v1/matches/[^/]+/analysis/imports', path)):
            return await self.app(scope, receive, send)
        # Small allowance for MIME headers/fields in addition to the ZIP bytes.
        limit = (5 * 1024 * 1024 if roster else self.settings.analysis_zip_limit) + 1024 * 1024
        headers = dict(scope.get('headers', []))
        try: declared = int(headers.get(b'content-length', b'0'))
        except ValueError: declared = limit + 1
        if declared > limit or declared < 0:
            return await JSONResponse({'error': {'code': 'size', 'message': 'Загрузка превышает допустимый размер запроса', 'fields': {}}}, status_code=413)(scope, receive, send)
        received = 0
        async def bounded_receive():
            nonlocal received
            message = await receive()
            if message['type'] == 'http.request':
                received += len(message.get('body', b''))
                if received > limit:
                    raise HTTPException(413, 'Превышен размер запроса загрузки')
            return message
        await self.app(scope, bounded_receive, send)
