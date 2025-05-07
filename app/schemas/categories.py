from marshmallow import ValidationError, fields, validates

from app.extensions import ma
from .things_to_do import ThingToDoSchema
from .hotels import HotelSchema
from .restaurants import RestaurantSchema
from .cities import CitySchema


class CitySchema(ma.Schema):
    name = fields.String(required=True)
    postal_code = fields.String(required=True)

    # Read-only fields
    id = fields.String(dump_only=True)
    created_at = fields.String(dump_only=True)

    @validates('postal_code')
    def validate_postal_code(self, value: str):
        if not value.isdigit() or len(value) != 6:
            raise ValidationError('Postal code must be a 6-digit number.')


class HotelsCategorySchema(ma.Schema):
    name = fields.String(required=True, default='hotels')
    places = fields.List(fields.Nested(HotelSchema), required=True)


class ThingsToDoCategorySchema(ma.Schema):
    name = fields.String(required=True, default='things_to_do')
    places = fields.List(fields.Nested(ThingToDoSchema), required=True)


class RestaurantsCategorySchema(ma.Schema):
    name = fields.String(required=True, default='restaurants')
    places = fields.List(fields.Nested(RestaurantSchema), required=True)


class CityCategoriesSchema(ma.Schema):
    city = fields.Nested(CitySchema, required=True)
    hotels = fields.Nested(HotelsCategorySchema, required=True)
    things_to_do = fields.Nested(ThingsToDoCategorySchema, required=True)
    restaurants = fields.Nested(RestaurantsCategorySchema, required=True)
