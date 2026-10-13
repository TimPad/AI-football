from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from aifootball.service.config import Settings
from aifootball.service.db import make_engine
from aifootball.service.errors import DomainError, error_body
from aifootball.service.auth.routes import router as auth_router


def create_app(settings=None):
    settings = settings or Settings()
    app = FastAPI(title='Кабинет турниров', version='0.1.0')
    app.state.settings = settings
    app.state.engine = make_engine(settings.database_url)
    app.include_router(auth_router, prefix='/api/v1')
    from aifootball.service.tournaments.routes import router as tournament_router
    app.include_router(tournament_router, prefix='/api/v1')
    from aifootball.service.catalog.routes import router as catalog_router
    from aifootball.service.matches.routes import router as match_router
    app.include_router(catalog_router, prefix='/api/v1')
    app.include_router(match_router, prefix='/api/v1')

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
            return {'status': 'ready', 'schema_version': version}
        except SQLAlchemyError:
            return JSONResponse({'status': 'not_ready'}, status_code=503)

    return app
