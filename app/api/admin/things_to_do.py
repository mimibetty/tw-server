import uuid
from datetime import datetime

from flask import Blueprint, request

from app.utils import execute_neo4j_query
from app.utils.response import APIResponse

bp = Blueprint('things-to-do', __name__, url_prefix='/things-to-do')


@bp.post('/')
def create_things_to_do():
    data = request.get_json()
    name = data['name']
    address = data['address']
    city_id = data['city_id']

    result = execute_neo4j_query(
        """
        MATCH (c:City)
        WHERE c.id = $city_id
        RETURN c
        """,
        {
            'city_id': city_id,
            'id': str(uuid.uuid4()),
            'created_at': datetime.now().isoformat(),
            'name': name,
            'address': address,
        },
    )
    data = result['t']
    data['city'] = result['c']

    return APIResponse.success(payload=data)
