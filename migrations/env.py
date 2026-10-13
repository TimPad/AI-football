from alembic import context
from aifootball.service.config import Settings
from aifootball.service.db import Base, make_engine
from aifootball.service.auth import models

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
