from flask import Blueprint
from marshmallow import ValidationError, fields, validates

from app.extensions import CamelCaseSchema
from app.utils import execute_neo4j_query

blueprint = Blueprint('restaurants', __name__, url_prefix='/restaurants')


class CitySchema(CamelCaseSchema):
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


class RestaurantSchema(CamelCaseSchema):
    created_at = fields.String(dump_only=True)
    element_id = fields.String(dump_only=True)

    # Address
    city = fields.Nested(CitySchema)

    # Common fields
    city = fields.Nested(CitySchema)
    email = fields.Email(required=True, allow_none=True)
    image = fields.String(required=True)
    latitude = fields.Float(required=True)
    longitude = fields.Float(required=True)
    name = fields.String(required=True)
    phone = fields.String(required=True, allow_none=True)
    photos = fields.List(fields.String(), required=True)
    price_levels = fields.List(fields.String(), required=True)
    rating = fields.Float(required=True)
    rating_histogram = fields.List(fields.Integer(), required=True)
    raw_ranking = fields.Float(required=True)
    street = fields.String(required=True)
    type = fields.Constant('RESTAURANT', dump_only=True)
    website = fields.String(required=True, allow_none=True)

    # Specific fields
    cuisines = fields.List(fields.String(), required=True)
    dietary_restrictions = fields.List(fields.String(), required=True)
    features = fields.List(fields.String(), required=True)
    meal_types = fields.List(fields.String(), required=True)
    menu_web_url = fields.String(required=True, allow_none=True)

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
