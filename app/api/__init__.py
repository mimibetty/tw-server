import logging

from flask import Blueprint
from flask_jwt_extended.exceptions import NoAuthorizationError
from jwt.exceptions import ExpiredSignatureError
from werkzeug.exceptions import (
    BadRequest,
    HTTPException,
    InternalServerError,
    Unauthorized,
)

from app.utils import create_response

from .auth import bp as auth_bp
from .users import bp as users_bp

logger = logging.getLogger(__name__)

bp = Blueprint('api', __name__, url_prefix='/api')
bp.register_blueprint(auth_bp)
bp.register_blueprint(users_bp)


@bp.get('/health')
def health_check():
    return create_response(message='OK', status=200)


# JWT Exceptions
def unauthorized_handler(_):
    return create_response(message=Unauthorized.name, status=Unauthorized.code)


bp.register_error_handler(NoAuthorizationError, unauthorized_handler)
bp.register_error_handler(ExpiredSignatureError, unauthorized_handler)


# HTTP Exceptions
@bp.errorhandler(HTTPException)
def http_handler(e: HTTPException):
    if e.code == BadRequest.code:
        return create_response(message=e.description, status=BadRequest.code)
    elif e.code == InternalServerError.code:
        logger.exception(e)

    return create_response(message=e.name, status=e.code)
