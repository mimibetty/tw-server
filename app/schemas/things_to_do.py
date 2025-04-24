from marshmallow import fields

from app.extensions import ma

from .cities import CitySchema


class DetailAddressSchema(ma.Schema):
    street = fields.String(required=True)
    city = fields.Nested(CitySchema, required=True)


class RatingHistogramSchema(ma.Schema):
    count1 = fields.Integer()
    count2 = fields.Integer()
    count3 = fields.Integer()
    count4 = fields.Integer()
    count5 = fields.Integer()


class ThingToDoSchema(ma.Schema):
    name = fields.String(required=True)
    address = fields.Nested(DetailAddressSchema, required=True)
    description = fields.String(required=True)
    longitude = fields.Float(required=True)
    latitude = fields.Float(required=True)
    rawRanking = fields.Float(required=True)
    rating = fields.Float(required=True)
    web = fields.String()
    phone = fields.String()
    thumbnail = fields.String()
    photos = fields.List(fields.String())
