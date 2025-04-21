import uuid
from datetime import datetime, timezone

from flask import Blueprint, abort, request

from app.constants import MAX_PAGINATION_LIMIT
from app.schemas.cities import CitySchema
from app.utils import execute_neo4j_query
from app.utils.response import APIResponse

bp = Blueprint('cities', __name__, url_prefix='/cities')


@bp.post('/')
def create_city():
    schema = CitySchema()
    inputs = schema.load(request.get_json())

    # Query the database
    result = execute_neo4j_query(
        """
        MERGE (c:City {postal_code: $postal_code})
        SET c.id = $id, c.created_at = $created_at, c.name = $name
        RETURN c
        """,
        {
            'id': str(uuid.uuid4()),
            'created_at': datetime.now(timezone.utc).isoformat(),
            'name': inputs['name'],
            'postal_code': inputs['postal_code'],
        },
    )
    if not result:
        abort(500, 'Something went wrong')

    return APIResponse.success(payload=schema.dump(result['c']), status=201)


@bp.get('/')
def get_cities():
    limit = min(
        request.args.get('limit', default=10, type=int), MAX_PAGINATION_LIMIT
    )
    offset = max(request.args.get('offset', default=0, type=int), 0)

    # Query the database
    results = execute_neo4j_query(
        """
        MATCH (c:City)
        RETURN c
        ORDER BY c.created_at DESC SKIP $offset
        LIMIT $limit
        """,
        {'offset': offset, 'limit': limit},
    )

    # Process the results
    schema = CitySchema()
    return APIResponse.success(
        payload={
            'data': [schema.dump(item.get('c')) for item in results.data()],
            'pagination': {},
        },
    )
