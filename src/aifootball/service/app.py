from pathlib import Path
from fastapi.responses import FileResponse,HTMLResponse
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from aifootball.service.config import Settings
from aifootball.service.db import make_engine
from aifootball.service.errors import DomainError, error_body
from aifootball.service.auth.routes import router as auth_router


def create_app(settings=None, *, web_dist=None):
    settings = settings or Settings()
    app = FastAPI(title='Кабинет турниров', version='0.1.0')
    from aifootball.service.analysis.body_limit import AnalysisBodyLimit
    app.add_middleware(AnalysisBodyLimit, settings=settings)
    app.state.settings = settings
    app.state.engine = make_engine(settings.database_url)
    expected_schema = ScriptDirectory(str(Path(__file__).resolve().parents[3] / 'migrations')).get_current_head()
    app.include_router(auth_router, prefix='/api/v1')
    from aifootball.service.captains.auth import router as captain_auth_router
    from aifootball.service.captains.routes import router as captain_router
    app.include_router(captain_auth_router,prefix='/api/v1')
    app.include_router(captain_router,prefix='/api/v1')
    from aifootball.service.captains.team_routes import router as captain_team_router
    from aifootball.service.captains.import_routes import router as captain_import_router
    app.include_router(captain_team_router,prefix='/api/v1')
    app.include_router(captain_import_router,prefix='/api/v1')
    from aifootball.service.captains.entry_routes import router as captain_entry_router
    app.include_router(captain_entry_router,prefix='/api/v1')
    from aifootball.service.tournaments.routes import router as tournament_router
    app.include_router(tournament_router, prefix='/api/v1')
    from aifootball.service.catalog.routes import router as catalog_router
    from aifootball.service.matches.routes import router as match_router
    app.include_router(catalog_router, prefix='/api/v1')
    from aifootball.service.catalog.roster_imports.routes import router as roster_import_router
    app.include_router(roster_import_router, prefix='/api/v1')
    from aifootball.service.catalog.images import router as catalog_images_router
    app.include_router(catalog_images_router, prefix='/api/v1')
    from aifootball.service.halls.address_routes import router as address_router
    app.include_router(address_router,prefix='/api/v1')
    from aifootball.service.halls.routes import router as halls_router
    app.include_router(halls_router, prefix='/api/v1')
    from aifootball.service.halls.frames import router as camera_frames_router
    app.include_router(camera_frames_router, prefix='/api/v1')
    from aifootball.service.analysis.routes import router as analysis_router
    from aifootball.service.analysis.team_review.routes import router as team_review_router
    app.include_router(team_review_router,prefix='/api/v1')
    app.include_router(analysis_router, prefix='/api/v1')
    from aifootball.service.ratings.routes import router as ratings_router
    app.include_router(ratings_router, prefix='/api/v1')
    app.include_router(match_router, prefix='/api/v1')
    from aifootball.service.protocol.routes import router as protocol_router
    from aifootball.service.storage.routes import router as storage_router
    app.include_router(protocol_router, prefix='/api/v1')
    app.include_router(storage_router, prefix='/api/v1')
    from aifootball.service.public import router as public_router
    app.include_router(public_router, prefix='/api/v1')
    from aifootball.service.public_profiles import router as public_profiles_router
    app.include_router(public_profiles_router,prefix='/api/v1')
    from aifootball.service.stages.routes import router as stage_router
    from aifootball.service.stages.public_routes import router as public_stage_router
    app.include_router(stage_router,prefix='/api/v1')
    app.include_router(public_stage_router,prefix='/api/v1')

    @app.exception_handler(DomainError)
    async def domain_error(request, error):
        return JSONResponse(error_body(error), status_code=error.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        fields = {'.'.join(str(x) for x in e['loc'][1:]): e['msg'] for e in error.errors()}
        return JSONResponse(error_body(DomainError('validation', 'Проверьте поля формы', fields)), status_code=422)

    @app.exception_handler(IntegrityError)
    async def integrity_error(request, error):
        return JSONResponse(error_body(DomainError('conflict', 'Запись уже существует или используется', status=409)), status_code=409)

    @app.get('/api/v1/health')
    def health():
        return {'status': 'ok'}

    @app.get('/api/v1/ready')
    def ready():
        try:
            with app.state.engine.connect() as db:
                db.execute(text('SELECT 1'))
                version = db.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
            if version != expected_schema:
                return JSONResponse({'status': 'not_ready', 'reason': 'migration_required'}, status_code=503)
            return {'status': 'ready', 'schema_version': version}
        except SQLAlchemyError:
            return JSONResponse({'status': 'not_ready'}, status_code=503)

    dist = Path(web_dist) if web_dist is not None else Path(__file__).resolve().parents[3] / 'web' / 'dist'

    @app.get('/{path:path}', include_in_schema=False)
    def frontend(path: str):
        target = (dist / path).resolve()
        if not target.is_relative_to(dist.resolve()) or path == 'api' or path.startswith('api/'):
            raise DomainError('not_found', 'Страница не найдена', status=404)
        if target.is_file() and target.suffix in {'.html', '.js', '.css', '.svg', '.png', '.ico', '.woff2'}:
            return FileResponse(target)
        if not (dist / 'index.html').is_file() and not path.startswith('assets/') and not Path(path).suffix:
            return HTMLResponse('<!doctype html><html lang="ru"><meta charset="utf-8"><title>AI Football</title><h1>Соберите интерфейс</h1><p>В каталоге проекта выполните: npm --prefix web ci и npm --prefix web run build.</p></html>', status_code=503)
        if path.startswith('assets/') or Path(path).suffix or not (dist / 'index.html').is_file():
            raise DomainError('not_found', 'Файл не найден', status=404)
        return FileResponse(dist / 'index.html', headers={'Cache-Control': 'no-cache'})

    return app
