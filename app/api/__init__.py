import logging

from flask import Blueprint
from flask_jwt_extended.exceptions import NoAuthorizationError
from jwt.exceptions import ExpiredSignatureError
from marshmallow import ValidationError
from werkzeug.exceptions import HTTPException

from app.utils import create_response

from .auth import bp as auth_bp
from .users import bp as users_bp

logger = logging.getLogger(__name__)

bp = Blueprint('api', __name__, url_prefix='/api')
bp.register_blueprint(auth_bp)
bp.register_blueprint(users_bp)


def unauthorized_handler(e):
    return create_response(message='Unauthorized', status=401)


def validation_handler(e: ValidationError):
    return create_response(data=e.messages, status=400)


def http_handler(e: HTTPException):
    return create_response(message=e.description, status=e.code)


def unknown_handler(e: Exception):
    logger.exception('Unknown error occurred:', exc_info=e)
    return create_response(message='Internal Server Error', status=500)


bp.register_error_handler(ValidationError, validation_handler)
bp.register_error_handler(NoAuthorizationError, unauthorized_handler)
bp.register_error_handler(ExpiredSignatureError, unauthorized_handler)
bp.register_error_handler(HTTPException, http_handler)
bp.register_error_handler(Exception, unknown_handler)
