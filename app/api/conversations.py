import logging

from flask import Blueprint

logger = logging.getLogger(__name__)
blueprint = Blueprint('conversations', __name__, url_prefix='/conversations')
