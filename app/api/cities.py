import logging

from flask import Blueprint, request
from marshmallow import ValidationError, fields, validates

from app.extensions import CamelCaseSchema
from app.utils import create_paging, execute_neo4j_query

logger = logging.getLogger(__name__)
blueprint = Blueprint('cities', __name__, url_prefix='/cities')


class CitySchema(CamelCaseSchema):
    created_at = fields.String(dump_only=True)
    element_id = fields.String(dump_only=True)

    name = fields.String(required=True)
    postal_code = fields.String(required=True)

    @validates('postal_code')
    def validate_postal_code(self, value: str):
        if not value.isdigit():
            raise ValidationError('Postal code must be numeric')
        if len(value) != 6:
            raise ValidationError('Postal code must be 6 digits long')


@blueprint.post('/')
def create_city():
    schema = CitySchema()
    data = schema.load(request.json)
    result = execute_neo4j_query(
        """
        MERGE (c:City {postal_code: $postal_code})
        ON CREATE SET
            c.name = $name,
            c.created_at =
                apoc.date.format(timestamp(), 'ms', 'yyyy-MM-dd HH:mm', 'GMT+7')
        RETURN c
        """,
        {
            'name': data['name'],
            'postal_code': data['postal_code'],
        },
    )
    return schema.dump(result[0]['c']), 201


@blueprint.get('/')
def get_cities():
    # Get pagination parameters from the request
    page = request.args.get('page', default=1, type=int)
    size = request.args.get('size', default=10, type=int)
    offset = (page - 1) * size

    # Query to get total count of cities
    total_count_result = execute_neo4j_query(
        """
        MATCH (c:City)
        RETURN count(c) AS total_count
        """
    )
    total_count = total_count_result[0]['total_count']

    # Query to get paginated cities
    result = execute_neo4j_query(
        """
        MATCH (c:City)
        RETURN c
        ORDER BY c.postal_code
        SKIP $offset
        LIMIT $size
        """,
        {'offset': offset, 'size': size},
    )

    # Create paginated response
    response = create_paging(
        data=CitySchema(many=True).dump([record['c'] for record in result]),
        page=page,
        size=size,
        offset=offset,
        total_count=total_count,
    )

    return response, 200


@blueprint.get('/<string:postal_code>')
def get_city_by_postal_code(postal_code):
    result = execute_neo4j_query(
        """
        MATCH (c:City {postal_code: $postal_code})
        RETURN c
        """,
        {'postal_code': postal_code},
    )

    if not result:
        return {'error': 'City not found'}, 404

    return CitySchema().dump(result[0]['c']), 200


@blueprint.put('/<string:postal_code>')
def update_city(postal_code):
    data = CitySchema().load(request.json)
    result = execute_neo4j_query(
        """
        MATCH (c:City {postal_code: $postal_code})
        SET c.name = $name
        RETURN c
        """,
        {
            'postal_code': postal_code,
            'name': data['name'],
        },
    )

    if not result:
        return {'error': 'City not found'}, 404

    return CitySchema().dump(result[0]['c']), 200


@blueprint.delete('/<string:postal_code>')
def delete_city(postal_code):
    result = execute_neo4j_query(
        """
        MATCH (c:City {postal_code: $postal_code})
        DELETE c
        RETURN count(c) AS deleted_count
        """,
        {'postal_code': postal_code},
    )

    if not result or result[0]['deleted_count'] == 0:
        return {'error': 'City not found'}, 404

    return 204
