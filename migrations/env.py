from alembic import context
from aifootball.service.config import Settings
from aifootball.service.db import Base, make_engine
from aifootball.service.auth import models
from aifootball.service.captains import models as captain_models
from aifootball.service.tournaments import models as tournament_models
from aifootball.service.catalog import models as catalog_models
from aifootball.service.catalog.roster_imports import models as roster_import_models
from aifootball.service.matches import models as match_models
from aifootball.service.protocol import models as protocol_models
from aifootball.service.halls import models as hall_models
from aifootball.service.analysis import models as analysis_models
from aifootball.service.analysis.team_review import models as team_review_models
from aifootball.service.ratings import models as rating_models
from aifootball.service.stages import models as stage_models

config = context.config
url = config.attributes.get('database_url') or Settings().database_url
if context.is_offline_mode():
    context.configure(url=url, target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    with make_engine(url).connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()

