import logging

from flask import Blueprint

logger = logging.getLogger(__name__)
bp = Blueprint('users', __name__, url_prefix='/users')
