import logging

from flask import Blueprint
from jwt.exceptions import PyJWTError
from marshmallow import ValidationError
from werkzeug.exceptions import HTTPException

from app.utils.response import APIResponse

from .auth import bp as auth_bp
from .cities import bp as cities_bp
from .things_to_do import bp as things_to_do_bp
from .users import bp as users_bp

logger = logging.getLogger(__name__)

bp = Blueprint('api', __name__, url_prefix='/api')
bp.register_blueprint(auth_bp)
bp.register_blueprint(cities_bp)
bp.register_blueprint(things_to_do_bp)
bp.register_blueprint(users_bp)


@bp.errorhandler(PyJWTError)
def unauthorized_handler(_: PyJWTError):
    return APIResponse.error(error='Unauthorized', status=401)


@bp.errorhandler(ValidationError)
def validation_error_handler(e: ValidationError):
    return APIResponse.error(error=e.messages, status=400)


@bp.errorhandler(HTTPException)
def http_exception_handler(e: HTTPException):
    return APIResponse.error(error=e.description, status=e.code)


@bp.errorhandler(Exception)
def generic_exception_handler(e: Exception):
    return APIResponse.error(error=str(e), status=500)
