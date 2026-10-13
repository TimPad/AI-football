import argparse
from getpass import getpass
from argon2 import PasswordHasher
from sqlalchemy.orm import Session
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
    p.add_argument('command', choices=['create-admin'])
    p.add_argument('--login', required=True)
    args = p.parse_args()
    first = getpass('Пароль: ')
    if first != getpass('Повторите пароль: '):
        raise SystemExit('Пароли не совпадают')
    with Session(make_engine(Settings().database_url)) as db:
        create_admin(db, args.login, first)
    print('Администратор создан')


if __name__ == '__main__':
    main()
