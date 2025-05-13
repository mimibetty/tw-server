from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_mail import Mail
from flask_marshmallow import Marshmallow
from flask_migrate import Migrate

jwt = JWTManager()
mail = Mail()
migrate = Migrate()

# Flask-CORS
cors = CORS(
    max_age=86400,
    supports_credentials=True,
    allow_headers=['Content-Type', 'Authorization'],
    methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'],
)

# Flask-Marshmallow
ma = Marshmallow()


def snake_case_to_camel_case(s: str) -> str:
    parts = iter(s.split('_'))
    return next(parts) + ''.join(word.title() for word in parts)


class CamelCaseAutoSchema(ma.SQLAlchemyAutoSchema):
    def on_bind_field(self, field_name, field_obj):
        field_obj.data_key = snake_case_to_camel_case(
            field_obj.data_key or field_name
        )


class CamelCaseSchema(ma.Schema):
    def on_bind_field(self, field_name, field_obj):
        field_obj.data_key = snake_case_to_camel_case(
            field_obj.data_key or field_name
        )
