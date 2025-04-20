import logging

from flask import Blueprint
from jwt.exceptions import PyJWTError
from werkzeug.exceptions import HTTPException

from app.utils.response import APIResponse

from .admin import bp as admin_bp
from .auth import bp as auth_bp
from .users import bp as users_bp

logger = logging.getLogger(__name__)

bp = Blueprint('api', __name__, url_prefix='/api')
bp.register_blueprint(admin_bp)
bp.register_blueprint(auth_bp)
bp.register_blueprint(users_bp)


@bp.get('/health')
def health_check():
    """Health check endpoint."""
    return APIResponse.success(message='OK')


# PyJWT Exceptions
@bp.errorhandler(PyJWTError)
def unauthorized_handler(_: PyJWTError):
    """Handle JWT errors."""
    return APIResponse.error(erro='Unauthorized', status=401)


# HTTP Exceptions
@bp.errorhandler(HTTPException)
def http_exception_handler(e: HTTPException):
    """Handle HTTP exceptions."""
    return APIResponse.error(error=e.description, status=e.code)


# Exceptions
@bp.errorhandler(Exception)
def exception_handler(e: Exception):
    """Handle all unhandled exceptions."""
    logger.error(f'Unhandled exception: {e}', exc_info=True)
    return APIResponse.error(message='Internal Server Error', status=500)
