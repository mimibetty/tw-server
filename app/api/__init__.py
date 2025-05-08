import logging

from flask import Blueprint
from flask_jwt_extended.exceptions import NoAuthorizationError
from jwt.exceptions import ExpiredSignatureError, InvalidSignatureError
from marshmallow import ValidationError
from werkzeug.exceptions import HTTPException, InternalServerError

from app.utils.response import APIResponse

from .auth import bp as auth_bp
from .chat import bp as chat_bp
from .cities import bp as cities_bp
from .things_to_do import bp as things_to_do_bp
from .users import bp as users_bp
from .hotels import bp as hotels_bp
from .restaurants import bp as restaurants_bp

logger = logging.getLogger(__name__)

bp = Blueprint('api', __name__, url_prefix='/api')
bp.register_blueprint(auth_bp)
bp.register_blueprint(chat_bp)
bp.register_blueprint(cities_bp)
bp.register_blueprint(things_to_do_bp)
bp.register_blueprint(users_bp)
bp.register_blueprint(hotels_bp)
bp.register_blueprint(restaurants_bp)


def unauthorized_handler(e):
    return APIResponse.error(error='Unauthorized', status=401)


def validation_error_handler(e: ValidationError):
    return APIResponse.error(error=e.messages, status=400)


def http_exception_handler(e: HTTPException):
    return APIResponse.error(error=e.description, status=e.code)


def generic_exception_handler(e: Exception):
    logger.exception(e)
    return APIResponse.error(error=InternalServerError.name, status=500)


bp.register_error_handler(NoAuthorizationError, unauthorized_handler)
bp.register_error_handler(InvalidSignatureError, unauthorized_handler)
bp.register_error_handler(ExpiredSignatureError, unauthorized_handler)
bp.register_error_handler(ValidationError, validation_error_handler)
bp.register_error_handler(HTTPException, http_exception_handler)
bp.register_error_handler(Exception, generic_exception_handler)
