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
