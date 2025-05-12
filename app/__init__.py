import redis
from flask import Flask

from . import extensions as exts
from .api import blueprint
from .environments import (
    REDIS_DB,
    REDIS_HOST,
    REDIS_PASSWORD,
    REDIS_PORT,
    REDIS_USERNAME,
    TEMPLATES_DIR,
    Config,
)
from .models import db


class AppContext:
    instance = None

    def init(self):
        self.app = Flask(__name__, template_folder=TEMPLATES_DIR)
        self.app.config.from_object(Config)

        # Init Redis
        self.redis = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            decode_responses=True,
            username=REDIS_USERNAME,
            password=REDIS_PASSWORD,
        )
        self.redis.flushall()

        # Init extensions
        db.init_app(self.app)
        exts.ma.init_app(self.app)
        exts.jwt.init_app(self.app)
        exts.cors.init_app(self.app)
        exts.mail.init_app(self.app)
        exts.migrate.init_app(self.app, db)

        # Register blueprints
        self.app.register_blueprint(blueprint)

    def __new__(cls):
        if not cls.instance:
            cls.instance = super(AppContext, cls).__new__(cls)
            cls.instance.init()

        return cls.instance

    def get_app(self) -> Flask:
        return self.app

    def get_redis(self) -> redis.Redis:
        return self.redis
