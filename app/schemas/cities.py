from marshmallow import ValidationError, fields, validates

from app.extensions import ma


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
