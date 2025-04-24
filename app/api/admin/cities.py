import uuid
from datetime import datetime, timezone

from flask import Blueprint, abort, request

from app.constants import MAX_PAGINATION_LIMIT
from app.schemas.cities import CitySchema
from app.utils import execute_neo4j_query
from app.utils.response import APIResponse

bp = Blueprint('cities', __name__, url_prefix='/cities')


@bp.post('')
def create_city():
    try:
        schema = CitySchema()
        inputs = schema.load(request.get_json())
        result = execute_neo4j_query(
            """
            MERGE (c:City {postalCode: $postalCode})
            SET c.id = $id, c.createdAt = $createdAt, c.name = $name
            RETURN c
            """,
            {
                'id': str(uuid.uuid4()),
                'createdAt': datetime.now(timezone.utc).isoformat(),
                'name': inputs['name'],
                'postalCode': inputs['postalCode'],
            },
        )
        return APIResponse.success(
            payload=schema.dump(result[0]['c']), status=201
        )
    except Exception as e:
        abort(500, str(e))


@bp.get('')
def get_cities():
    try:
        limit = min(
            request.args.get('limit', default=10, type=int),
            MAX_PAGINATION_LIMIT,
        )
        offset = max(request.args.get('offset', default=0, type=int), 0)

        # Query the database
        results = execute_neo4j_query(
            """
            MATCH (c:City) RETURN c
            ORDER BY c.postalCode SKIP $offset LIMIT $limit
            """,
            {'offset': offset, 'limit': limit},
        )

        # Process the results
        schema = CitySchema()
        return APIResponse.success(
            payload={
                'data': [schema.dump(item.get('c')) for item in results],
                'pagination': {},
            },
        )
    except Exception as e:
        abort(500, str(e))
