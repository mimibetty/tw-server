import logging
from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm import joinedload
import json

from app.models import UserReview, User, db
from app.utils import update_place_rating_histogram, check_place_exists, get_redis, update_user_preference_cache,create_paging

logger = logging.getLogger(__name__)
blueprint = Blueprint('reviews', __name__, url_prefix='/reviews')

def get_reviews_cache_key(place_id: str) -> str:
    """Generate Redis cache key for place reviews."""
    return f"reviews:{place_id}"

def get_place_cache_key(place_type: str, place_id: str) -> str:
    """Generate Redis cache key for place based on type."""
    place_type = place_type.lower()
    if place_type == 'thing-to-do':
        return f"things-to-do:{place_id}"
    return f"{place_type}s:{place_id}"

def cache_reviews(place_id: str, reviews: list):
    """Cache reviews in Redis."""
    try:
        redis = get_redis()
        cache_key = get_reviews_cache_key(place_id)
        # Cache for 6 hours (21600 seconds)
        redis.setex(cache_key, 21600, json.dumps(reviews))
    except Exception as e:
        logger.warning('Redis is not available to set data: %s', e)

def get_cached_reviews(place_id: str) -> list:
    """Get cached reviews from Redis."""
    try:
        redis = get_redis()
        cache_key = get_reviews_cache_key(place_id)
        cached_data = redis.get(cache_key)
        return json.loads(cached_data) if cached_data else None
    except Exception as e:
        logger.warning('Redis is not available to get data: %s', e)
        return None

def invalidate_caches(place_id: str):
    """Invalidate both reviews and place caches."""
    try:
        redis = get_redis()
        # Invalidate reviews cache
        reviews_cache_key = get_reviews_cache_key(place_id)
        
        # Invalidate place caches for all types
        place_cache_keys = [
            f'hotels:{place_id}',
            f'restaurants:{place_id}',
            f'things-to-do:{place_id}'
        ]
        
        # Delete review cache and all place caches
        redis.delete(reviews_cache_key, *place_cache_keys)
        
        # Also invalidate list caches for all place types
        patterns = [
            'hotels:*',
            'restaurants:*',
            'things-to-do:*'
        ]
        
        for pattern in patterns:
            keys_to_delete = redis.keys(pattern)
            if keys_to_delete:
                redis.delete(*keys_to_delete)
                
        # Invalidate any cached place data that might include ratings
        rating_pattern = f'*:{place_id}'
        rating_keys = redis.keys(rating_pattern)
        if rating_keys:
            redis.delete(*rating_keys)
    except Exception as e:
        logger.warning('Redis is not available to delete data: %s', e)

@blueprint.post('/<string:place_id>')
@jwt_required()
def create_review(place_id):
    """Create a new review for a place."""
    user_id = get_jwt_identity()
    
    # Parse JSON with error handling
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body must be valid JSON'}), 400
    except Exception as e:
        logger.error(f'JSON parsing error: {str(e)}')
        return jsonify({'error': 'Invalid JSON format'}), 400

    # Validate required fields
    if 'rating' not in data or 'review' not in data:
        return jsonify({'error': 'Rating and review are required'}), 400

    # Validate rating range
    try:
        rating = int(data['rating'])
        if rating < 1 or rating > 5:
            return jsonify({'error': 'Rating must be between 1 and 5'}), 400
    except (ValueError, TypeError):
        return jsonify({'error': 'Rating must be a valid integer between 1 and 5'}), 400

    # Check if place exists in Neo4j
    if not check_place_exists(place_id):
        return jsonify({'error': 'Place not found'}), 404

    # Check if user exists
    user = User.query.filter_by(id=user_id).first()
    if not user:
        return jsonify({'error': 'User not found. Please log in again.'}), 401

    try:
        # Check if user already reviewed this place
        existing_review = UserReview.query.filter_by(
            user_id=user_id, place_id=place_id
        ).first()

        if existing_review:
            return jsonify({'error': 'You have already reviewed this place'}), 400

        # Create new review
        review = UserReview(
            user_id=user_id,
            place_id=place_id,
            rating=rating,
            review=data['review']
        )

        db.session.add(review)
        db.session.commit()

        # Update place rating histogram
        update_place_rating_histogram(place_id, new_rating=rating)

        # Invalidate caches
        invalidate_caches(place_id)

        # Update user recommendation cache
        update_user_preference_cache(user_id)

        return jsonify({
            'id': str(review.id),
            'user': {
                'full_name': user.full_name,
                'avatar': user.avatar
            },
            'place_id': review.place_id,
            'rating': review.rating,
            'review': review.review,
            'created_at': review.created_at.isoformat(),
            'updated_at': review.updated_at.isoformat()
        }), 201

    except IntegrityError as e:
        db.session.rollback()
        logger.error(f'Integrity error creating review: {str(e)}')
        if 'user_reviews_user_id_fkey' in str(e):
            return jsonify({'error': 'User not found. Please log in again.'}), 401
        elif 'unique_user_review' in str(e):
            return jsonify({'error': 'You have already reviewed this place'}), 400
        else:
            return jsonify({'error': 'Failed to create review due to data constraint'}), 400
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f'Error creating review: {str(e)}')
        return jsonify({'error': 'Failed to create review'}), 500

@blueprint.get('/<string:place_id>')
def get_place_reviews(place_id):
    """Get all reviews for a place with pagination and sorting."""
    # Get pagination parameters
    page = request.args.get('page', default=1, type=int)
    size = request.args.get('size', default=10, type=int)
    
    # Get sorting parameters
    sort_by = request.args.get('sort_by', default='created_at', type=str)
    order = request.args.get('order', default='desc', type=str)
    
    # Validate pagination parameters
    if page < 1:
        return jsonify({'error': 'Page must be greater than 0'}), 400
    if size < 1 or size > 100:
        return jsonify({'error': 'Size must be between 1 and 100'}), 400
    
    # Validate sorting parameters
    valid_sort_fields = ['rating', 'updated_at', 'created_at']
    valid_orders = ['asc', 'desc']
    
    if sort_by not in valid_sort_fields:
        return jsonify({'error': f'Invalid sort_by. Must be one of: {", ".join(valid_sort_fields)}'}), 400
    
    if order not in valid_orders:
        return jsonify({'error': f'Invalid order. Must be one of: {", ".join(valid_orders)}'}), 400

    offset = (page - 1) * size

    # Check if place exists in Neo4j
    if not check_place_exists(place_id):
        return jsonify({'error': 'Place not found'}), 404

    # Include sorting parameters in cache key
    cache_key = f'reviews:{place_id}:page={page}:size={size}:sort={sort_by}:order={order}'
    cached_reviews = get_cached_reviews(cache_key)
    if cached_reviews is not None:
        return jsonify(cached_reviews), 200

    try:
        # Get total count for pagination
        total_count = db.session.query(UserReview).filter(
            UserReview.place_id == place_id
        ).count()

        # Build the query with sorting
        query = db.session.query(UserReview, User).join(
            User, UserReview.user_id == User.id
        ).filter(
            UserReview.place_id == place_id
        )
        
        # Apply sorting
        if sort_by == 'rating':
            sort_column = UserReview.rating
        elif sort_by == 'updated_at':
            sort_column = UserReview.updated_at
        else:  # created_at (default)
            sort_column = UserReview.created_at
        
        if order == 'asc':
            query = query.order_by(sort_column.asc())
        else:  # desc (default)
            query = query.order_by(sort_column.desc())
        
        # Apply pagination
        reviews = query.offset(offset).limit(size).all()
        
        reviews_data = [{
            'id': str(review.id),
            'user': {
                'full_name': user.full_name,
                'avatar': user.avatar
            },
            'place_id': review.place_id,
            'rating': review.rating,
            'review': review.review,
            'created_at': review.created_at.isoformat(),
            'updated_at': review.updated_at.isoformat()
        } for review, user in reviews]

        # Create paginated response
        response = create_paging(
            data=reviews_data,
            page=page,
            size=size,
            offset=offset,
            total_count=total_count
        )

        # Cache the paginated response
        cache_reviews(cache_key, response)
        
        return jsonify(response), 200

    except SQLAlchemyError as e:
        logger.error(f'Error fetching reviews: {str(e)}')
        return jsonify({'error': 'Failed to fetch reviews'}), 500

@blueprint.patch('/<string:place_id>')
@jwt_required()
def update_review(place_id):
    """Update a review for a place (partial update)."""
    user_id = get_jwt_identity()
    
    # Parse JSON with error handling
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body must be valid JSON'}), 400
    except Exception as e:
        logger.error(f'JSON parsing error: {str(e)}')
        return jsonify({'error': 'Invalid JSON format'}), 400

    # For PATCH, at least one field should be provided
    if 'rating' not in data and 'review' not in data:
        return jsonify({'error': 'At least one field (rating or review) must be provided'}), 400

    # Validate rating if provided
    if 'rating' in data:
        try:
            rating = int(data['rating'])
            if rating < 1 or rating > 5:
                return jsonify({'error': 'Rating must be between 1 and 5'}), 400
        except (ValueError, TypeError):
            return jsonify({'error': 'Rating must be a valid integer between 1 and 5'}), 400

    # Check if place exists in Neo4j
    if not check_place_exists(place_id):
        return jsonify({'error': 'Place not found'}), 404

    try:
        review = UserReview.query.options(joinedload(UserReview.user)).filter_by(
            user_id=user_id, place_id=place_id
        ).first()

        if not review:
            return jsonify({'error': 'Review not found'}), 404

        # Store old rating for histogram update
        old_rating = review.rating

        # Update only provided fields
        if 'rating' in data:
            review.rating = rating
        if 'review' in data:
            review.review = data['review']

        db.session.commit()

        # Update place rating histogram only if rating changed
        if 'rating' in data and old_rating != review.rating:
            update_place_rating_histogram(
                place_id, 
                old_rating=old_rating, 
                new_rating=review.rating
            )

        # Invalidate caches
        invalidate_caches(place_id)

        # Update user recommendation cache
        update_user_preference_cache(user_id)

        return jsonify({
            'id': str(review.id),
            'user': {
                'full_name': review.user.full_name,
                'avatar': review.user.avatar
            },
            'place_id': review.place_id,
            'rating': review.rating,
            'review': review.review,
            'created_at': review.created_at.isoformat(),
            'updated_at': review.updated_at.isoformat()
        }), 200

    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f'Error updating review: {str(e)}')
        return jsonify({'error': 'Failed to update review'}), 500

@blueprint.delete('/<string:place_id>')
@jwt_required()
def delete_review(place_id):
    """Delete a review for a place."""
    user_id = get_jwt_identity()

    # Check if place exists in Neo4j
    if not check_place_exists(place_id):
        return jsonify({'error': 'Place not found'}), 404

    try:
        review = UserReview.query.filter_by(
            user_id=user_id, place_id=place_id
        ).first()

        if not review:
            return jsonify({'error': 'Review not found'}), 404

        # Store rating for histogram update
        old_rating = review.rating

        # Delete review
        db.session.delete(review)
        db.session.commit()

        # Update place rating histogram
        update_place_rating_histogram(place_id, old_rating=old_rating)

        # Invalidate caches
        invalidate_caches(place_id)

        # Update user recommendation cache
        update_user_preference_cache(user_id)

        return jsonify({'message': 'Review deleted successfully'}), 200

    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f'Error deleting review: {str(e)}')
        return jsonify({'error': 'Failed to delete review'}), 500 