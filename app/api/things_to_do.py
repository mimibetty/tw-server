import json
import logging

from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from marshmallow import ValidationError, fields, pre_load, validates

from app.extensions import ma
from app.models import UserFavourite, db
from app.utils import (
    create_paging,
    execute_neo4j_query,
    get_all_subcategories,
    get_all_subtypes,
    get_redis,
    delete_place_and_related_data,
)

logger = logging.getLogger(__name__)
blueprint = Blueprint('things_to_do', __name__, url_prefix='/things-to-do')


class AttachCitySchema(ma.Schema):
    created_at = fields.String(dump_only=True)
    element_id = fields.String(dump_only=True)
    name = fields.String(dump_only=True)

    postal_code = fields.String(required=True)

    @validates('postal_code')
    def validate_postal_code(self, value: str):
        result = execute_neo4j_query(
            """
            MATCH (c:City {postal_code: $postal_code})
            RETURN c
            """,
            {'postal_code': value},
        )
        if not result:
            raise ValidationError('City with this postal code does not exist')
        return value


class ShortThingToDoSchema(ma.Schema):
    created_at = fields.String(dump_only=True)
    element_id = fields.String(dump_only=True)
    city = fields.Nested(AttachCitySchema, required=True)
    email = fields.Email(required=False, allow_none=True)
    image = fields.String(required=True)
    is_favorite = fields.Boolean(dump_only=True, default=False)
    latitude = fields.Float(required=True)
    longitude = fields.Float(required=True)
    name = fields.String(required=True)
    rating = fields.Float(required=False, allow_none=True)
    rating_histogram = fields.List(
        fields.Integer(), required=False, default=list
    )
    raw_ranking = fields.Float(required=True)
    street = fields.String(required=False, allow_none=True)
    type = fields.String(dump_only=True, default='THING-TO-DO')

    @validates('rating')
    def validate_rating(self, value: float):
        if value is not None and (value < 0 or value > 5):
            raise ValidationError('Rating must be between 0 and 5')
        return value

    @validates('rating_histogram')
    def validate_rating_histogram(self, value: list):
        if value and len(value) != 5:
            raise ValidationError(
                'Rating histogram must contain exactly 5 integers'
            )
        if value and not all(isinstance(i, int) and i >= 0 for i in value):
            raise ValidationError(
                'Rating histogram must be a list of 5 non-negative integers'
            )
        return value

    @validates('raw_ranking')
    def validate_raw_ranking(self, value: float):
        if value < 0 or value > 5:
            raise ValidationError('Raw ranking must be between 0 and 5')
        return value

    @pre_load
    def calculate_rating_from_histogram(self, data, **kwargs):
        if 'rating_histogram' not in data:
            data['rating_histogram'] = [0, 0, 0, 0, 0]
            data['rating'] = 0

        # Calculate rating from histogram if available
        if (
            'rating_histogram' in data
            and isinstance(data['rating_histogram'], list)
            and len(data['rating_histogram']) == 5
        ):
            rh = data['rating_histogram']
            total = sum(rh)
            if total > 0:
                calculated_rating = (
                    sum((i + 1) * rh[i] for i in range(5)) / total
                )
                data['rating'] = round(calculated_rating, 1)
            else:
                data['rating'] = 0

        return data


class ThingToDoSchema(ShortThingToDoSchema):
    phone = fields.String(required=False, allow_none=True)
    photos = fields.List(fields.String(), required=False, default=list)
    website = fields.String(required=False, allow_none=True)

    description = fields.String(required=False, allow_none=True)
    subtypes = fields.List(fields.String(), required=False, default=list)
    subcategories = fields.List(fields.String(), required=False, default=list)


@blueprint.get('/subtypes/')
def get_subtypes():
    """Get all available subtypes for things to do."""
    subtypes = get_all_subtypes()
    return {'subtypes': subtypes}, 200


@blueprint.get('/subcategories/')
def get_subcategories():
    """Get all available subcategories for things to do."""
    subcategories = get_all_subcategories()
    return {'subcategories': subcategories}, 200


@blueprint.post('/')
def create_thing_to_do():
    schema = ThingToDoSchema()
    data = schema.load(request.json)
    city_postal_code = data['city']['postal_code']

    # Create the thing to do and attach it to the city in Neo4j
    result = execute_neo4j_query(
        """
        MATCH (c:City {postal_code: $postal_code})
        CREATE
            (t:ThingToDo
                {
                    name: $name,
                    image: $image,
                    latitude: $latitude,
                    longitude: $longitude,
                    photos: $photos,
                    rating: $rating,
                    rating_histogram: $rating_histogram,
                    raw_ranking: $raw_ranking,
                    description: $description,
                    email: $email,
                    phone: $phone,
                    website: $website,
                    street: $street,
                    type: 'THING-TO-DO',
                    created_at:
                        apoc.date.format(timestamp(), 'ms', 'yyyy-MM-dd HH:mm', 'GMT+7')
                })
        MERGE (t)-[:LOCATED_IN]->(c)

        // Handle subtypes if provided
        WITH t, c, $subtypes AS subtypes
        UNWIND subtypes AS subtype
        MERGE (st:Subtype {name: subtype})
        MERGE (t)-[:HAS_SUBTYPE]->(st)

        // Handle subcategories if provided
        WITH t, c, $subcategories AS subcategories
        UNWIND subcategories AS subcategory
        MERGE (sc:Subcategory {name: subcategory})
        MERGE (t)-[:HAS_SUBCATEGORY]->(sc)

        // Return thing to do with related data
        RETURN
            t,
            elementId(t) AS element_id,
            c
        """,
        {
            'postal_code': city_postal_code,
            'name': data['name'],
            'image': data['image'],
            'latitude': data['latitude'],
            'longitude': data['longitude'],
            'photos': data.get('photos', []),
            'rating': data.get('rating'),
            'rating_histogram': data.get('rating_histogram', []),
            'raw_ranking': data['raw_ranking'],
            'description': data.get('description'),
            'email': data.get('email'),
            'phone': data.get('phone'),
            'website': data.get('website'),
            'street': data.get('street'),
            'subtypes': data.get('subtypes', []),
            'subcategories': data.get('subcategories', []),
        },
    )

    if not result:
        return {'error': 'Failed to create thing to do.'}, 400

    # Delete cached thing to do data
    redis = get_redis()
    keys_to_delete = redis.keys('things-to-do:*')
    if keys_to_delete:
        redis.delete(*keys_to_delete)

    thing_to_do = result[0]['t']
    thing_to_do['element_id'] = result[0]['element_id']
    thing_to_do['city'] = result[0]['c']
    return schema.dump(thing_to_do), 201


@blueprint.get('/')
@jwt_required(optional=True)
def get_things_to_do():
    # Get query parameters for pagination
    page = request.args.get('page', default=1, type=int)
    size = request.args.get('size', default=10, type=int)
    offset = (page - 1) * size

    # Get search and filter parameters
    search = request.args.get('search', default='', type=str)
    rating = request.args.get('rating', type=float)
    subtypes = request.args.get('subtypes', type=str)
    subcategories = request.args.get('subcategories', type=str)

    # Get sort order
    sort_order = request.args.get('order', default='desc', type=str)
    sort_order = 'DESC' if sort_order.upper() == 'DESC' else 'ASC'

    user_id = None
    try:
        user_id = get_jwt_identity()
    except Exception:
        pass

    # Determine operation mode
    is_search_mode = bool(search.strip())
    is_filter_mode = (
        rating is not None or subtypes is not None or subcategories is not None
    )

    if is_search_mode and is_filter_mode:
        return {
            'error': 'Cannot use search and filter parameters simultaneously. Please use either search OR filter parameters.'
        }, 400

    if not is_search_mode and not is_filter_mode:
        # Default behavior: return all things to do
        return _get_all_things_to_do(page, size, offset, user_id, sort_order)
    elif is_search_mode:
        return _search_things_to_do(
            search, page, size, offset, user_id, sort_order
        )
    else:  # is_filter_mode
        # Parse comma-separated strings into lists
        subtype_list = subtypes.split(',') if subtypes else []
        subcategory_list = subcategories.split(',') if subcategories else []

        return _filter_things_to_do(
            rating,
            subtype_list,
            subcategory_list,
            page,
            size,
            offset,
            user_id,
            sort_order,
        )


def _get_all_things_to_do(page, size, offset, user_id, sort_order):
    """Get all things to do with pagination."""
    # Check if the result is cached
    redis = get_redis()
    cache_key = f'things-to-do:page={page}:size={size}:order={sort_order}:all'
    try:
        cached_response = redis.get(cache_key)
        if cached_response:
            things = json.loads(cached_response)
            # Add is_favorite field if user_id exists
            if user_id:
                thing_ids = [t['element_id'] for t in things['data']]
                favourites = (
                    db.session.query(UserFavourite.place_id)
                    .filter(
                        UserFavourite.user_id == user_id,
                        UserFavourite.place_id.in_(thing_ids),
                    )
                    .all()
                )
                favourite_ids = set(f[0] for f in favourites)
                for t in things['data']:
                    t['is_favorite'] = t['element_id'] in favourite_ids
            else:
                for t in things['data']:
                    t['is_favorite'] = False
            return things, 200
    except Exception as e:
        logger.warning('Redis is not available to get data: %s', e)

    # Get the total count of all things to do
    count_query = 'MATCH (t:ThingToDo) RETURN count(t) AS total_count'
    total_count_result = execute_neo4j_query(count_query)
    total_count = total_count_result[0]['total_count']

    # Get all things to do with pagination
    things_query = f"""
    MATCH (t:ThingToDo)
    OPTIONAL MATCH (t)-[:LOCATED_IN]->(c:City)
    OPTIONAL MATCH (t)-[:HAS_SUBTYPE]->(st:Subtype)
    OPTIONAL MATCH (t)-[:HAS_SUBCATEGORY]->(sc:Subcategory)
    WITH t, collect(DISTINCT st.name) AS subtypes, collect(DISTINCT sc.name) AS subcategories, c
    RETURN t, elementId(t) AS element_id, subtypes, subcategories, c AS city
    ORDER BY t.raw_ranking {sort_order}
    SKIP $offset
    LIMIT $size
    """

    result = execute_neo4j_query(
        things_query, {'offset': offset, 'size': size}
    )

    # Process results
    processed_results = _process_things_to_do_results(result, user_id)

    # Create paginated response
    response = create_paging(
        data=ShortThingToDoSchema(many=True).dump(processed_results),
        page=page,
        size=size,
        offset=offset,
        total_count=total_count,
    )

    # Cache the response for 6 hours
    try:
        redis.set(cache_key, json.dumps(response), ex=21600)
    except Exception as e:
        logger.warning('Redis is not available to set data: %s', e)

    return response, 200


def _search_things_to_do(search, page, size, offset, user_id, sort_order):
    """Search things to do by name."""
    # Check if the result is cached
    redis = get_redis()
    cache_key = f'things-to-do:page={page}:size={size}:order={sort_order}:search={search}'
    try:
        cached_response = redis.get(cache_key)
        if cached_response:
            things = json.loads(cached_response)
            # Add is_favorite field if user_id exists
            if user_id:
                thing_ids = [t['element_id'] for t in things['data']]
                favourites = (
                    db.session.query(UserFavourite.place_id)
                    .filter(
                        UserFavourite.user_id == user_id,
                        UserFavourite.place_id.in_(thing_ids),
                    )
                    .all()
                )
                favourite_ids = set(f[0] for f in favourites)
                for t in things['data']:
                    t['is_favorite'] = t['element_id'] in favourite_ids
            else:
                for t in things['data']:
                    t['is_favorite'] = False
            return things, 200
    except Exception as e:
        logger.warning('Redis is not available to get data: %s', e)

    query_params = {'offset': offset, 'size': size, 'search': search}

    # Get the total count of things to do matching the search criteria
    count_query = """
    MATCH (t:ThingToDo)
    WHERE toLower(t.name) CONTAINS toLower($search)
    RETURN count(t) AS total_count
    """

    total_count_result = execute_neo4j_query(count_query, query_params)
    total_count = total_count_result[0]['total_count']

    # Get the things to do with pagination
    things_query = f"""
    MATCH (t:ThingToDo)
    WHERE toLower(t.name) CONTAINS toLower($search)
    OPTIONAL MATCH (t)-[:LOCATED_IN]->(c:City)
    OPTIONAL MATCH (t)-[:HAS_SUBTYPE]->(st:Subtype)
    OPTIONAL MATCH (t)-[:HAS_SUBCATEGORY]->(sc:Subcategory)
    WITH t, collect(DISTINCT st.name) AS subtypes, collect(DISTINCT sc.name) AS subcategories, c
    RETURN t, elementId(t) AS element_id, subtypes, subcategories, c AS city
    ORDER BY t.raw_ranking {sort_order}
    SKIP $offset
    LIMIT $size
    """

    result = execute_neo4j_query(things_query, query_params)

    # Process results
    processed_results = _process_things_to_do_results(result, user_id)

    # Create paginated response
    response = create_paging(
        data=ShortThingToDoSchema(many=True).dump(processed_results),
        page=page,
        size=size,
        offset=offset,
        total_count=total_count,
    )

    # Cache the response for 6 hours
    try:
        redis.set(cache_key, json.dumps(response), ex=21600)
    except Exception as e:
        logger.warning('Redis is not available to set data: %s', e)

    return response, 200


def _filter_things_to_do(
    rating, subtypes, subcategories, page, size, offset, user_id, sort_order
):
    """Filter things to do by rating and subtypes/subcategories."""
    redis = get_redis()

    # Build a dynamic cache key
    cache_parts = [
        f'page={page}',
        f'size={size}',
        f'order={sort_order}',
        'filter',
    ]
    if rating is not None:
        cache_parts.append(f'rating={rating}')
    if subtypes:
        cache_parts.append(f'subtypes={",".join(sorted(subtypes))}')
    if subcategories:
        cache_parts.append(f'subcategories={",".join(sorted(subcategories))}')
    cache_key = f'things-to-do:{":".join(cache_parts)}'

    # Check Redis cache first
    try:
        cached_response = redis.get(cache_key)
        if cached_response:
            things = json.loads(cached_response)
            # Add is_favorite field for authenticated users
            if user_id:
                thing_ids = [t['element_id'] for t in things['data']]
                favourites = (
                    db.session.query(UserFavourite.place_id)
                    .filter(
                        UserFavourite.user_id == user_id,
                        UserFavourite.place_id.in_(thing_ids),
                    )
                    .all()
                )
                favourite_ids = set(f[0] for f in favourites)
                for t in things['data']:
                    t['is_favorite'] = t['element_id'] in favourite_ids
            else:
                for t in things['data']:
                    t['is_favorite'] = False
            return things, 200
    except Exception as e:
        logger.warning('Redis cache unavailable: %s', e)

    # Build the query dynamically
    query_params = {'offset': offset, 'size': size}
    where_clauses = []

    if rating is not None:
        where_clauses.append('t.rating >= $rating')
        query_params['rating'] = rating
    if subtypes:
        # This clause checks if a place has ALL of the specified subtypes
        where_clauses.append(
            'ALL(subtype_name IN $subtypes WHERE (t)-[:HAS_SUBTYPE]->(:Subtype {name: subtype_name}))'
        )
        query_params['subtypes'] = subtypes
    if subcategories:
        # This clause checks if a place has ALL of the specified subcategories
        where_clauses.append(
            'ALL(subcategory_name IN $subcategories WHERE (t)-[:HAS_SUBCATEGORY]->(:Subcategory {name: subcategory_name}))'
        )
        query_params['subcategories'] = subcategories

    where_str = ''
    if where_clauses:
        where_str = 'WHERE ' + ' AND '.join(where_clauses)

    # Get the total count of things to do matching the filter
    count_query = f"""
    MATCH (t:ThingToDo)
    {where_str}
    RETURN count(t) AS total_count
    """
    total_count_result = execute_neo4j_query(count_query, query_params)
    total_count = (
        total_count_result[0]['total_count'] if total_count_result else 0
    )

    # Get the things to do with pagination and filter
    things_query = f"""
    MATCH (t:ThingToDo)
    {where_str}
    OPTIONAL MATCH (t)-[:LOCATED_IN]->(c:City)
    OPTIONAL MATCH (t)-[:HAS_SUBTYPE]->(st:Subtype)
    OPTIONAL MATCH (t)-[:HAS_SUBCATEGORY]->(sc:Subcategory)
    WITH t, c, collect(DISTINCT st.name) AS subtypes, collect(DISTINCT sc.name) AS subcategories
    RETURN t, elementId(t) AS element_id, subtypes, subcategories, c AS city
    ORDER BY t.raw_ranking {sort_order}
    SKIP $offset
    LIMIT $size
    """

    result = execute_neo4j_query(things_query, query_params)

    # Process results
    processed_results = _process_things_to_do_results(result, user_id)

    # Create paginated response
    response = create_paging(
        data=ShortThingToDoSchema(many=True).dump(processed_results),
        page=page,
        size=size,
        offset=offset,
        total_count=total_count,
    )

    # Cache the result for 6 hours
    try:
        redis.set(cache_key, json.dumps(response), ex=21600)
    except Exception as e:
        logger.warning('Redis cache set failed: %s', e)

    return response, 200


def _process_things_to_do_results(result, user_id):
    """Process things to do query results."""
    processed_results = []
    for record in result:
        thing = record['t']
        thing['element_id'] = record['element_id']
        thing['subtypes'] = record['subtypes']
        thing['subcategories'] = record['subcategories']
        if record['city']:
            thing['city'] = record['city']

        # Calculate rating if not present
        if 'rating' not in thing or thing['rating'] is None:
            rh = thing.get('rating_histogram', [])
            if rh and isinstance(rh, list) and len(rh) == 5:
                total = sum(rh)
                if total > 0:
                    rating = sum((i + 1) * rh[i] for i in range(5)) / total
                    thing['rating'] = round(rating, 1)
        processed_results.append(thing)

    # Add is_favorite field
    if user_id:
        thing_ids = [t['element_id'] for t in processed_results]
        favourites = (
            db.session.query(UserFavourite.place_id)
            .filter(
                UserFavourite.user_id == user_id,
                UserFavourite.place_id.in_(thing_ids),
            )
            .all()
        )
        favourite_ids = set(f[0] for f in favourites)
        for t in processed_results:
            t['is_favorite'] = t['element_id'] in favourite_ids
    else:
        for t in processed_results:
            t['is_favorite'] = False

    return processed_results


@blueprint.get('/<thing_to_do_id>/')
@jwt_required(optional=True)
def get_thing_to_do(thing_to_do_id):
    schema = ThingToDoSchema()

    # Check if the user is authenticated
    user_id = None
    try:
        user_id = get_jwt_identity()
    except Exception:
        pass

    # Check if the result is cached
    redis = get_redis()
    cache_key = f'things-to-do:{thing_to_do_id}'
    try:
        cached_response = redis.get(cache_key)
        if cached_response:
            thing_to_do = json.loads(cached_response)
            # Add is_favorite field
            if user_id:
                favourite = (
                    db.session.query(UserFavourite.place_id)
                    .filter(
                        UserFavourite.user_id == user_id,
                        UserFavourite.place_id == thing_to_do_id,
                    )
                    .first()
                )
                thing_to_do['is_favorite'] = bool(favourite)
            else:
                thing_to_do['is_favorite'] = False
            return schema.dump(thing_to_do), 200
    except Exception as e:
        logger.warning('Redis is not available to get data: %s', e)

    # Get the thing to do details along with subtypes, subcategories
    result = execute_neo4j_query(
        """
        MATCH (t:ThingToDo)
        WHERE elementId(t) = $thing_to_do_id
        OPTIONAL MATCH (t)-[:HAS_SUBTYPE]->(st:Subtype)
        OPTIONAL MATCH (t)-[:HAS_SUBCATEGORY]->(sc:Subcategory)
        OPTIONAL MATCH (t)-[:LOCATED_IN]->(c:City)
        RETURN
            t,
            elementId(t) AS element_id,
            collect(DISTINCT st.name) AS subtypes,
            collect(DISTINCT sc.name) AS subcategories,
            c AS city
        """,
        {'thing_to_do_id': thing_to_do_id},
    )

    if not result:
        return {'error': 'Thing to do not found'}, 404

    thing_to_do = result[0]['t']
    thing_to_do['element_id'] = result[0]['element_id']
    thing_to_do['subtypes'] = result[0]['subtypes']
    thing_to_do['subcategories'] = result[0]['subcategories']
    if result[0]['city']:
        thing_to_do['city'] = result[0]['city']

    # Calculate rating if not present
    if 'rating' not in thing_to_do or thing_to_do['rating'] is None:
        rh = thing_to_do.get('rating_histogram', [])
        if rh and isinstance(rh, list) and len(rh) == 5:
            total = sum(rh)
            if total > 0:
                rating = sum((i + 1) * rh[i] for i in range(5)) / total
                thing_to_do['rating'] = round(rating, 1)

    # Add is_favorite field
    if user_id:
        favourite = (
            db.session.query(UserFavourite.place_id)
            .filter(
                UserFavourite.user_id == user_id,
                UserFavourite.place_id == thing_to_do_id,
            )
            .first()
        )
        thing_to_do['is_favorite'] = bool(favourite)
    else:
        thing_to_do['is_favorite'] = False

    # Cache the response for 6 hours
    try:
        redis.set(cache_key, json.dumps(thing_to_do), ex=21600)
    except Exception as e:
        logger.warning('Redis is not available to set data: %s', e)

    return schema.dump(thing_to_do), 200


@blueprint.delete('/<thing_to_do_id>/')
def delete_thing_to_do(thing_to_do_id):
    """
    Delete a thing-to-do and all related data.

    This endpoint will:
    - Remove the thing-to-do from Neo4j database
    - Delete all user reviews of this thing-to-do
    - Remove thing-to-do from user favorites
    - Remove thing-to-do from user trips
    - Clear all related cache entries
    """
    try:
        # First check if thing-to-do exists and is actually a thing-to-do
        result = execute_neo4j_query(
            """
            MATCH (t:ThingToDo)
            WHERE elementId(t) = $thing_to_do_id
            RETURN t.name as name, t.type as type
            """,
            {'thing_to_do_id': thing_to_do_id},
        )

        if not result:
            return {'error': 'Thing to do not found'}, 404

        thing_name = result[0]['name']

        # Use the comprehensive deletion utility
        deletion_summary = delete_place_and_related_data(thing_to_do_id)

        # Check if deletion was successful
        if not deletion_summary['place_deleted']:
            return {
                'error': 'Failed to delete thing to do',
                'details': deletion_summary['errors'],
            }, 500

        # Prepare success response
        response = {
            'message': f'Thing to do "{thing_name}" has been successfully deleted',
            'summary': {
                'thing_to_do_deleted': deletion_summary['place_deleted'],
                'reviews_deleted': deletion_summary['reviews_deleted'],
                'favorites_removed': deletion_summary['favorites_deleted'],
                'trips_updated': deletion_summary['trips_updated'],
                'cache_cleared': deletion_summary['cache_cleared'],
            },
        }

        # Include any non-critical errors as warnings
        if deletion_summary['errors']:
            response['warnings'] = deletion_summary['errors']

        return response, 200

    except Exception as e:
        logger.error(f'Error deleting thing to do {thing_to_do_id}: {str(e)}')
        return {
            'error': 'An unexpected error occurred while deleting the thing to do',
            'details': str(e),
        }, 500
