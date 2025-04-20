from datetime import datetime

from flask import Blueprint, abort, request

from app.constants import DEFAULT_LIMIT, MAX_LIMIT
from app.utils import get_neo4j
from app.utils.response import APIResponse

bp = Blueprint('cities', __name__, url_prefix='/cities')


@bp.post('/')
def create_city():
    data = request.get_json()
    name = data['name']
    postal_code = data['postal_code']

    # Query the database
    driver = get_neo4j()
    with driver.session() as session:
        result = session.run(
            """
            CREATE (c:City {created_at: $created_at, name: $name, postal_code: $postal_code})
            RETURN
                elementId(c) AS id,
                c.created_at AS created_at,
                c.name AS name,
                c.postal_code AS postal_code
            """,
            created_at=datetime.now().isoformat(),
            name=name,
            postal_code=postal_code,
        ).single()
        if not result:
            abort(500, 'Something went wrong')

        return APIResponse.success(
            data=result.data(), message='City created successfully', status=201
        )


@bp.get('/')
def get_cities():
    limit = request.args.get('limit', default=DEFAULT_LIMIT, type=int)
    offset = request.args.get('offset', default=0, type=int)

    if not 0 < limit <= MAX_LIMIT:
        abort(400, f'Limit must be between 1 and {MAX_LIMIT}')
    if offset < 0:
        abort(400, 'Offset cannot be negative')

    driver = get_neo4j()
    with driver.session() as session:
        result = session.run(
            """
            MATCH (c:City)
            RETURN
                elementId(c) AS id,
                c.created_at AS created_at,
                c.name AS name,
                c.postal_code AS postal_code
            SKIP $offset
            LIMIT $limit
            """,
            offset=offset,
            limit=limit,
        ).data()
        if not result:
            abort(500, 'Something went wrong')

        return APIResponse.success(data=result, status=200)


@bp.delete('/<city_id>')
def delete_city(city_id):
    driver = get_neo4j()
    with driver.session() as session:
        result = session.run(
            """
            MATCH (c:City)
            WHERE elementId(c) = $city_id
            DELETE c
            RETURN COUNT(c) AS deleted_count
            """,
            city_id=city_id,
        ).single()

        if not result:
            abort(500, 'Something went wrong')

        if result['deleted_count'] == 0:
            abort(404, 'City not found')

        return APIResponse.success(status=204)
