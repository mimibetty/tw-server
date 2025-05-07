from marshmallow import fields
from app.extensions import ma


class HotelSchema(ma.Schema):
    name = fields.String(required=True)
    amenities = fields.List(fields.String(), allow_none=True)
    photos = fields.List(fields.String(), allow_none=True)
    aiReviewsSummary = fields.String(allow_none=True)
    image = fields.String(allow_none=True)
    webUrl = fields.String(allow_none=True)
    email = fields.String(allow_none=True)
    hotelClass = fields.String(allow_none=True)
    priceRange = fields.String(allow_none=True)
    description = fields.String(allow_none=True)
    priceLevel = fields.String(allow_none=True)
    localName = fields.String(allow_none=True)
    travelerChoiceAward = fields.String(allow_none=True)
    website = fields.String(allow_none=True)
    rawRanking = fields.Float(allow_none=True)
    numberOfRooms = fields.Integer(allow_none=True)
    whatsAppRedirectUrl = fields.String(allow_none=True)
    longitude = fields.Float(required=True)
    latitude = fields.Float(required=True)
    address = fields.String(allow_none=True)
    phone = fields.String(allow_none=True)
    rating_histogram = fields.List(fields.Integer(), allow_none=True)
    new_rating_histogram = fields.List(fields.Integer(), allow_none=True)
