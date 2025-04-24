from marshmallow import fields

from app.extensions import ma


class CitySchema(ma.Schema):
    name = fields.String(required=True)
    postalCode = fields.String(required=True)

    # Read-only fields
    id = fields.String(dump_only=True)
    created_at = fields.String(dump_only=True)
