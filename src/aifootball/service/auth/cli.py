import argparse
from getpass import getpass
from argon2 import PasswordHasher
from sqlalchemy.orm import Session
from sqlalchemy import select
from aifootball.service.auth.models import Admin
from aifootball.service.config import Settings
from aifootball.service.db import make_engine


def create_admin(db, login, password):
    if len(password) < 12:
        raise ValueError('Пароль должен содержать не менее 12 символов')
    admin = Admin(login=login.strip().lower(), password_hash=PasswordHasher().hash(password))
    db.add(admin)
    db.commit()
    return admin


def main():
    p = argparse.ArgumentParser()
    p.add_argument('command', choices=['create-admin', 'grant-analytics', 'revoke-analytics'])
    p.add_argument('--login', required=True)
    args = p.parse_args()
    with Session(make_engine(Settings().database_url)) as db:
        if args.command == 'create-admin':
            first = getpass('Пароль: ')
            if first != getpass('Повторите пароль: '):
                raise SystemExit('Пароли не совпадают')
            create_admin(db, args.login, first)
            print('Администратор создан')
        else:
            admin = db.scalar(select(Admin).where(Admin.login == args.login.strip().lower()))
            if admin is None:
                raise SystemExit('Администратор не найден')
            admin.can_manage_analytics = args.command == 'grant-analytics'
            db.commit()
            print('Право Админ+ выдано' if admin.can_manage_analytics else 'Право Админ+ отозвано')


if __name__ == '__main__':
    main()
