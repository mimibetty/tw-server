from flask import Blueprint

from .cities import bp as cities_bp

bp = Blueprint('admin', __name__, url_prefix='/admin')

# Register blueprints
bp.register_blueprint(cities_bp)
