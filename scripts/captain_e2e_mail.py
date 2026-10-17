"""Synthetic mail reader for an isolated local E2E database. Never uses SMTP."""
import base64
E2E_MAIL_KEY=base64.urlsafe_b64encode(b'C'*32).decode()
class MemoryMailSender:
    def __init__(self):self.messages=[]
    def send(self,message,key):
        if not any(m['key']==key for m in self.messages):self.messages.append({**message,'key':key})

def main():
    import argparse,os,json
    from pathlib import Path
    from sqlalchemy.engine import make_url
    from aifootball.service.config import Settings
    from aifootball.service.app import create_app
    from aifootball.service.captains.mail import deliver_pending
    p=argparse.ArgumentParser();p.add_argument('--email',required=True);args=p.parse_args()
    os.chdir(Path(__file__).resolve().parents[1]);database=os.environ.get('AIF_E2E_DATABASE_NAME','aifootball_e2e')
    assert database.startswith('aifootball_') and database.endswith('_e2e') and database.replace('_','').isalnum()
    url=make_url(Settings().database_url).set(database=database);assert url.host in {'127.0.0.1','localhost'}
    app=create_app(Settings(database_url=url.render_as_string(hide_password=False),captain_mail_key=E2E_MAIL_KEY));app.state.mail_sender=MemoryMailSender()
    try:
        deliver_pending(app)
        messages=[m for m in app.state.mail_sender.messages if m['to']==args.email]
        if not messages:raise SystemExit('Synthetic mail not found')
        print(json.dumps({'url':messages[-1]['url']}))
    finally:app.state.engine.dispose()
if __name__=='__main__':main()
