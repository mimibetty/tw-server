import logging
from flask import Blueprint, jsonify
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy.exc import SQLAlchemyError

from app.models import UserFavourite, UserReview, db
from app.utils import execute_neo4j_query

logger = logging.getLogger(__name__)
blueprint = Blueprint('recommendations', __name__, url_prefix='/recommendations')

def calculate_similarity_score(place1, place2):
    """Calculate similarity score between two places based on their attributes."""
    score = 0.0
    
    # Compare subcategories (50% weight)
    place1_cats = set(place1.get('subcategories', []))
    place2_cats = set(place2.get('subcategories', []))
    if place1_cats and place2_cats:
        cat_similarity = len(place1_cats.intersection(place2_cats)) / len(place1_cats.union(place2_cats))
        score += cat_similarity * 0.5
    
    # Compare subtypes (50% weight)
    place1_types = set(place1.get('subtypes', []))
    place2_types = set(place2.get('subtypes', []))
    if place1_types and place2_types:
        type_similarity = len(place1_types.intersection(place2_types)) / len(place1_types.union(place2_types))
        score += type_similarity * 0.5
    
    return score

@blueprint.get('/')
@jwt_required()
def get_recommendations():
    """Get personalized thing-to-do recommendations based on user favorites and ratings."""
    user_id = get_jwt_identity()
    print("user_id", user_id)

    try:
        # Get user's favorite places and rated places
        favorites = UserFavourite.query.filter_by(user_id=user_id).all()
        user_ratings = UserReview.query.filter_by(user_id=user_id).all()
        
        # Combine favorite and rated place IDs
        user_place_ids = set()
        user_place_ids.update(fav.place_id for fav in favorites)
        user_place_ids.update(rating.place_id for rating in user_ratings)
        
        if not user_place_ids:
            # If no favorites or ratings, return popular things-to-do
            return get_popular_things_to_do()
        
        # Get details of user's places from Neo4j
        user_places = []
        
        # Batch query Neo4j for user's places
        results = execute_neo4j_query(
            """
            MATCH (p:ThingToDo)
            WHERE elementId(p) IN $place_ids
            RETURN p, elementId(p) AS element_id, labels(p) AS types
            """,
            {'place_ids': list(user_place_ids)},
        )
        
        for result in results:
            place_data = result['p']
            place_id = result['element_id']
            place_data['element_id'] = place_id
            user_places.append(place_data)
        
        # Get all things-to-do places from Neo4j (excluding user's places)
        all_places = execute_neo4j_query(
            """
            MATCH (p:ThingToDo)
            WHERE NOT elementId(p) IN $user_place_ids
            RETURN p, elementId(p) AS element_id, labels(p) AS types
            """,
            {'user_place_ids': list(user_place_ids)},
        )
        
        # Calculate similarity scores for each place
        recommendations = []
        for result in all_places:
            place_data = result['p']
            place_id = result['element_id']
            place_data['element_id'] = place_id
            
            # Calculate average similarity score with user's places
            similarity_scores = [
                calculate_similarity_score(place_data, user_place)
                for user_place in user_places
            ]
            avg_similarity = sum(similarity_scores) / len(similarity_scores)
            
            # Add rating as a factor (30% weight)
            rating = place_data.get('rating', 0)
            final_score = (avg_similarity * 0.7) + (rating / 5.0 * 0.3)
            
            recommendations.append({
                'place': place_data,
                'score': final_score
            })
        
        # Sort by score and return top 10 recommendations
        recommendations.sort(key=lambda x: x['score'], reverse=True)
        top_recommendations = [
            {
                'id': rec['place']['element_id'],
                'name': rec['place'].get('name', ''),
                'rating': rec['place'].get('rating', 0),
                'image': rec['place'].get('image', ''),
                'subcategories': rec['place'].get('subcategories', []),
                'subtypes': rec['place'].get('subtypes', []),
                'similarity_score': rec['score']
            }
            for rec in recommendations[:10]
        ]
        
        return jsonify({
            'recommendations': top_recommendations,
            'total': len(top_recommendations)
        }), 200
        
    except Exception as e:
        logger.error(f'Error getting recommendations: {str(e)}')
        return jsonify({'error': 'Failed to get recommendations'}), 500

def get_popular_things_to_do():
    """Get popular things-to-do when user has no favorites or ratings."""
    try:
        # Query Neo4j for things-to-do with high ratings and many reviews
        results = execute_neo4j_query(
            """
            MATCH (p:ThingToDo)
            WHERE p.rating >= 4.0
            WITH p, 
                 CASE WHEN p.rating_histogram IS NOT NULL 
                 THEN reduce(total = 0, x IN p.rating_histogram | total + x) 
                 ELSE 0 END as review_count
            ORDER BY p.rating DESC, review_count DESC
            LIMIT 10
            RETURN p, elementId(p) AS element_id
            """
        )
        
        popular_places = []
        for result in results:
            place_data = result['p']
            place_id = result['element_id']
            
            popular_places.append({
                'id': place_id,
                'name': place_data.get('name', ''),
                'rating': place_data.get('rating', 0),
                'image': place_data.get('image', ''),
                'subcategories': place_data.get('subcategories', []),
                'subtypes': place_data.get('subtypes', [])
            })
        
        return jsonify({
            'recommendations': popular_places,
            'total': len(popular_places)
        }), 200
        
    except Exception as e:
        logger.error(f'Error getting popular things-to-do: {str(e)}')
        return jsonify({'error': 'Failed to get popular things-to-do'}), 500 