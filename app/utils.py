import logging
import json

logger = logging.getLogger(__name__)

def create_paging(
    data: list, page: int, size: int, offset: int, total_count: int
):
    page_count = (total_count // size) + (1 if total_count % size > 0 else 0)

    return {
        'data': data,
        'paging': {
            'page': page,
            'size': size,
            'offset': offset,
            'totalCount': total_count,
            'pageCount': page_count,
        },
    }


def execute_neo4j_query(query: str, params: dict = None):
    from neo4j import GraphDatabase

    from .environments import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USERNAME

    driver = GraphDatabase.driver(
        NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD)
    )
    try:
        with driver.session() as session:
            result = session.run(query, params)
            if 'RETURN' in query.upper():
                return result.data()
    except Exception as e:
        raise e
    finally:
        driver.close()


def send_async_email(recipients: list[str], subject: str, html: str):
    from threading import Thread

    from flask_mail import Message

    from . import AppContext
    from .extensions import mail

    def send_email(message: Message):
        app = AppContext().get_app()
        with app.app_context():
            mail.send(message)

    # Create a new message
    message = Message(subject=subject, recipients=recipients)
    message.html = html

    # Start a new thread to send the email
    thread = Thread(target=send_email, args=(message,))
    thread.start()


def get_redis():
    from . import AppContext

    return AppContext().get_redis()


def update_place_rating_histogram(place_id: str, old_rating: float = None, new_rating: float = None):
    """
    Update the rating histogram of a place in Neo4j.
    
    Args:
        place_id: The ID of the place
        old_rating: The old rating to remove (if updating or deleting)
        new_rating: The new rating to add (if creating or updating)
    """
    try:
        # Convert ratings to integers (1-5)
        if old_rating is not None:
            old_rating = int(round(old_rating))
        if new_rating is not None:
            new_rating = int(round(new_rating))

        # If updating or deleting, first decrement the old rating
        if old_rating is not None:
            execute_neo4j_query(
                """
                MATCH (p)
                WHERE elementId(p) = $place_id
                WITH p, 
                     CASE WHEN p.rating_histogram IS NULL THEN [0,0,0,0,0] ELSE p.rating_histogram END as hist
                SET p.rating_histogram = [
                    CASE WHEN $rating = 1 AND hist[0] > 0 THEN hist[0] - 1 ELSE hist[0] END,
                    CASE WHEN $rating = 2 AND hist[1] > 0 THEN hist[1] - 1 ELSE hist[1] END,
                    CASE WHEN $rating = 3 AND hist[2] > 0 THEN hist[2] - 1 ELSE hist[2] END,
                    CASE WHEN $rating = 4 AND hist[3] > 0 THEN hist[3] - 1 ELSE hist[3] END,
                    CASE WHEN $rating = 5 AND hist[4] > 0 THEN hist[4] - 1 ELSE hist[4] END
                ]
                """,
                {'place_id': place_id, 'rating': old_rating}
            )
        
        # If creating or updating, increment the new rating
        if new_rating is not None:
            execute_neo4j_query(
                """
                MATCH (p)
                WHERE elementId(p) = $place_id
                WITH p, 
                     CASE WHEN p.rating_histogram IS NULL THEN [0,0,0,0,0] ELSE p.rating_histogram END as hist
                SET p.rating_histogram = [
                    CASE WHEN $rating = 1 THEN hist[0] + 1 ELSE hist[0] END,
                    CASE WHEN $rating = 2 THEN hist[1] + 1 ELSE hist[1] END,
                    CASE WHEN $rating = 3 THEN hist[2] + 1 ELSE hist[2] END,
                    CASE WHEN $rating = 4 THEN hist[3] + 1 ELSE hist[3] END,
                    CASE WHEN $rating = 5 THEN hist[4] + 1 ELSE hist[4] END
                ]
                """,
                {'place_id': place_id, 'rating': new_rating}
            )
        
        # Update the average rating
        execute_neo4j_query(
            """
            MATCH (p)
            WHERE elementId(p) = $place_id
            WITH p, 
                 CASE WHEN p.rating_histogram IS NULL THEN [0,0,0,0,0] ELSE p.rating_histogram END as hist
            SET p.rating = CASE 
                WHEN reduce(total = 0, x IN hist | total + x) > 0 
                THEN round(toFloat(reduce(total = 0, i IN range(0, 4) | total + (i + 1) * hist[i])) / toFloat(reduce(total = 0, x IN hist | total + x)), 1)
                ELSE 0.0 
            END
            RETURN p.rating, p.rating_histogram
            """,
            {'place_id': place_id}
        )
        # # Log the updated rating and histogram for debugging
        # result = execute_neo4j_query(
        #     """
        #     MATCH (p)
        #     WHERE elementId(p) = $place_id
        #     RETURN p.rating, p.rating_histogram
        #     """,
        #     {'place_id': place_id}
        # )
        # print(result)
        # print("--------------------------------")
        # if result:
        #     logger.info(f"Updated rating for place {place_id}: {result[0]['p.rating']}, histogram: {result[0]['p.rating_histogram']}")
        # else:
        #     logger.warning(f"No result found for place {place_id} after updating rating.")
        
        return True
    except Exception as e:
        logger.error(f"Error updating rating histogram: {str(e)}")
        return False


def check_place_exists(place_id: str) -> bool:
    """
    Check if a place exists in Neo4j database.
    
    Args:
        place_id: The ID of the place to check
        
    Returns:
        bool: True if place exists, False otherwise
    """
    try:
        result = execute_neo4j_query(
            """
            MATCH (p)
            WHERE elementId(p) = $place_id
            RETURN count(p) as count
            """,
            {'place_id': place_id}
        )
        return result[0]['count'] > 0
    except Exception as e:
        logger.error(f"Error checking place existence: {str(e)}")
        return False


def update_user_preference_cache(user_id: str):
    """
    Update cached user preferences when user adds favorites or reviews.
    This helps keep recommendations fresh and personalized.
    
    Args:
        user_id: The ID of the user whose preferences need updating
    """
    try:
        redis = get_redis()
        
        # Clear cached recommendations for this user
        pattern = f"recommendations:{user_id}:*"
        keys_to_delete = redis.keys(pattern)
        if keys_to_delete:
            redis.delete(*keys_to_delete)
            logger.info(f"Cleared {len(keys_to_delete)} cached recommendations for user {user_id}")
        
        # Optionally pre-compute and cache user preferences
        from app.models import UserFavourite, UserReview, db
        
        # Get user's favorites and reviews
        favorites_result = db.session.execute(
            db.text("SELECT place_id FROM user_favourites WHERE user_id = :user_id"),
            {'user_id': user_id}
        )
        favorite_place_ids = [row.place_id for row in favorites_result]
        
        reviews_result = db.session.execute(
            db.text("SELECT place_id, rating FROM user_reviews WHERE user_id = :user_id"),
            {'user_id': user_id}
        )
        reviews = {row.place_id: row.rating for row in reviews_result}
        
        # Cache user interaction summary
        interaction_summary = {
            'favorite_count': len(favorite_place_ids),
            'review_count': len(reviews),
            'avg_rating': sum(reviews.values()) / len(reviews) if reviews else 0.0,
            'last_updated': db.session.execute(db.text("SELECT NOW()")).scalar().isoformat()
        }
        
        redis.setex(f"user_summary:{user_id}", 3600, json.dumps(interaction_summary))
        
        return True
    except Exception as e:
        logger.error(f"Error updating user preference cache: {str(e)}")
        return False
