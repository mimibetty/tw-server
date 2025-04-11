from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_mail import Mail
from flask_migrate import Migrate

from .environments import CORS_ORIGINS

jwt = JWTManager()
cors = CORS(origins=CORS_ORIGINS)
mail = Mail()
migrate = Migrate()
