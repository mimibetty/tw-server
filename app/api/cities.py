import uuid
from datetime import datetime, timezone

from flask import Blueprint, request

from app.schemas.cities import CitySchema
from app.utils import execute_neo4j_query
from app.utils.response import APIResponse

bp = Blueprint('cities', __name__, url_prefix='/cities')


@bp.post('')
def create_city():
    schema = CitySchema()
    inputs = schema.load(request.json)
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
    return APIResponse.success(data=schema.dump(result[0]['c']), status=201)


@bp.get('')
def get_cities():
    page = max(request.args.get('page', default=1, type=int), 1)
    per_page = min(request.args.get('per_page', default=10, type=int), 50)

    # Query the database for total records
    total_records_result = execute_neo4j_query(
        'MATCH (c:City) RETURN count(c) as total_records'
    )

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
    return APIResponse.paginate(
        data=[schema.dump(item.get('c')) for item in results],
        page=page,
        per_page=per_page,
        total_records=total_records_result[0]['total_records'],
    )
