from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_mail import Mail
from flask_marshmallow import Marshmallow
from flask_migrate import Migrate

ma = Marshmallow()
jwt = JWTManager()
mail = Mail()
migrate = Migrate()

# Flask-CORS
cors = CORS(
    supports_credentials=True,
    resources={r'/api/*': {'origins': '*'}},
    methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'],
)
