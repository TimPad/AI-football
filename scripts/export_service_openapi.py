import argparse
import json
from pathlib import Path
from aifootball.service.app import create_app
from aifootball.service.config import Settings

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--output',type=Path,required=True); args=p.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    # Создание engine ленивое; экспорт не соединяется с БД.
    args.output.write_text(json.dumps(create_app(Settings(database_url='postgresql+psycopg://localhost/openapi')).openapi(),ensure_ascii=False,indent=2),encoding='utf-8')
