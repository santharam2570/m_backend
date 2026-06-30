import os

import mongoengine
from dotenv import load_dotenv


def initialize_db(app):
    load_dotenv()
    settings = app.config.get('MONGODB_SETTINGS', {})
    db_name = os.environ.get('MONGODB_DB') or settings.get('db', 'map_backend')

    mongo_uri = os.environ.get('MONGO_URI')
    if mongo_uri:
        mongoengine.connect(db=db_name, host=mongo_uri)
        return

    host = settings.get('host', 'localhost')
    port = settings.get('port', 27017)
    username = settings.get('username')
    password = settings.get('password')

    if username and password:
        mongoengine.connect(
            db=db_name,
            host=host,
            port=port,
            username=username,
            password=password,
        )
    else:
        mongoengine.connect(db=db_name, host=host, port=port)
