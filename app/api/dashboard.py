import logging
from flask import Blueprint, jsonify, request, Response
from flask_jwt_extended import jwt_required
from marshmallow import fields, ValidationError
from app.extensions import ma
from app.models import db
from app.utils import execute_neo4j_query, create_paging

logger = logging.getLogger(__name__)
blueprint = Blueprint('dashboard', __name__, url_prefix='/dashboard')


class DashboardStatsSchema(ma.Schema):
    element_id = fields.String(dump_only=True)
    name = fields.String(dump_only=True)
    description = fields.String(dump_only=True, allow_none=True)
    email = fields.String(dump_only=True, allow_none=True)
    image = fields.String(dump_only=True, allow_none=True)
    latitude = fields.Float(dump_only=True, allow_none=True)
    longitude = fields.Float(dump_only=True, allow_none=True)
    phone = fields.String(dump_only=True, allow_none=True)
    rating = fields.Float(dump_only=True, allow_none=True)
    rating_histogram = fields.List(fields.Integer(), dump_only=True, default=list)
    raw_ranking = fields.Float(dump_only=True, allow_none=True)
    street = fields.String(dump_only=True, allow_none=True)
    website = fields.String(dump_only=True, allow_none=True)
    type = fields.String(dump_only=True)
    city = fields.Dict(dump_only=True, allow_none=True)
    trip_count = fields.Integer(dump_only=True)


class DashboardRankingSchema(ma.Schema):
    element_id = fields.String(dump_only=True)
    name = fields.String(dump_only=True)
    description = fields.String(dump_only=True, allow_none=True)
    email = fields.String(dump_only=True, allow_none=True)
    image = fields.String(dump_only=True, allow_none=True)
    latitude = fields.Float(dump_only=True, allow_none=True)
    longitude = fields.Float(dump_only=True, allow_none=True)
    phone = fields.String(dump_only=True, allow_none=True)
    rating = fields.Float(dump_only=True, allow_none=True)
    rating_histogram = fields.List(fields.Integer(), dump_only=True, default=list)
    raw_ranking = fields.Float(dump_only=True, allow_none=True)
    street = fields.String(dump_only=True, allow_none=True)
    website = fields.String(dump_only=True, allow_none=True)
    type = fields.String(dump_only=True)
    city = fields.Dict(dump_only=True, allow_none=True)
    review_number = fields.Integer(dump_only=True)


class DashboardQuerySchema(ma.Schema):
    place_type = fields.String(
        required=False,
        missing='all',
        validate=lambda x: x in ['all', 'hotels', 'restaurants', 'things-to-do']
    )
    order = fields.String(
        required=False,
        missing='desc',
        validate=lambda x: x in ['asc', 'desc']
    )
    page = fields.Integer(required=False, missing=1, validate=lambda x: x >= 1)
    size = fields.Integer(required=False, missing=10, validate=lambda x: 1 <= x <= 100)


@blueprint.get('/statistics/places')
@jwt_required()
def get_places_statistics():
    """Get statistics about top places and how many times they've been added to trips."""
    try:
        # Validate query parameters
        schema = DashboardQuerySchema()
        try:
            args = schema.load(request.args)
        except ValidationError as e:
            return jsonify({'error': 'Invalid parameters', 'details': e.messages}), 400

        place_type = args['place_type']
        order = args['order']
        page = args['page']
        size = args['size']
        offset = (page - 1) * size

        # Get place statistics from PostgreSQL (count how many times each place appears in trips)
        trip_stats_query = """
        SELECT 
            place_id, 
            COUNT(*) as trip_count
        FROM trips 
        GROUP BY place_id
        ORDER BY trip_count {order}
        """.format(order='DESC' if order == 'desc' else 'ASC')

        trip_stats_result = db.session.execute(db.text(trip_stats_query))
        place_stats = {row.place_id: row.trip_count for row in trip_stats_result}

        if not place_stats:
            # Return empty result with proper pagination structure
            return jsonify({
                'data': [],
                'paging': create_paging(0, page, 1, size, 0)
            }), 200

        # Get place details from Neo4j
        place_ids = list(place_stats.keys())
        
        # Build type filter for Neo4j query
        type_filter = ""
        if place_type == 'things-to-do':
            type_filter = "AND p:ThingToDo"
        elif place_type == 'hotels':
            type_filter = "AND p:Hotel"
        elif place_type == 'restaurants':
            type_filter = "AND p:Restaurant"
        # For 'all', no additional filter needed

        neo4j_query = f"""
        UNWIND $place_ids AS pid
        MATCH (p) WHERE elementId(p) = pid {type_filter}
        OPTIONAL MATCH (p)-[:LOCATED_IN]->(c:City)
        RETURN p AS place,
               elementId(p) AS element_id,
               CASE 
                   WHEN labels(p)[0] = 'Hotel' THEN 'HOTEL'
                   WHEN labels(p)[0] = 'Restaurant' THEN 'RESTAURANT' 
                   WHEN labels(p)[0] = 'ThingToDo' THEN 'THING_TO_DO'
                   ELSE 'UNKNOWN'
               END AS type,
               c.name AS city_name,
               c.created_at AS city_created_at,
               c.postal_code AS city_postal_code
        """

        places_data = execute_neo4j_query(neo4j_query, {'place_ids': place_ids})

        if not places_data:
            return jsonify({
                'data': [],
                'paging': create_paging(0, page, 1, size, 0)
            }), 200

        # Combine place data with trip statistics
        places_with_stats = []
        for place_data in places_data:
            place = place_data['place']
            element_id = place_data['element_id']
            
            # Add trip count from statistics
            place['trip_count'] = place_stats.get(element_id, 0)
            place['element_id'] = element_id
            place['type'] = place_data['type']
            
            
            # Add city information
            if place_data.get('city_name'):
                place['city'] = {
                    'created_at': place_data.get('city_created_at', ''),
                    'name': place_data['city_name'],
                    'postal_code': place_data.get('city_postal_code', '')
                }
            
            places_with_stats.append(place)

        # Sort by trip count according to order parameter
        reverse_order = order == 'desc'
        places_with_stats.sort(key=lambda x: x['trip_count'], reverse=reverse_order)

        # Calculate total count for pagination
        total_count = len(places_with_stats)
        page_count = (total_count + size - 1) // size if total_count > 0 else 1

        # Apply pagination
        paginated_places = places_with_stats[offset:offset + size]

        # Format city data properly
        for place in paginated_places:
            if place.get('city'):
                city_data = place['city']
                if hasattr(city_data, '__dict__'):
                    # Convert Neo4j Node to dict
                    place['city'] = {
                        'created_at': city_data.get('created_at', ''),
                        'name': city_data.get('name', ''),
                        'postal_code': city_data.get('postal_code', '')
                    }
                elif isinstance(city_data, dict):
                    # Already a dict, ensure it has required fields
                    place['city'] = {
                        'created_at': city_data.get('created_at', ''),
                        'name': city_data.get('name', ''),
                        'postal_code': city_data.get('postal_code', '')
                    }

        # Serialize data
        schema = DashboardStatsSchema(many=True)
        serialized_data = schema.dump(paginated_places)

        # Create paging info
        paging = create_paging(offset, page, page_count, size, total_count)

        result = {
            'data': serialized_data,
            'paging': paging
        }

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error getting places statistics: {str(e)}")
        return jsonify({'error': 'Failed to get places statistics'}), 500


@blueprint.get('/statistics/places/ranking')
@jwt_required()
def get_places_ranking_statistics():
    """Get statistics about top places ordered by raw_ranking with review numbers."""
    try:
        # Validate query parameters
        schema = DashboardQuerySchema()
        try:
            args = schema.load(request.args)
        except ValidationError as e:
            return jsonify({'error': 'Invalid parameters', 'details': e.messages}), 400

        place_type = args['place_type']
        order = args['order']
        page = args['page']
        size = args['size']
        offset = (page - 1) * size

        # Build type filter for Neo4j query
        type_filter = ""
        if place_type == 'things-to-do':
            type_filter = "p:ThingToDo"
        elif place_type == 'hotels':
            type_filter = "p:Hotel"
        elif place_type == 'restaurants':
            type_filter = "p:Restaurant"
        else:
            type_filter = "p:ThingToDo OR p:Hotel OR p:Restaurant"

        order_clause = "DESC" if order == 'desc' else "ASC"

        # Get places ordered by raw_ranking from Neo4j
        neo4j_query = f"""
        MATCH (p) WHERE ({type_filter})
        OPTIONAL MATCH (p)-[:LOCATED_IN]->(c:City)
        WITH p, 
             elementId(p) AS element_id,
             CASE 
                 WHEN labels(p)[0] = 'Hotel' THEN 'HOTEL'
                 WHEN labels(p)[0] = 'Restaurant' THEN 'RESTAURANT' 
                 WHEN labels(p)[0] = 'ThingToDo' THEN 'THING_TO_DO'
                 ELSE 'UNKNOWN'
             END AS type,
             c.name AS city_name,
             c.created_at AS city_created_at,
             c.postal_code AS city_postal_code
        WHERE p.raw_ranking IS NOT NULL
        RETURN p AS place,
               element_id,
               type,
               city_name,
               city_created_at,
               city_postal_code
        ORDER BY p.raw_ranking {order_clause}
        SKIP $offset
        LIMIT $limit
        """

        neo4j_query = neo4j_query.replace("{order_clause}", order_clause)

        places_data = execute_neo4j_query(
            neo4j_query, 
            {'offset': offset, 'limit': size}
        )

        if not places_data:
            return jsonify({
                'data': [],
                'paging': create_paging(0, page, 1, size, 0)
            }), 200

        # Process place data and calculate review_number
        places_with_reviews = []
        for place_data in places_data:
            place = place_data['place']
            element_id = place_data['element_id']
            
            # Calculate review_number from rating_histogram
            rating_histogram = place.get('rating_histogram', [])
            if rating_histogram and isinstance(rating_histogram, list):
                review_number = sum(rating_histogram)
            else:
                review_number = 0
            
            place['review_number'] = review_number
            place['element_id'] = element_id
            place['type'] = place_data['type']
            
            # Add city information
            if place_data.get('city_name'):
                place['city'] = {
                    'created_at': place_data.get('city_created_at', ''),
                    'name': place_data['city_name'],
                    'postal_code': place_data.get('city_postal_code', '')
                }
            
            places_with_reviews.append(place)

        # Get total count for pagination (separate query)
        count_query = f"""
        MATCH (p) WHERE ({type_filter})
        AND p.raw_ranking IS NOT NULL
        RETURN COUNT(p) AS total_count
        """

        count_result = execute_neo4j_query(count_query, {})
        total_count = count_result[0]['total_count'] if count_result else 0
        page_count = (total_count + size - 1) // size if total_count > 0 else 1

        # Format city data properly
        for place in places_with_reviews:
            if place.get('city'):
                city_data = place['city']
                if hasattr(city_data, '__dict__'):
                    # Convert Neo4j Node to dict
                    place['city'] = {
                        'created_at': city_data.get('created_at', ''),
                        'name': city_data.get('name', ''),
                        'postal_code': city_data.get('postal_code', '')
                    }
                elif isinstance(city_data, dict):
                    # Already a dict, ensure it has required fields
                    place['city'] = {
                        'created_at': city_data.get('created_at', ''),
                        'name': city_data.get('name', ''),
                        'postal_code': city_data.get('postal_code', '')
                    }

        # Serialize data
        schema = DashboardRankingSchema(many=True)
        serialized_data = schema.dump(places_with_reviews)

        # Create paging info
        paging = create_paging(offset, page, page_count, size, total_count)

        result = {
            'data': serialized_data,
            'paging': paging
        }

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error getting places ranking statistics: {str(e)}")
        return jsonify({'error': 'Failed to get places ranking statistics'}), 500


@blueprint.get('/statistics/summary')
@jwt_required()
def get_dashboard_summary():
    """Get overall dashboard summary statistics."""
    try:
        # Get total counts
        total_optimized_trips_query = """
        SELECT COUNT(*) as total_optimized_trips
        FROM user_trips
        WHERE is_optimized = true
        """
        
        total_trips_query = """
        SELECT COUNT(*) as total_trips
        FROM user_trips
        """
        
        total_users_query = """
        SELECT COUNT(*) as total_users
        FROM users
        """
        
        avg_places_per_trip_query = """
        SELECT AVG(place_count) as avg_places_per_trip
        FROM (
            SELECT COUNT(*) as place_count
            FROM trips
            GROUP BY trip_id
        ) as trip_place_counts
        """

        total_optimized_result = db.session.execute(db.text(total_optimized_trips_query)).fetchone()
        total_trips_result = db.session.execute(db.text(total_trips_query)).fetchone()
        total_users_result = db.session.execute(db.text(total_users_query)).fetchone()
        avg_places_result = db.session.execute(db.text(avg_places_per_trip_query)).fetchone()

        summary = {
            'total_optimized_trips': total_optimized_result.total_optimized_trips if total_optimized_result else 0,
            'total_trips': total_trips_result.total_trips if total_trips_result else 0,
            'total_users': total_users_result.total_users if total_users_result else 0,
            'average_places_per_trip': round(avg_places_result.avg_places_per_trip, 2) if avg_places_result and avg_places_result.avg_places_per_trip else 0
        }

        return jsonify(summary), 200

    except Exception as e:
        logger.error(f"Error getting dashboard summary: {str(e)}")
        return jsonify({'error': 'Failed to get dashboard summary'}), 500


@blueprint.get('/statistics/users/monthly')
@jwt_required()
def get_monthly_user_statistics():
    """Get statistics about the number of users created each month this year."""
    try:
        from datetime import datetime
        import json
        from flask import Response
        
        current_year = datetime.now().year
        
        # Query to get user creation statistics by month for current year
        monthly_stats_query = """
        SELECT 
            EXTRACT(MONTH FROM created_at) as month_number,
            COUNT(*) as user_count
        FROM users 
        WHERE EXTRACT(YEAR FROM created_at) = :current_year
        GROUP BY EXTRACT(MONTH FROM created_at)
        ORDER BY month_number
        """
        
        # Get total users count
        total_users_query = """
        SELECT COUNT(*) as total_users
        FROM users
        """
        
        monthly_result = db.session.execute(
            db.text(monthly_stats_query), 
            {'current_year': current_year}
        )
        
        total_result = db.session.execute(db.text(total_users_query))
        
        # Month names in chronological order
        months_in_order = [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]
        
        # Month names mapping
        month_names = {
            1: "January", 2: "February", 3: "March", 4: "April",
            5: "May", 6: "June", 7: "July", 8: "August", 
            9: "September", 10: "October", 11: "November", 12: "December"
        }
        
        # Create dictionary with actual data
        monthly_data = {}
        for row in monthly_result:
            month_name = month_names[int(row.month_number)]
            monthly_data[month_name] = row.user_count
        
        # Build response dictionary in correct order
        monthly_stats = {}
        
        # Add months in chronological order
        for month_name in months_in_order:
            monthly_stats[month_name] = monthly_data.get(month_name, 0)
        
        # Get total users
        total_users = total_result.fetchone().total_users if total_result else 0
        
        # Add total to response
        monthly_stats['total_user'] = total_users
        
        # Return JSON response with preserved order
        response_json = json.dumps(monthly_stats, separators=(',', ':'))
        return Response(response_json, content_type='application/json'), 200

    except Exception as e:
        logger.error(f"Error getting monthly user statistics: {str(e)}")
        return jsonify({'error': 'Failed to get monthly user statistics'}), 500 