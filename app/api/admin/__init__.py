from flask import Blueprint

from .cities import bp as cities_bp
from .things_to_do import bp as things_to_do_bp

bp = Blueprint('admin', __name__, url_prefix='/admin')

# Register blueprints
bp.register_blueprint(cities_bp)
bp.register_blueprint(things_to_do_bp)
