import os

basedir = os.path.abspath(os.path.dirname(__name__))

#SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, 'app.db')
SQLALCHEMY_DATABASE_URI = 'mysql+oursql://lime:limelime@localhost/lime?charset=utf8'
SQLALCHEMY_MIGRATE_REPO = os.path.join(basedir, 'db_repository')

REDIS_HOST = 'localhost'
REDIS_PORT = 6379
REDIS_DB = 0

WTF_CSRF_ENABLED = True
SECRET_KEY = 'f324awfeb@#arber'
