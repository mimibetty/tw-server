import logging
import uuid

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy.exc import SQLAlchemyError

from app.models import db, Trip, User, UserTrip

logger = logging.getLogger(__name__)
blueprint = Blueprint('trips', __name__, url_prefix='/trips')


# ===== User Trip Endpoints =====

@blueprint.post('/')
@jwt_required()
def create_user_trip():
    """Create a new user trip."""
    user_id = get_jwt_identity()
    data = request.json

    if not data or 'name' not in data:
        return jsonify({'error': 'Name is required'}), 400

    try:
        # Create new user trip
        user_trip = UserTrip(
            user_id=user_id,
            name=data['name']
        )
        
        db.session.add(user_trip)
        db.session.commit()
        
        return jsonify({
            'id': str(user_trip.id),
            'user_id': str(user_trip.user_id),
            'name': user_trip.name,
            'created_at': user_trip.created_at.isoformat(),
            'updated_at': user_trip.updated_at.isoformat()
        }), 201
        
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f"Error creating user trip: {str(e)}")
        return jsonify({'error': 'Failed to create user trip'}), 500


@blueprint.get('/')
@jwt_required()
def get_user_trips():
    """Get all user trips for the authenticated user."""
    user_id = get_jwt_identity()
    
    try:
        user_trips = UserTrip.query.filter_by(user_id=user_id).all()
        
        result = []
        for trip in user_trips:
            result.append({
                'id': str(trip.id),
                'name': trip.name,
                'created_at': trip.created_at.isoformat(),
                'updated_at': trip.updated_at.isoformat(),
                'place_count': len(trip.trips)
            })
            
        return jsonify(result), 200
        
    except SQLAlchemyError as e:
        logger.error(f"Error fetching user trips: {str(e)}")
        return jsonify({'error': 'Failed to fetch user trips'}), 500



















# not yet implemented



@blueprint.get('/<uuid:trip_id>')
@jwt_required()
def get_user_trip(trip_id):
    """Get a specific user trip by ID."""
    user_id = get_jwt_identity()
    
    try:
        user_trip = UserTrip.query.filter_by(id=trip_id, user_id=user_id).first()
        
        if not user_trip:
            return jsonify({'error': 'Trip not found'}), 404
            
        result = {
            'id': str(user_trip.id),
            'name': user_trip.name,
            'created_at': user_trip.created_at.isoformat(),
            'updated_at': user_trip.updated_at.isoformat()
        }
            
        return jsonify(result), 200
        
    except SQLAlchemyError as e:
        logger.error(f"Error fetching user trip: {str(e)}")
        return jsonify({'error': 'Failed to fetch user trip'}), 500


@blueprint.put('/<uuid:trip_id>')
@jwt_required()
def update_user_trip(trip_id):
    """Update a user trip."""
    user_id = get_jwt_identity()
    data = request.json
    
    if not data or 'name' not in data:
        return jsonify({'error': 'Name is required'}), 400
    
    try:
        user_trip = UserTrip.query.filter_by(id=trip_id, user_id=user_id).first()
        
        if not user_trip:
            return jsonify({'error': 'Trip not found'}), 404
            
        user_trip.name = data['name']
        db.session.commit()
        
        return jsonify({
            'id': str(user_trip.id),
            'name': user_trip.name,
            'created_at': user_trip.created_at.isoformat(),
            'updated_at': user_trip.updated_at.isoformat()
        }), 200
        
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f"Error updating user trip: {str(e)}")
        return jsonify({'error': 'Failed to update user trip'}), 500


@blueprint.delete('/<uuid:trip_id>')
@jwt_required()
def delete_user_trip(trip_id):
    """Delete a user trip."""
    user_id = get_jwt_identity()
    
    try:
        user_trip = UserTrip.query.filter_by(id=trip_id, user_id=user_id).first()
        
        if not user_trip:
            return jsonify({'error': 'Trip not found'}), 404
            
        # Delete all places in this trip first
        Trip.query.filter_by(trip_id=trip_id).delete()
        
        # Then delete the trip itself
        db.session.delete(user_trip)
        db.session.commit()
        
        return jsonify({'message': 'Trip deleted successfully'}), 200
        
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f"Error deleting user trip: {str(e)}")
        return jsonify({'error': 'Failed to delete user trip'}), 500


# ===== Trip Places Endpoints =====

@blueprint.post('/<uuid:trip_id>/places')
@jwt_required()
def add_place_to_trip(trip_id):
    """Add a place to a user trip."""
    user_id = get_jwt_identity()
    data = request.json
    
    if not data or 'place_id' not in data:
        return jsonify({'error': 'Place ID is required'}), 400
    
    try:
        # Verify trip exists and belongs to user
        user_trip = UserTrip.query.filter_by(id=trip_id, user_id=user_id).first()
        
        if not user_trip:
            return jsonify({'error': 'Trip not found'}), 404
            
        # Get the next order number
        max_order = db.session.query(db.func.max(Trip.order)).filter_by(trip_id=trip_id).scalar() or 0
        next_order = max_order + 1
        
        # Create new trip place
        trip_place = Trip(
            trip_id=trip_id,
            place_id=data['place_id'],
            order=next_order
        )
        
        db.session.add(trip_place)
        db.session.commit()
        
        return jsonify({
            'id': str(trip_place.id),
            'trip_id': str(trip_place.trip_id),
            'place_id': trip_place.place_id,
            'order': trip_place.order,
            'created_at': trip_place.created_at.isoformat(),
            'updated_at': trip_place.updated_at.isoformat()
        }), 201
        
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f"Error adding place to trip: {str(e)}")
        return jsonify({'error': 'Failed to add place to trip'}), 500


@blueprint.get('/<uuid:trip_id>/places')
@jwt_required()
def get_trip_places(trip_id):
    """Get all places in a user trip."""
    user_id = get_jwt_identity()
    
    try:
        # Verify trip exists and belongs to user
        user_trip = UserTrip.query.filter_by(id=trip_id, user_id=user_id).first()
        
        if not user_trip:
            return jsonify({'error': 'Trip not found'}), 404
            
        # Get places in trip, ordered by order
        places = Trip.query.filter_by(trip_id=trip_id).order_by(Trip.order).all()
        
        result = []
        for place in places:
            result.append({
                'id': str(place.id),
                'place_id': place.place_id,
                'order': place.order,
                'created_at': place.created_at.isoformat(),
                'updated_at': place.updated_at.isoformat()
            })
            
        return jsonify(result), 200
        
    except SQLAlchemyError as e:
        logger.error(f"Error fetching trip places: {str(e)}")
        return jsonify({'error': 'Failed to fetch trip places'}), 500


@blueprint.put('/<uuid:trip_id>/places/<uuid:place_id>')
@jwt_required()
def update_trip_place(trip_id, place_id):
    """Update a place in a trip (currently only order can be updated)."""
    user_id = get_jwt_identity()
    data = request.json
    
    if not data or 'order' not in data:
        return jsonify({'error': 'Order is required'}), 400
    
    try:
        # Verify trip exists and belongs to user
        user_trip = UserTrip.query.filter_by(id=trip_id, user_id=user_id).first()
        
        if not user_trip:
            return jsonify({'error': 'Trip not found'}), 404
            
        # Get the place
        place = Trip.query.filter_by(id=place_id, trip_id=trip_id).first()
        
        if not place:
            return jsonify({'error': 'Place not found in trip'}), 404
            
        # Update order
        place.order = data['order']
        db.session.commit()
        
        return jsonify({
            'id': str(place.id),
            'trip_id': str(place.trip_id),
            'place_id': place.place_id,
            'order': place.order,
            'created_at': place.created_at.isoformat(),
            'updated_at': place.updated_at.isoformat()
        }), 200
        
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f"Error updating trip place: {str(e)}")
        return jsonify({'error': 'Failed to update trip place'}), 500


@blueprint.delete('/<uuid:trip_id>/places/<uuid:place_id>')
@jwt_required()
def delete_trip_place(trip_id, place_id):
    """Delete a place from a trip."""
    user_id = get_jwt_identity()
    
    try:
        # Verify trip exists and belongs to user
        user_trip = UserTrip.query.filter_by(id=trip_id, user_id=user_id).first()
        
        if not user_trip:
            return jsonify({'error': 'Trip not found'}), 404
            
        # Get the place
        place = Trip.query.filter_by(id=place_id, trip_id=trip_id).first()
        
        if not place:
            return jsonify({'error': 'Place not found in trip'}), 404
            
        # Delete the place
        db.session.delete(place)
        
        # Reorder remaining places to keep order consistent
        remaining_places = Trip.query.filter_by(trip_id=trip_id).order_by(Trip.order).all()
        for i, rp in enumerate(remaining_places, 1):
            rp.order = i
            
        db.session.commit()
        
        return jsonify({'message': 'Place removed from trip successfully'}), 200
        
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f"Error deleting trip place: {str(e)}")
        return jsonify({'error': 'Failed to delete trip place'}), 500


@blueprint.post('/<uuid:trip_id>/places/reorder')
@jwt_required()
def reorder_trip_places(trip_id):
    """Reorder places in a trip."""
    user_id = get_jwt_identity()
    data = request.json
    
    if not data or 'places' not in data or not isinstance(data['places'], list):
        return jsonify({'error': 'Places array is required'}), 400
    
    try:
        # Verify trip exists and belongs to user
        user_trip = UserTrip.query.filter_by(id=trip_id, user_id=user_id).first()
        
        if not user_trip:
            return jsonify({'error': 'Trip not found'}), 404
            
        # Create a mapping of place_id to new order
        place_order_map = {place['id']: i+1 for i, place in enumerate(data['places'])}
        
        # Update orders
        for place_id, new_order in place_order_map.items():
            place = Trip.query.filter_by(id=uuid.UUID(place_id), trip_id=trip_id).first()
            if place:
                place.order = new_order
        
        db.session.commit()
        
        # Get updated places
        updated_places = Trip.query.filter_by(trip_id=trip_id).order_by(Trip.order).all()
        
        result = []
        for place in updated_places:
            result.append({
                'id': str(place.id),
                'place_id': place.place_id,
                'order': place.order
            })
            
        return jsonify(result), 200
        
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f"Error reordering trip places: {str(e)}")
        return jsonify({'error': 'Failed to reorder trip places'}), 500 