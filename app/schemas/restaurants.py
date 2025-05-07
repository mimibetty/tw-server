from marshmallow import fields

from app.extensions import ma

from .cities import CitySchema

class OpenHourSchema(ma.Schema):
    open = fields.Integer()
    openHours = fields.String()
    close = fields.Integer()
    closeHours = fields.String()

class HoursSchema(ma.Schema):
    weekRanges = fields.List(fields.List(fields.Nested(OpenHourSchema)))
    timezone = fields.String()

class RestaurantSchema(ma.Schema):
    localName = fields.String()
    name = fields.String()
    description = fields.String()
    travelerChoiceAward = fields.String(allow_none=True)
    phone = fields.String()
    address = fields.String()
    latitude = fields.Float()
    longitude = fields.Float()
    mealTypes = fields.List(fields.String())
    cuisines = fields.List(fields.String())
    dishes = fields.List(fields.String())
    features = fields.List(fields.String())
    dietaryRestrictions = fields.List(fields.String())
    hours = fields.Nested(HoursSchema)
    website = fields.String(allow_none=True)
    email = fields.String()
    rawRanking = fields.Float()
    menuWebUrl = fields.String(allow_none=True)
    webUrl = fields.String()
    priceLevel = fields.String()
    image = fields.String()
    photos = fields.List(fields.String())
    rating_histogram = fields.List(fields.Integer())
    new_rating_histogram = fields.List(fields.Integer())