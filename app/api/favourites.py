import logging

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from marshmallow import fields
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import ma
from app.models import UserFavourite, db
from app.utils import execute_neo4j_query, update_user_preference_cache

logger = logging.getLogger(__name__)
blueprint = Blueprint('favourites', __name__, url_prefix='/favourites')


class CitySchema(ma.Schema):
    name = fields.String(dump_only=True)
    postal_code = fields.String(dump_only=True)


class ShortPlaceSchema(ma.Schema):
    created_at = fields.String(dump_only=True)
    element_id = fields.String(dump_only=True)
    city = fields.Nested(CitySchema)
    email = fields.Email(allow_none=True)
    image = fields.String(dump_only=True)
    is_favorite = fields.Boolean(dump_only=True)
    latitude = fields.Float(dump_only=True)
    longitude = fields.Float(dump_only=True)
    name = fields.String(dump_only=True)
    rating = fields.Float(allow_none=True)
    rating_histogram = fields.List(fields.Integer(), default=list)
    raw_ranking = fields.Float(load_only=True)
    street = fields.String(dump_only=True, allow_none=True)
    type = fields.String(dump_only=True)


@blueprint.get('/')
@jwt_required()
def get_favourites():
    user_id = get_jwt_identity()
    query = 'SELECT place_id FROM user_favourites WHERE user_id = :user_id'

    result = db.session.execute(db.text(query), {'user_id': user_id})
    place_ids = [row.place_id for row in result]

    # If no favourites, return empty list
    if not place_ids:
        return jsonify([]), 200

    # Query Neo4j for place details
    neo4j_query = """
    UNWIND $place_ids AS pid
    MATCH (p) WHERE elementId(p) = pid
    OPTIONAL MATCH (p)-[:LOCATED_IN]->(c:City)
    RETURN p AS place, elementId(p) AS element_id, c AS city
    """
    neo4j_result = execute_neo4j_query(neo4j_query, {'place_ids': place_ids})

    # If Neo4j returns None, treat as empty list
    if not neo4j_result:
        neo4j_result = []

    # Prepare data for serialization
    places = []
    for record in neo4j_result:
        place = record['place']
        place['element_id'] = record['element_id']
        place['is_favorite'] = True
        if record.get('city'):
            place['city'] = record['city']
        places.append(place)

    return jsonify(ShortPlaceSchema(many=True).dump(places)), 200


class RequestSchema(ma.Schema):
    place_id = fields.String(required=True, load_only=True)


@blueprint.post('/')
@jwt_required()
def add_favourite():
    """Add a place to the current user's favourites."""
    user_id = get_jwt_identity()
    place_id = request.get_json().get('place_id')
    if not place_id:
        return jsonify({'error': 'place_id is required'}), 400

    # Check if already exists
    existing_favourite = (
        db.session.query(UserFavourite)
        .filter_by(user_id=user_id, place_id=place_id)
        .first()
    )
    if existing_favourite:
        return {'error': 'Place already in favourites'}, 400

    favourite = UserFavourite(user_id=user_id, place_id=place_id)
    db.session.add(favourite)
    db.session.commit()

    # Update user recommendation cache
    update_user_preference_cache(user_id)

    return {'success': True}, 201


@blueprint.delete('/<string:place_id>')
@jwt_required()
def delete_favourite(place_id):
    """Remove a place from the current user's favourites."""
    user_id = get_jwt_identity()

    try:
        # Find and delete the favourite
        favourite = (
            db.session.query(UserFavourite)
            .filter_by(user_id=user_id, place_id=place_id)
            .first()
        )

        if not favourite:
            return jsonify({'error': 'Place not found in favourites'}), 404

        db.session.delete(favourite)
        db.session.commit()

        # Update user recommendation cache
        update_user_preference_cache(user_id)

        return jsonify(
            {'message': 'Place removed from favourites successfully'}
        ), 200

    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f'Error removing place from favourites: {str(e)}')
        return jsonify({'error': 'Failed to remove place from favourites'}), 500
