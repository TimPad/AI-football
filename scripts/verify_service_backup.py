"""Make a private local backup, restore to a fresh *_test DB and verify it.

Run from the repository root with the compose PostgreSQL service running.
Original database and files are never changed. Test restore DB is retained.
"""
import argparse
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import subprocess
import tarfile
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from aifootball.service.config import Settings

parser=argparse.ArgumentParser();parser.add_argument('--source',choices=['organizer','e2e'],default='organizer');args=parser.parse_args()
settings=Settings();url=make_url(settings.database_url)
if args.source=='e2e':
    url=url.set(database='aifootball_e2e')
    settings=settings.model_copy(update={'attachment_root':Path('data/service/e2e-attachments')})
if url.host not in {'127.0.0.1','localhost'} or url.port!=54329:
    raise SystemExit('This verifier only supports the local compose database on port54329.')
root=Path('data/service/backups')/datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
root.mkdir(parents=True,mode=0o700);root.chmod(0o700)
dump=root/'database.dump'
with dump.open('xb') as out:
    dump.chmod(0o600)
    subprocess.run(['docker','compose','exec','-T','db','pg_dump','-U',url.username,'-d',url.database,'-Fc'],stdout=out,check=True)
archive=root/'attachments.tar.gz'
with tarfile.open(archive,'w:gz') as tar:
    if settings.attachment_root.exists():tar.add(settings.attachment_root,arcname='attachments')
archive.chmod(0o600)
name='aifootball_restore_'+uuid4().hex[:8]+'_test'
engine=create_engine(url,isolation_level='AUTOCOMMIT')
with engine.connect() as db:db.execute(text(f'CREATE DATABASE "{name}"'))
with dump.open('rb') as data:
    subprocess.run(['docker','compose','exec','-T','db','pg_restore','-U',url.username,'-d',name,'--exit-on-error','--no-owner'],stdin=data,check=True)
restored=root/'restored-files';restored.mkdir(mode=0o700)
with tarfile.open(archive) as tar:tar.extractall(restored,filter='data')
clone=create_engine(url.set(database=name));tables=['tournaments','matches','protocol_versions','attachments',
    'teams','players','team_members','team_profile_commands','catalog_images','halls','hall_commands','camera_profiles',
    'analysis_jobs','analysis_runs','analysis_assignments','analysis_commands','player_match_metrics','analysis_understanding_decisions']
with engine.connect() as original,clone.connect() as copy:
    for table in tables:
        query=text(f'SELECT count(*) FROM {table}')
        assert original.scalar(query)==copy.scalar(query),table
    snapshots=text('SELECT id, snapshot FROM protocol_versions ORDER BY id')
    assert original.execute(snapshots).all()==copy.execute(snapshots).all()
    publications=text('SELECT id, published_version_id, hall_id, hall_snapshot, camera_profile_id, analysis_revision, active_analysis_run_id, published_analysis_run_id FROM matches ORDER BY id')
    assert original.execute(publications).all()==copy.execute(publications).all()
    for key,size,sha in copy.execute(text('SELECT storage_key,size,sha256 FROM attachments')):
        import hashlib
        raw=(restored/'attachments'/key).read_bytes()
        assert len(raw)==size and hashlib.sha256(raw).hexdigest()==sha
    for table in ['teams','players','team_members','team_profile_commands','catalog_images','halls','hall_commands','camera_profiles']:
        query=text(f'SELECT * FROM {table} ORDER BY id')
        assert original.execute(query).all()==copy.execute(query).all(),table
    for table,order in [('analysis_jobs','id'),('analysis_runs','id'),('analysis_assignments','run_id,track_id'),('analysis_commands','id'),('player_match_metrics','run_id,player_id'),('analysis_understanding_decisions','run_id,revision')]:
        query=text(f'SELECT * FROM {table} ORDER BY {order}')
        assert original.execute(query).all()==copy.execute(query).all(),table
    for storage_key, in copy.execute(text('SELECT DISTINCT storage_key FROM analysis_runs')):
        from aifootball.analytics.exchange import validate_result
        path=restored/'attachments'/'analysis'/storage_key
        assert path.read_bytes()==(settings.attachment_root/'analysis'/storage_key).read_bytes()
        validate_result(path)
    for identifier,size in copy.execute(text('SELECT id,size FROM catalog_images')):
        original_path=settings.attachment_root/'catalog'/f'{identifier}.png'
        restored_path=restored/'attachments'/'catalog'/f'{identifier}.png'
        raw=restored_path.read_bytes()
        assert len(raw)==size and raw==original_path.read_bytes()
print(f'Backup restored and verified: {root}; database: {name}.')
clone.dispose();engine.dispose()
