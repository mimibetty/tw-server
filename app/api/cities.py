import uuid
from datetime import datetime, timezone

from flask import Blueprint, abort, request

from app.schemas.cities import CitySchema
from app.utils import execute_neo4j_query
from app.utils.response import APIResponse

bp = Blueprint('cities', __name__, url_prefix='/cities')


@bp.post('')
def create_city():
    schema = CitySchema()
    inputs = schema.load(request.json)
    try:
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
        return APIResponse.success(
            payload=schema.dump(result[0]['c']), status=201
        )
    except Exception as e:
        abort(500, str(e))


@bp.get('')
def get_cities():
    try:
        page = max(request.args.get('page', default=1, type=int), 1)
        per_page = min(request.args.get('per_page', default=10, type=int), 50)

        # Query the database for total records
        total_records_result = execute_neo4j_query(
            """
            MATCH (c:City) RETURN count(c) as total_records
            """
        )
        total_records = total_records_result[0]['total_records']

        # Calculate pagination details
        total_pages = (total_records + per_page - 1) // per_page
        next_page = page + 1 if page < total_pages else None
        prev_page = page - 1 if page > 1 else None

        # Query the database for paginated results
        results = execute_neo4j_query(
            """
            MATCH (c:City) RETURN c
            ORDER BY c.postal_code SKIP $offset LIMIT $limit
            """,
            {'offset': (page - 1) * per_page, 'limit': per_page},
        )

        # Process the results
        schema = CitySchema()
        return APIResponse.success(
            payload={
                'data': [schema.dump(item.get('c')) for item in results],
                'pagination': {
                    'total_records': total_records,
                    'current_page': page,
                    'total_pages': total_pages,
                    'per_page': per_page,
                    'next_page': next_page,
                    'prev_page': prev_page,
                },
            },
        )
    except Exception as e:
        abort(500, str(e))
