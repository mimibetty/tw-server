from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_mail import Mail
from flask_marshmallow import Marshmallow
from flask_migrate import Migrate

from .environments import CORS_ORIGINS

ma = Marshmallow()
jwt = JWTManager()
cors = CORS(
    origins=CORS_ORIGINS,
    methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
    allow_headers=['Content-Type', 'Authorization', 'Accept'],
)
mail = Mail()
migrate = Migrate()
