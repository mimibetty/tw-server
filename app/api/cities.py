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


@blueprint.get('/<string:postal_code>/')
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


@blueprint.put('/<postal_code>/')
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


@blueprint.delete('/<postal_code>/')
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


@blueprint.delete('/<postal_code>/children')
def delete_city_children(postal_code):
    """
    Delete all nodes connected to a city (hotels, restaurants, attractions, etc.)
    but keep the city node itself.
    """
    # First check if city exists
    city_result = execute_neo4j_query(
        """
        MATCH (c:City {postal_code: $postal_code})
        RETURN c
        """,
        {'postal_code': postal_code},
    )

    if not city_result:
        return {'error': 'City not found'}, 404
        
    # Delete all relationships and connected nodes
    result = execute_neo4j_query(
        """
        MATCH (c:City {postal_code: $postal_code})
        OPTIONAL MATCH (n)-[r:LOCATED_IN]->(c)
        WITH n, r
        WHERE n IS NOT NULL
        DETACH DELETE n
        """,
        {'postal_code': postal_code},
    )
    
    # Get statistics about deleted nodes
    stats_result = execute_neo4j_query(
        """
        MATCH (c:City {postal_code: $postal_code})
        OPTIONAL MATCH (connected_node)-[:LOCATED_IN]->(c)
        RETURN count(connected_node) AS remaining_nodes
        """,
        {'postal_code': postal_code},
    )
    
    remaining = stats_result[0]['remaining_nodes']
    
    # Clear any orphaned nodes that might be connected to the deleted nodes
    cleanup_result = execute_neo4j_query(
        """
        MATCH (orphan)
        WHERE NOT (orphan)-[]-() AND NOT orphan:City
        DELETE orphan
        """,
    )
    
    return {
        'message': 'Successfully deleted all nodes connected to the city',
        'postal_code': postal_code,
        'remaining_connected_nodes': remaining,
    }, 200


@blueprint.delete('/<postal_code>/hotels')
def delete_city_hotels(postal_code):
    """
    Delete all hotel nodes connected to a city but keep other nodes.
    """
    # First check if city exists
    city_result = execute_neo4j_query(
        """
        MATCH (c:City {postal_code: $postal_code})
        RETURN c
        """,
        {'postal_code': postal_code},
    )

    if not city_result:
        return {'error': 'City not found'}, 404
        
    # Delete all hotel nodes and their relationships
    result = execute_neo4j_query(
        """
        MATCH (c:City {postal_code: $postal_code})
        OPTIONAL MATCH (h:Hotel)-[r:LOCATED_IN]->(c)
        WITH h, r
        WHERE h IS NOT NULL
        DETACH DELETE h
        """,
        {'postal_code': postal_code},
    )
    
    # Get statistics about remaining hotel nodes
    stats_result = execute_neo4j_query(
        """
        MATCH (c:City {postal_code: $postal_code})
        OPTIONAL MATCH (h:Hotel)-[:LOCATED_IN]->(c)
        RETURN count(h) AS remaining_hotels
        """,
        {'postal_code': postal_code},
    )
    
    remaining = stats_result[0]['remaining_hotels']
    
    return {
        'message': 'Successfully deleted all hotel nodes connected to the city',
        'postal_code': postal_code,
        'remaining_hotels': remaining,
    }, 200


@blueprint.delete('/<postal_code>/restaurants')
def delete_city_restaurants(postal_code):
    """
    Delete all restaurant nodes connected to a city but keep other nodes.
    """
    # First check if city exists
    city_result = execute_neo4j_query(
        """
        MATCH (c:City {postal_code: $postal_code})
        RETURN c
        """,
        {'postal_code': postal_code},
    )

    if not city_result:
        return {'error': 'City not found'}, 404
        
    # Delete all restaurant nodes and their relationships
    result = execute_neo4j_query(
        """
        MATCH (c:City {postal_code: $postal_code})
        OPTIONAL MATCH (r:Restaurant)-[rel:LOCATED_IN]->(c)
        WITH r, rel
        WHERE r IS NOT NULL
        DETACH DELETE r
        """,
        {'postal_code': postal_code},
    )
    
    # Get statistics about remaining restaurant nodes
    stats_result = execute_neo4j_query(
        """
        MATCH (c:City {postal_code: $postal_code})
        OPTIONAL MATCH (r:Restaurant)-[:LOCATED_IN]->(c)
        RETURN count(r) AS remaining_restaurants
        """,
        {'postal_code': postal_code},
    )
    
    remaining = stats_result[0]['remaining_restaurants']
    
    return {
        'message': 'Successfully deleted all restaurant nodes connected to the city',
        'postal_code': postal_code,
        'remaining_restaurants': remaining,
    }, 200


@blueprint.delete('/<postal_code>/things-to-do')
def delete_city_things_to_do(postal_code):
    """
    Delete all things-to-do nodes connected to a city but keep other nodes.
    """
    # First check if city exists
    city_result = execute_neo4j_query(
        """
        MATCH (c:City {postal_code: $postal_code})
        RETURN c
        """,
        {'postal_code': postal_code},
    )

    if not city_result:
        return {'error': 'City not found'}, 404
        
    # Delete all things-to-do nodes and their relationships
    result = execute_neo4j_query(
        """
        MATCH (c:City {postal_code: $postal_code})
        OPTIONAL MATCH (t:ThingToDo)-[r:LOCATED_IN]->(c)
        WITH t, r
        WHERE t IS NOT NULL
        DETACH DELETE t
        """,
        {'postal_code': postal_code},
    )
    
    # Get statistics about remaining things-to-do nodes
    stats_result = execute_neo4j_query(
        """
        MATCH (c:City {postal_code: $postal_code})
        OPTIONAL MATCH (t:ThingToDo)-[:LOCATED_IN]->(c)
        RETURN count(t) AS remaining_things_to_do
        """,
        {'postal_code': postal_code},
    )
    
    remaining = stats_result[0]['remaining_things_to_do']
    
    return {
        'message': 'Successfully deleted all things-to-do nodes connected to the city',
        'postal_code': postal_code,
        'remaining_things_to_do': remaining,
    }, 200
