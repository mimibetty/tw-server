from marshmallow import fields, validate
from decimal import Decimal

from app.extensions import ma

class RoundedFloat(fields.Float):
    """Custom field that rounds float values to a specified number of decimal places"""
    def __init__(self, decimals=5, **kwargs):
        self.decimals = decimals
        super().__init__(**kwargs)
    
    def _serialize(self, value, attr, obj, **kwargs):
        if value is None:
            return None
        return round(float(value), self.decimals)
    
    def _deserialize(self, value, attr, data, **kwargs):
        value = super()._deserialize(value, attr, data, **kwargs)
        if value is None:
            return None
        return round(float(value), self.decimals)

class ThingToDoSchema(ma.Schema):
    name = fields.String(required=True)
    address = fields.String(required=True)
    description = fields.String(required=True, allow_none=True)
    longitude = fields.Float(required=True)
    latitude = fields.Float(required=True)
    rawRanking = RoundedFloat(required=True, decimals=5)
    web = fields.String(allow_none=True)
    phone = fields.String(allow_none=True)
    thumbnail = fields.String(allow_none=True)
    photos = fields.List(fields.String())
    rating_histogram = fields.List(fields.Integer())
    new_rating_histogram = fields.List(fields.Integer())
    travelerChoiceAward = fields.Boolean(default=False)