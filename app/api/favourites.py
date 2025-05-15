import logging
from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy.exc import SQLAlchemyError
from marshmallow import fields

from app.models import db, UserFavourite
from app.extensions import CamelCaseSchema
from app.utils import execute_neo4j_query

logger = logging.getLogger(__name__)
blueprint = Blueprint('favourites', __name__, url_prefix='/favourites')

# Schema for favourite response
class FavouriteSchema(CamelCaseSchema):
    id = fields.String(dump_only=True)
    place_id = fields.String(required=True)
    user_id = fields.String(dump_only=True)
    created_at = fields.String(dump_only=True)
    updated_at = fields.String(dump_only=True)

# Schema for place details in favourites
class FavouritePlaceSchema(CamelCaseSchema):
    created_at = fields.String(dump_only=True)
    element_id = fields.String(dump_only=True)
    city = fields.Dict(dump_only=True)
    email = fields.String(dump_only=True)
    image = fields.String(dump_only=True)
    latitude = fields.Float(dump_only=True)
    longitude = fields.Float(dump_only=True)
    name = fields.String(dump_only=True)
    rating = fields.Float(dump_only=True)
    rating_histogram = fields.List(fields.Integer(), dump_only=True)
    raw_ranking = fields.Float(dump_only=True)
    street = fields.String(dump_only=True)
    type = fields.String(dump_only=True)
    favourite_id = fields.String(dump_only=True)


@blueprint.get('/')
@jwt_required()
def get_favourites():
    """Get all user's favourites."""
    user_id = get_jwt_identity()
    include_details = request.args.get('include_details', 'false').lower() == 'true'
    
    try:
        # Get favourites sorted by created_at in descending order (newest first)
        favourites = UserFavourite.query.filter_by(user_id=user_id).order_by(UserFavourite.created_at.desc()).all()
        
        if not include_details:
            # Return just the favourite IDs
            return jsonify(FavouriteSchema(many=True).dump(favourites)), 200
        
        # Get place details for each favourite
        result = []
        for favourite in favourites:
            place_info = get_place_details_from_neo4j(favourite.place_id)
            
            if place_info:
                # Add favourite ID and preserve original place created_at
                place_created_at = place_info.get('created_at')
                
                # Update with favourite info
                place_info['favourite_id'] = str(favourite.id)
                place_info['created_at'] = favourite.created_at.isoformat()
                
                # If place has its own created_at, store it under a different name
                if place_created_at:
                    place_info['place_created_at'] = place_created_at
                    
                result.append(place_info)
        
        return jsonify(FavouritePlaceSchema(many=True).dump(result)), 200
        
    except SQLAlchemyError as e:
        logger.error(f"Error fetching favourites: {str(e)}")
        return jsonify({'error': 'Failed to fetch favourites'}), 500


@blueprint.get('/<string:place_id>/status')
@jwt_required()
def check_favourite_status(place_id):
    """Check if a place is in user's favourites."""
    user_id = get_jwt_identity()
    
    try:
        favourite = UserFavourite.query.filter_by(
            user_id=user_id, 
            place_id=place_id
        ).first()
        
        return jsonify({
            'is_favourite': favourite is not None,
            'favourite': FavouriteSchema().dump(favourite) if favourite else None
        }), 200
        
    except SQLAlchemyError as e:
        logger.error(f"Error checking favourite status: {str(e)}")
        return jsonify({'error': 'Failed to check favourite status'}), 500


@blueprint.post('/toggle')
@jwt_required()
def toggle_favourite():
    """Toggle a place's favourite status - add if not in favourites, remove if already in favourites."""
    user_id = get_jwt_identity()
    data = request.json
    
    if not data or 'place_id' not in data:
        return jsonify({'error': 'Place ID is required'}), 400
    
    place_id = data['place_id']
    
    try:
        # Check if the place already exists in favourites
        existing_favourite = UserFavourite.query.filter_by(
            user_id=user_id, 
            place_id=place_id
        ).first()
        
        if existing_favourite:
            # Place exists in favourites - remove it
            db.session.delete(existing_favourite)
            db.session.commit()
            
            return jsonify({
                'status': 'removed',
                'message': 'Place removed from favourites successfully',
                'is_favourite': False
            }), 200
        else:
            # Place not in favourites - add it
            favourite = UserFavourite(
                user_id=user_id,
                place_id=place_id
            )
            
            db.session.add(favourite)
            db.session.commit()
            
            return jsonify({
                'status': 'added',
                'message': 'Place added to favourites successfully',
                'is_favourite': True,
                'favourite': FavouriteSchema().dump(favourite)
            }), 200
        
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f"Error toggling favourite status: {str(e)}")
        return jsonify({'error': 'Failed to toggle favourite status'}), 500


@blueprint.get('/details')
@jwt_required()
def get_favourites_with_details():
    """Get all user's favourites with detailed place information."""
    user_id = get_jwt_identity()
    
    try:
        # Get all favourites for the user, ordered by created_at in descending order (newest first)
        favourites = UserFavourite.query.filter_by(user_id=user_id).order_by(UserFavourite.created_at.desc()).all()
        
        if not favourites:
            # Return empty list if user has no favourites
            return jsonify([]), 200
        
        # Get place details from Neo4j for each favourite
        place_details = []
        
        for favourite in favourites:
            # Get place details from Neo4j
            place_info = get_place_details_from_neo4j(favourite.place_id)
            
            if place_info:
                # Add favourite ID and use favourite's created_at
                place_info['favourite_id'] = str(favourite.id)
                place_info['created_at'] = favourite.created_at.isoformat()
                place_details.append(place_info)
        
        return jsonify(FavouritePlaceSchema(many=True).dump(place_details)), 200
        
    except SQLAlchemyError as e:
        logger.error(f"Error fetching favourite details: {str(e)}")
        return jsonify({'error': 'Failed to fetch favourite details'}), 500


def get_place_details_from_neo4j(place_id):
    """Get place details from Neo4j regardless of place type."""
    # First, try to find the place by elementId
    result = execute_neo4j_query(
        """
        MATCH (p)
        WHERE elementId(p) = $place_id
        OPTIONAL MATCH (p)-[:LOCATED_IN]->(c:City)
        RETURN p, elementId(p) AS element_id, labels(p) AS types, c
        """,
        {'place_id': place_id}
    )
    
    if not result:
        return None
    
    # Extract the place data and determine its type
    place_data = result[0]['p']
    place_data['element_id'] = result[0]['element_id']
    place_types = result[0]['types']
    city_data = result[0]['c']
    
    # Add city data if available, without created_at
    if city_data:
        place_data['city'] = {
            'postal_code': city_data.get('postal_code', ''),
            'name': city_data.get('name', '')
        }
    
    # Determine place type and standardize it
    place_type = None
    standardized_type = "UNKNOWN"
    for type_label in place_types:
        if type_label == 'Hotel':
            place_type = type_label
            standardized_type = "HOTEL"
            break
        elif type_label == 'Restaurant':
            place_type = type_label
            standardized_type = "RESTAURANT"
            break
        elif type_label == 'ThingToDo':
            place_type = type_label
            standardized_type = "THING-TO-DO"
            break
    
    if not place_type:
        # Default to the 'type' field if available
        place_type = place_data.get('type', 'Unknown')
    
    # Ensure 'type' field is standardized
    place_data['type'] = standardized_type
    
    # No need to fetch price_levels as we're not including them in the response
    
    # Ensure all fields match the expected format in ShortSchemas
    # Provide default values for any missing fields
    if 'rating_histogram' not in place_data or not place_data['rating_histogram']:
        place_data['rating_histogram'] = [0, 0, 0, 0, 0]
    
    if 'rating' not in place_data or place_data['rating'] is None:
        # Calculate rating from histogram if available
        rh = place_data.get('rating_histogram', [])
        if rh and isinstance(rh, list) and len(rh) == 5:
            total = sum(rh)
            if total > 0:
                rating = sum((i + 1) * rh[i] for i in range(5)) / total
                place_data['rating'] = round(rating, 1)
            else:
                place_data['rating'] = 0
        else:
            place_data['rating'] = 0
    
    # Convert camelCase keys to snake_case if needed
    camel_to_snake_mappings = {
        'ratingHistogram': 'rating_histogram',
        'rawRanking': 'raw_ranking',
        'elementId': 'element_id',
        'createdAt': 'created_at',
        'updatedAt': 'updated_at'
    }
    
    for camel, snake in camel_to_snake_mappings.items():
        if camel in place_data and snake not in place_data:
            place_data[snake] = place_data[camel]
    
    # Filter fields to only include those from short schemas
    common_fields = [
        'created_at', 'element_id', 'city', 'email', 'image', 
        'latitude', 'longitude', 'name', 'rating', 'rating_histogram',
        'raw_ranking', 'street', 'type'
    ]
    
    # Create filtered dict with only fields from short schemas
    filtered_data = {k: place_data.get(k) for k in common_fields if k in place_data}
    
    return filtered_data 