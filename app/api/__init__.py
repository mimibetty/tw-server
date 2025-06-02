import logging

from flask import Blueprint
from flask_jwt_extended.exceptions import NoAuthorizationError
from jwt.exceptions import ExpiredSignatureError, InvalidSignatureError
from marshmallow import ValidationError

from .auth import blueprint as auth_blueprint
from .cities import blueprint as cities_blueprint
from .conversations import blueprint as conversations_blueprint
from .favourites import blueprint as favourites_blueprint
from .hotels import blueprint as hotels_blueprint
from .restaurants import blueprint as restaurants_blueprint
from .things_to_do import blueprint as things_to_do_blueprint
from .trips import blueprint as trips_blueprint
from .reviews import blueprint as reviews_blueprint
from .places import blueprint as places_blueprint
from .recommendations import blueprint as recommendations_blueprint
from .users import blueprint as users_blueprint

logger = logging.getLogger(__name__)
blueprint = Blueprint('api', __name__, url_prefix='/api')

# Register the blueprints
blueprint.register_blueprint(auth_blueprint)
blueprint.register_blueprint(cities_blueprint)
blueprint.register_blueprint(conversations_blueprint)
blueprint.register_blueprint(favourites_blueprint)
blueprint.register_blueprint(hotels_blueprint)
blueprint.register_blueprint(restaurants_blueprint)
blueprint.register_blueprint(things_to_do_blueprint)
blueprint.register_blueprint(trips_blueprint)
blueprint.register_blueprint(reviews_blueprint)
blueprint.register_blueprint(places_blueprint)
blueprint.register_blueprint(recommendations_blueprint)
blueprint.register_blueprint(users_blueprint)

def unauthorized_handler(_):
    return {'error': 'Unauthorized'}, 401


def validation_handler(error: ValidationError):
    return {'error': error.messages}, 400


def exception_handler(error):
    error_message = str(error)
    logger.error(f'Exception occurred: {error_message}')
    return {'error': error_message}, 500


blueprint.register_error_handler(NoAuthorizationError, unauthorized_handler)
blueprint.register_error_handler(ExpiredSignatureError, unauthorized_handler)
blueprint.register_error_handler(InvalidSignatureError, unauthorized_handler)
blueprint.register_error_handler(ValidationError, validation_handler)
blueprint.register_error_handler(Exception, exception_handler)
