from threading import Lock

import redis
from flask import Flask

from .api import bp
from .constants import TEMPLATES_DIR
from .environments import (
    REDIS_DB,
    REDIS_HOST,
    REDIS_PASSWORD,
    REDIS_PORT,
    REDIS_USERNAME,
    Config,
)
from .extensions import cors, jwt, mail, migrate
from .postgres import db


class AppContext:
    _instance = None
    _lock = Lock()

    def _initialize(self):
        self._app = Flask(__name__, template_folder=TEMPLATES_DIR)
        self._app.config.from_object(Config)

        # Initialize Redis
        self._redis = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            decode_responses=True,
            username=REDIS_USERNAME,
            password=REDIS_PASSWORD,
        )
        self._redis.flushall()

        # Initialize extensions
        db.init_app(self._app)
        jwt.init_app(self._app)
        cors.init_app(self._app)
        mail.init_app(self._app)
        migrate.init_app(self._app, db)

        # Register blueprints
        self._app.register_blueprint(bp)

    def __new__(cls):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(AppContext, cls).__new__(cls)
                    cls._instance._initialize()
        return cls._instance

    def get_app(self) -> Flask:
        return self._app

    def get_redis(self) -> redis.Redis:
        return self._redis
