import uuid
from datetime import datetime

from flask import Blueprint, abort, request

from app.constants import DEFAULT_PAGINATION_LIMIT, MAX_PAGINATION_LIMIT
from app.utils import execute_neo4j_query
from app.utils.response import APIResponse

bp = Blueprint('cities', __name__, url_prefix='/cities')


@bp.post('/')
def create_city():
    data = request.get_json()
    name = data['name']
    postal_code = data['postal_code']

    # Query the database
    result = execute_neo4j_query(
        """
        CREATE (c:City {id: $id, created_at: $created_at, name: $name, postal_code: $postal_code})
        RETURN c
        """,
        {
            'id': str(uuid.uuid4()),
            'created_at': datetime.now().isoformat(),
            'name': name,
            'postal_code': postal_code,
        },
        single=True,
    )
    if not result:
        abort(500, 'Something went wrong')

    return APIResponse.success(
        payload=result['c'],
        message='City created successfully',
        status=201,
    )


@bp.get('/')
def get_cities():
    limit = request.args.get(
        'limit', default=DEFAULT_PAGINATION_LIMIT, type=int
    )
    offset = request.args.get('offset', default=0, type=int)

    if not 0 < limit <= MAX_PAGINATION_LIMIT:
        abort(400, f'Limit must be between 1 and {MAX_PAGINATION_LIMIT}')
    if offset < 0:
        abort(400, 'Offset cannot be negative')

    result = execute_neo4j_query(
        """
        MATCH (c:City) RETURN c
        SKIP $offset LIMIT $limit
        """,
        {'offset': offset, 'limit': limit},
    )
    return APIResponse.success(
        payload=[record.get('c') for record in result], status=200
    )


@bp.delete('/<city_id>')
def delete_city(city_id):
    result = execute_neo4j_query(
        """
        MATCH (c:City)
        WHERE c.id = $id
        DELETE c
        RETURN COUNT(c) AS deleted_count
        """,
        {'id': city_id},
        single=True,
    )
    if not result:
        abort(500, 'Something went wrong')

    if result['deleted_count'] == 0:
        abort(404, 'City not found')

    return APIResponse.success(status=200)
