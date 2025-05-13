import logging

from flask import Blueprint
from marshmallow import ValidationError, fields, validates

from app.extensions import CamelCaseSchema
from app.utils import execute_neo4j_query

logger = logging.getLogger(__name__)
blueprint = Blueprint('restaurants', __name__, url_prefix='/restaurants')


class AttachCitySchema(CamelCaseSchema):
    created_at = fields.String(dump_only=True)
    element_id = fields.String(dump_only=True)
    name = fields.String(dump_only=True)

    postal_code = fields.String(required=True)

    @validates('postal_code')
    def validate_postal_code(self, value: str):
        result = execute_neo4j_query(
            """
            MATCH (c:City {postal_code: $postal_code})
            RETURN c
            """,
            {'postal_code': value},
        )
        if not result:
            raise ValidationError('City with this postal code does not exist')
        return value


class ShortRestaurantSchema(CamelCaseSchema):
    created_at = fields.String(dump_only=True)
    element_id = fields.String(dump_only=True)
    city = fields.Nested(AttachCitySchema, required=True)
    email = fields.Email(required=True, allow_none=True)
    image = fields.String(required=True)
    latitude = fields.Float(required=True)
    longitude = fields.Float(required=True)
    name = fields.String(required=True)
    price_levels = fields.List(fields.String(), required=True)
    rating = fields.Float(required=True)
    rating_histogram = fields.List(fields.Integer(), required=True)
    raw_ranking = fields.Float(required=True, load_only=True)
    street = fields.String(required=True)
    type = fields.String(dump_only=True)

    @validates('rating')
    def validate_rating(self, value: float):
        if value < 0 or value > 5:
            raise ValidationError('Rating must be between 0 and 5')
        return value

    @validates('rating_histogram')
    def validate_rating_histogram(self, value: list):
        if len(value) != 5:
            raise ValidationError(
                'Rating histogram must contain exactly 5 integers'
            )
        if not all(isinstance(i, int) and i > 0 for i in value):
            raise ValidationError(
                'Rating histogram must be a list of 5 positive integers'
            )
        return value

    @validates('raw_ranking')
    def validate_raw_ranking(self, value: float):
        if value < 0 or value > 5:
            raise ValidationError('Raw ranking must be between 0 and 5')
        return value


class RestaurantSchema(ShortRestaurantSchema):
    # Common fields
    phone = fields.String(required=True, allow_none=True)
    photos = fields.List(fields.String(), required=True)
    website = fields.String(required=True, allow_none=True)

    # Specific fields
    # Not implemented yet


@blueprint.post('/')
def create_restaurant():
    # Needs to be implemented
    pass


@blueprint.get('/')
def get_restaurants():
    # Needs to be implemented
    pass


@blueprint.get('/<string:element_id>')
def get_restaurant(element_id: str):
    # Needs to be implemented
    pass
