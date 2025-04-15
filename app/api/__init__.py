import logging

from flask import Blueprint
from jwt.exceptions import PyJWTError
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
    return create_response(message='OK')


# PyJWT Exceptions
@bp.errorhandler(PyJWTError)
def unauthorized_handler(_: PyJWTError):
    return create_response(
        message=Unauthorized.name, status=Unauthorized.code, default=False
    )


# HTTP Exceptions
@bp.errorhandler(HTTPException)
def http_handler(e: HTTPException):
    if e.code == BadRequest.code:
        return create_response(message=e.description, status=BadRequest.code)
    elif e.code == InternalServerError.code:
        logger.exception(e)

    return create_response(message=e.name, status=e.code)
