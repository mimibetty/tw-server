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
    get_all_cuisines,
    get_all_dietary_restrictions,
    get_all_dishes,
    get_all_meal_types,
    get_all_restaurant_features,
    get_redis,
    delete_place_and_related_data,
)

logger = logging.getLogger(__name__)
blueprint = Blueprint('restaurants', __name__, url_prefix='/restaurants')


class SimplifiedHourSchema(ma.Schema):
    open = fields.String(required=True)
    close = fields.String(required=True)


class HoursSchema(ma.Schema):
    monday = fields.Nested(SimplifiedHourSchema, allow_none=True)
    tuesday = fields.Nested(SimplifiedHourSchema, allow_none=True)
    wednesday = fields.Nested(SimplifiedHourSchema, allow_none=True)
    thursday = fields.Nested(SimplifiedHourSchema, allow_none=True)
    friday = fields.Nested(SimplifiedHourSchema, allow_none=True)
    saturday = fields.Nested(SimplifiedHourSchema, allow_none=True)
    sunday = fields.Nested(SimplifiedHourSchema, allow_none=True)
    timezone = fields.String(allow_none=True)


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


class ShortRestaurantSchema(ma.Schema):
    created_at = fields.String(dump_only=True)
    element_id = fields.String(dump_only=True)
    city = fields.Nested(AttachCitySchema, required=True)
    email = fields.Email(required=False, allow_none=True)
    image = fields.String(required=True)
    is_favorite = fields.Boolean(dump_only=True, default=False)
    latitude = fields.Float(required=True)
    longitude = fields.Float(required=True)
    name = fields.String(required=True)
    price_levels = fields.List(fields.String(), required=False, default=list)
    rating = fields.Float(required=False, allow_none=True)
    rating_histogram = fields.List(
        fields.Integer(), required=False, default=list
    )
    raw_ranking = fields.Float(required=True, load_only=True)
    street = fields.String(required=False, allow_none=True)
    type = fields.String(dump_only=True)

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


class RestaurantSchema(ShortRestaurantSchema):
    phone = fields.String(required=False, allow_none=True)
    photos = fields.List(fields.String(), required=False, default=list)
    website = fields.String(required=False, allow_none=True)

    # Restaurant-specific fields
    description = fields.String(required=False, allow_none=True)
    menu_web_url = fields.String(required=False, allow_none=True)
    hours = fields.Nested(HoursSchema, required=False, allow_none=True)
    dishes = fields.List(fields.String(), required=False, default=list)
    features = fields.List(fields.String(), required=False, default=list)
    dietary_restrictions = fields.List(
        fields.String(), required=False, default=list
    )
    meal_types = fields.List(fields.String(), required=False, default=list)
    cuisines = fields.List(fields.String(), required=False, default=list)
    traveler_choice_award = fields.Boolean(required=False, default=False)


@blueprint.get('/cuisines/')
def get_cuisines():
    """Get all available cuisines for restaurants."""
    cuisines = get_all_cuisines()
    return {'cuisines': cuisines}, 200


@blueprint.get('/meal-types/')
def get_meal_types():
    """Get all available meal types for restaurants."""
    meal_types = get_all_meal_types()
    return {'meal_types': meal_types}, 200


@blueprint.get('/features/')
def get_features():
    """Get all available features (amenities) for restaurants."""
    features = get_all_restaurant_features()
    return {'features': features}, 200


@blueprint.get('/dietary-restrictions/')
def get_dietary_restrictions():
    """Get all available dietary restrictions for restaurants."""
    restrictions = get_all_dietary_restrictions()
    return {'dietary_restrictions': restrictions}, 200


@blueprint.get('/dishes/')
def get_dishes():
    """Get all available dishes for restaurants."""
    dishes = get_all_dishes()
    return {'dishes': dishes}, 200


@blueprint.post('/')
def create_restaurant():
    data = RestaurantSchema().load(request.json)
    city_postal_code = data['city']['postal_code']

    # Get data with defaults for empty lists
    features = data.get('features', [])
    price_levels = data.get('price_levels', [])
    meal_types = data.get('meal_types', [])
    cuisines = data.get('cuisines', [])

    # Base query to create restaurant
    query = """
    MATCH (c:City {postal_code: $postal_code})
    CREATE
        (r:Restaurant
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
                menu_web_url: $menu_web_url,
                hours: $hours,
                dishes: $dishes,
                dietary_restrictions: $dietary_restrictions,
                traveler_choice_award: $traveler_choice_award,
                street: $street,
                type: 'RESTAURANT',
                created_at:
                    apoc.date.format(timestamp(), 'ms', 'yyyy-MM-dd HH:mm', 'GMT+7')
            })
    MERGE (r)-[:LOCATED_IN]->(c)
    """

    # Add features relationship if features list is not empty
    if features:
        query += """
        WITH r, c
        UNWIND $features AS feature_name
        MERGE (a:Feature {name: feature_name})
        MERGE (r)-[:HAS_FEATURE]->(a)
        """

    # Add price_levels relationship if price_levels list is not empty
    if price_levels:
        query += """
        WITH r, c
        UNWIND $price_levels AS price_level
        MERGE (pl:PriceLevel {level: price_level})
        MERGE (r)-[:HAS_PRICE_LEVEL]->(pl)
        """

    # Add meal_types relationship if meal_types list is not empty
    if meal_types:
        query += """
        WITH r, c
        UNWIND $meal_types AS meal_type
        MERGE (mt:MealType {name: meal_type})
        MERGE (r)-[:SERVES_MEAL]->(mt)
        """

    # Add cuisines relationship if cuisines list is not empty
    if cuisines:
        query += """
        WITH r, c
        UNWIND $cuisines AS cuisine
        MERGE (cu:Cuisine {name: cuisine})
        MERGE (r)-[:HAS_CUISINE]->(cu)
        """

    # Finalize query to return data
    query += """
    RETURN
        r,
        elementId(r) AS element_id,
        c
    """

    # Execute the Neo4j query
    result = execute_neo4j_query(
        query,
        {
            'postal_code': city_postal_code,
            'name': data['name'],
            'image': data['image'],
            'latitude': data['latitude'],
            'longitude': data['longitude'],
            'photos': data.get('photos', []),
            'price_levels': price_levels,
            'rating': data.get('rating'),
            'rating_histogram': data.get('rating_histogram', []),
            'raw_ranking': data['raw_ranking'],
            'description': data.get('description'),
            'email': data.get('email'),
            'phone': data.get('phone'),
            'website': data.get('website'),
            'menu_web_url': data.get('menu_web_url'),
            'hours': json.dumps(data.get('hours'))
            if data.get('hours')
            else None,
            'dishes': data.get('dishes', []),
            'features': features,
            'dietary_restrictions': data.get('dietary_restrictions', []),
            'meal_types': meal_types,
            'cuisines': cuisines,
            'traveler_choice_award': data.get('traveler_choice_award', False),
            'street': data.get('street'),
        },
    )

    if not result:
        return {'error': 'Failed to create restaurant.'}, 400

    # Delete cached restaurant data
    redis = get_redis()
    keys_to_delete = redis.keys('restaurants:*')
    if keys_to_delete:
        redis.delete(*keys_to_delete)

    restaurant = result[0]['r']
    restaurant['element_id'] = result[0]['element_id']
    restaurant['city'] = result[0]['c']
    return ShortRestaurantSchema().dump(restaurant), 201


@blueprint.get('/')
@jwt_required(optional=True)
def get_restaurants():
    # Get query parameters for pagination
    page = request.args.get('page', default=1, type=int)
    size = request.args.get('size', default=10, type=int)
    offset = (page - 1) * size

    # Get search and filter parameters
    search = request.args.get('search', default='', type=str)
    rating = request.args.get('rating', type=float) #ok
    cuisines = request.args.get('cuisines', type=str)
    meal_types = request.args.get('meal_types', type=str)  #ok
    features = request.args.get('features', type=str)  # Amenities #ok
    dietary_restrictions = request.args.get('dietary_restrictions', type=str)
    dishes = request.args.get('dishes', type=str)

    print('--------------------------------')
    print('search', search)
    print('rating', rating)
    print('cuisines', cuisines)
    print('meal_types', meal_types)
    print('features', features)
    print('dietary_restrictions', dietary_restrictions)
    print('dishes', dishes)
    print('--------------------------------')
    user_id = None
    try:
        user_id = get_jwt_identity()
    except Exception:
        pass

    # Determine operation mode
    is_search_mode = bool(search.strip())
    is_filter_mode = any(
        [rating, cuisines, meal_types, features, dietary_restrictions, dishes]
    )

    if is_search_mode and is_filter_mode:
        return {
            'error': 'Cannot use search and filter parameters simultaneously. Please use either search OR filter parameters.'
        }, 400

    if not is_search_mode and not is_filter_mode:
        return _get_all_restaurants(page, size, offset, user_id)
    elif is_search_mode:
        return _search_restaurants(search, page, size, offset, user_id)
    else:  # is_filter_mode
        # Parse comma-separated strings into lists
        cuisine_list = cuisines.split(',') if cuisines else []
        meal_type_list = meal_types.split(',') if meal_types else []
        feature_list = features.split(',') if features else []
        dietary_list = (
            dietary_restrictions.split(',') if dietary_restrictions else []
        )
        dish_list = dishes.split(',') if dishes else []

        return _filter_restaurants(
            rating=rating,
            cuisines=cuisine_list,
            meal_types=meal_type_list,
            features=feature_list,
            dietary_restrictions=dietary_list,
            dishes=dish_list,
            page=page,
            size=size,
            offset=offset,
            user_id=user_id,
        )


def _process_restaurant_results(result, user_id):
    """Helper function to process Neo4j results for restaurants."""
    # Add element_id, price_levels, and city to each restaurant record
    for record in result:
        record['r']['element_id'] = record['element_id']
        record['r']['price_levels'] = record.get('price_levels', [])
        record['r']['cuisines'] = record.get('cuisines', [])
        record['r']['meal_types'] = record.get('meal_types', [])
        record['r']['features'] = record.get('features', [])
        if record['city']:
            record['r']['city'] = record['city']

    restaurants_data = [record['r'] for record in result]

    # Add is_favorite field
    if user_id:
        restaurant_ids = [r['element_id'] for r in restaurants_data]
        favourites = (
            db.session.query(UserFavourite.place_id)
            .filter(
                UserFavourite.user_id == user_id,
                UserFavourite.place_id.in_(restaurant_ids),
            )
            .all()
        )
        favourite_ids = set(f[0] for f in favourites)
        for r in restaurants_data:
            r['is_favorite'] = r['element_id'] in favourite_ids
    else:
        for r in restaurants_data:
            r['is_favorite'] = False

    return restaurants_data


def _get_all_restaurants(page, size, offset, user_id):
    """Get all restaurants with pagination."""
    redis = get_redis()
    cache_key = f'restaurants:page={page}:size={size}:all'
    try:
        cached_response = redis.get(cache_key)
        if cached_response:
            restaurants = json.loads(cached_response)
            # Add is_favorite field if user_id exists
            if user_id:
                restaurant_ids = [r['element_id'] for r in restaurants['data']]
                favourites = (
                    db.session.query(UserFavourite.place_id)
                    .filter(
                        UserFavourite.user_id == user_id,
                        UserFavourite.place_id.in_(restaurant_ids),
                    )
                    .all()
                )
                favourite_ids = set(f[0] for f in favourites)
                for r in restaurants['data']:
                    r['is_favorite'] = r['element_id'] in favourite_ids
            else:
                for r in restaurants['data']:
                    r['is_favorite'] = False
            return restaurants, 200
    except Exception as e:
        logger.warning('Redis is not available to get data: %s', e)

    count_query = 'MATCH (r:Restaurant) RETURN count(r) AS total_count'
    total_count_result = execute_neo4j_query(count_query)
    total_count = total_count_result[0]['total_count']

    restaurants_query = """
    MATCH (r:Restaurant)
    OPTIONAL MATCH (r)-[:HAS_PRICE_LEVEL]->(pl:PriceLevel)
    OPTIONAL MATCH (r)-[:LOCATED_IN]->(c:City)
    OPTIONAL MATCH (r)-[:HAS_CUISINE]->(cu:Cuisine)
    OPTIONAL MATCH (r)-[:SERVES_MEAL]->(mt:MealType)
    OPTIONAL MATCH (r)-[:HAS_FEATURE]->(f:Feature)
    WITH r, c, pl, collect(DISTINCT cu.name) AS cuisines, collect(DISTINCT mt.name) AS meal_types, collect(DISTINCT f.name) AS features
    RETURN r, elementId(r) AS element_id, collect(DISTINCT pl.level) AS price_levels, c AS city, cuisines, meal_types, features
    ORDER BY r.raw_ranking DESC
    SKIP $offset
    LIMIT $size
    """

    result = execute_neo4j_query(
        restaurants_query, {'offset': offset, 'size': size}
    )
    restaurants_data = _process_restaurant_results(result, user_id)

    response = create_paging(
        data=ShortRestaurantSchema(many=True).dump(restaurants_data),
        page=page,
        size=size,
        offset=offset,
        total_count=total_count,
    )

    try:
        redis.set(cache_key, json.dumps(response), ex=21600)
    except Exception as e:
        logger.warning('Redis is not available to set data: %s', e)

    return response, 200


def _search_restaurants(search, page, size, offset, user_id):
    """Search restaurants by name."""
    redis = get_redis()
    cache_key = f'restaurants:page={page}:size={size}:search={search}'
    try:
        cached_response = redis.get(cache_key)
        if cached_response:
            restaurants = json.loads(cached_response)
            # Add is_favorite field if user_id exists
            if user_id:
                restaurant_ids = [r['element_id'] for r in restaurants['data']]
                favourites = (
                    db.session.query(UserFavourite.place_id)
                    .filter(
                        UserFavourite.user_id == user_id,
                        UserFavourite.place_id.in_(restaurant_ids),
                    )
                    .all()
                )
                favourite_ids = set(f[0] for f in favourites)
                for r in restaurants['data']:
                    r['is_favorite'] = r['element_id'] in favourite_ids
            else:
                for r in restaurants['data']:
                    r['is_favorite'] = False
            return restaurants, 200
    except Exception as e:
        logger.warning('Redis is not available to get data: %s', e)

    query_params = {'offset': offset, 'size': size, 'search': search}

    count_query = """
    MATCH (r:Restaurant)
    WHERE toLower(r.name) CONTAINS toLower($search)
    RETURN count(r) AS total_count
    """
    total_count_result = execute_neo4j_query(count_query, query_params)
    total_count = total_count_result[0]['total_count']

    restaurants_query = """
    MATCH (r:Restaurant)
    WHERE toLower(r.name) CONTAINS toLower($search)
    OPTIONAL MATCH (r)-[:HAS_PRICE_LEVEL]->(pl:PriceLevel)
    OPTIONAL MATCH (r)-[:LOCATED_IN]->(c:City)
    OPTIONAL MATCH (r)-[:HAS_CUISINE]->(cu:Cuisine)
    OPTIONAL MATCH (r)-[:SERVES_MEAL]->(mt:MealType)
    OPTIONAL MATCH (r)-[:HAS_FEATURE]->(f:Feature)
    WITH r, c, pl, collect(DISTINCT cu.name) AS cuisines, collect(DISTINCT mt.name) AS meal_types, collect(DISTINCT f.name) AS features
    RETURN r, elementId(r) AS element_id, collect(DISTINCT pl.level) AS price_levels, c AS city, cuisines, meal_types, features
    ORDER BY r.raw_ranking DESC
    SKIP $offset
    LIMIT $size
    """
    result = execute_neo4j_query(restaurants_query, query_params)
    restaurants_data = _process_restaurant_results(result, user_id)

    response = create_paging(
        data=ShortRestaurantSchema(many=True).dump(restaurants_data),
        page=page,
        size=size,
        offset=offset,
        total_count=total_count,
    )

    try:
        redis.set(cache_key, json.dumps(response), ex=21600)
    except Exception as e:
        logger.warning('Redis is not available to set data: %s', e)

    return response, 200


def _filter_restaurants(
    rating,
    cuisines,
    meal_types,
    features,
    dietary_restrictions,
    dishes,
    page,
    size,
    offset,
    user_id,
):
    """Filter restaurants based on various criteria."""
    redis = get_redis()

    # Build a dynamic cache key
    cache_parts = [f'page={page}', f'size={size}', 'filter']
    if rating is not None:
        cache_parts.append(f'rating={rating}')
    if cuisines:
        cache_parts.append(f"cuisines={','.join(sorted(cuisines))}")
    if meal_types:
        cache_parts.append(f"meal_types={','.join(sorted(meal_types))}")
    if features:
        cache_parts.append(f"features={','.join(sorted(features))}")
    if dietary_restrictions:
        cache_parts.append(
            f"dietary_restrictions={','.join(sorted(dietary_restrictions))}"
        )
    if dishes:
        cache_parts.append(f"dishes={','.join(sorted(dishes))}")
    cache_key = f'restaurants:{":".join(cache_parts)}'

    # Check Redis cache first
    try:
        cached_response = redis.get(cache_key)
        if cached_response:
            restaurants = json.loads(cached_response)
            # Add is_favorite field for authenticated users
            if user_id:
                restaurant_ids = [r['element_id'] for r in restaurants['data']]
                favourites = (
                    db.session.query(UserFavourite.place_id)
                    .filter(
                        UserFavourite.user_id == user_id,
                        UserFavourite.place_id.in_(restaurant_ids),
                    )
                    .all()
                )
                favourite_ids = set(f[0] for f in favourites)
                for r in restaurants['data']:
                    r['is_favorite'] = r['element_id'] in favourite_ids
            else:
                for r in restaurants['data']:
                    r['is_favorite'] = False
            return restaurants, 200
    except Exception as e:
        logger.warning('Redis cache unavailable: %s', e)

    # Build the query dynamically
    query_params = {'offset': offset, 'size': size}
    where_clauses = []

    if rating is not None:
        where_clauses.append('r.rating >= $rating')
        query_params['rating'] = rating
    if cuisines:
        where_clauses.append(
            'ALL(c_name IN $cuisines WHERE (r)-[:HAS_CUISINE]->(:Cuisine {name: c_name}))'
        )
        query_params['cuisines'] = cuisines
    if meal_types:
        where_clauses.append(
            'ALL(mt_name IN $meal_types WHERE (r)-[:SERVES_MEAL]->(:MealType {name: mt_name}))'
        )
        query_params['meal_types'] = meal_types
    if features:
        where_clauses.append(
            'ALL(f_name IN $features WHERE (r)-[:HAS_FEATURE]->(:Feature {name: f_name}))'
        )
        query_params['features'] = features
    if dietary_restrictions:
        where_clauses.append(
            'ALL(dr_name IN $dietary_restrictions WHERE dr_name IN r.dietary_restrictions)'
        )
        query_params['dietary_restrictions'] = dietary_restrictions
    if dishes:
        where_clauses.append(
            'ALL(d_name IN $dishes WHERE d_name IN r.dishes)'
        )
        query_params['dishes'] = dishes

    where_str = ''
    if where_clauses:
        where_str = 'WHERE ' + ' AND '.join(where_clauses)

    count_query = f"""
    MATCH (r:Restaurant)
    {where_str}
    RETURN count(r) AS total_count
    """
    total_count_result = execute_neo4j_query(count_query, query_params)
    total_count = total_count_result[0]['total_count'] if total_count_result else 0

    restaurants_query = f"""
    MATCH (r:Restaurant)
    {where_str}
    OPTIONAL MATCH (r)-[:HAS_PRICE_LEVEL]->(pl:PriceLevel)
    OPTIONAL MATCH (r)-[:LOCATED_IN]->(c:City)
    OPTIONAL MATCH (r)-[:HAS_CUISINE]->(cu:Cuisine)
    OPTIONAL MATCH (r)-[:SERVES_MEAL]->(mt:MealType)
    OPTIONAL MATCH (r)-[:HAS_FEATURE]->(f:Feature)
    WITH r, c, pl, collect(DISTINCT cu.name) AS cuisines, collect(DISTINCT mt.name) AS meal_types, collect(DISTINCT f.name) AS features
    RETURN r, elementId(r) AS element_id, collect(DISTINCT pl.level) AS price_levels, c AS city, cuisines, meal_types, features
    ORDER BY r.raw_ranking DESC
    SKIP $offset
    LIMIT $size
    """
    result = execute_neo4j_query(restaurants_query, query_params)
    restaurants_data = _process_restaurant_results(result, user_id)

    response = create_paging(
        data=ShortRestaurantSchema(many=True).dump(restaurants_data),
        page=page,
        size=size,
        offset=offset,
        total_count=total_count,
    )

    try:
        redis.set(cache_key, json.dumps(response), ex=21600)
    except Exception as e:
        logger.warning('Redis cache set failed: %s', e)

    return response, 200


@blueprint.get('/<restaurant_id>/')
@jwt_required(optional=True)
def get_restaurant(restaurant_id):
    schema = RestaurantSchema()

    user_id = None
    try:
        user_id = get_jwt_identity()
    except Exception:
        pass

    # Check if the result is cached
    redis = get_redis()
    cache_key = f'restaurants:{restaurant_id}'
    try:
        cached_response = redis.get(cache_key)
        if cached_response:
            restaurant = json.loads(cached_response)
            # Add is_favorite field if user is authenticated
            user_id = None
            try:
                user_id = get_jwt_identity()
            except Exception:
                pass
            if user_id:
                is_favorite = (
                    db.session.query(UserFavourite)
                    .filter_by(user_id=user_id, place_id=restaurant_id)
                    .first()
                    is not None
                )
                restaurant['is_favorite'] = is_favorite
            else:
                restaurant['is_favorite'] = False
            return schema.dump(restaurant), 200
    except Exception as e:
        logger.exception(e)
        logger.warning('Redis is not available to get data: %s', e)

    # Get the restaurant details along with features, cuisines, price_levels, meal_types, and city
    result = execute_neo4j_query(
        """
        MATCH (r:Restaurant)
        WHERE elementId(r) = $restaurant_id
        OPTIONAL MATCH (r)-[:HAS_FEATURE]->(f:Feature)
        OPTIONAL MATCH (r)-[:HAS_PRICE_LEVEL]->(pl:PriceLevel)
        OPTIONAL MATCH (r)-[:HAS_CUISINE]->(cu:Cuisine)
        OPTIONAL MATCH (r)-[:SERVES_MEAL]->(mt:MealType)
        OPTIONAL MATCH (r)-[:LOCATED_IN]->(c:City)
        RETURN
            r,
            elementId(r) AS element_id,
            collect(DISTINCT f.name) AS features,
            collect(DISTINCT pl.level) AS price_levels,
            collect(DISTINCT cu.name) AS cuisines,
            collect(DISTINCT mt.name) AS meal_types,
            c AS city
        """,
        {'restaurant_id': restaurant_id},
    )

    if not result:
        return {'error': 'Restaurant not found'}, 404

    restaurant = result[0]['r']
    restaurant['element_id'] = result[0]['element_id']
    restaurant['features'] = result[0]['features']
    restaurant['price_levels'] = result[0]['price_levels']
    restaurant['cuisines'] = result[0]['cuisines']
    restaurant['meal_types'] = result[0]['meal_types']
    if result[0]['city']:
        restaurant['city'] = result[0]['city']

    # Parse hours JSON if stored as string
    if 'hours' in restaurant and isinstance(restaurant['hours'], str):
        try:
            restaurant['hours'] = json.loads(restaurant['hours'])
        except Exception:
            restaurant['hours'] = None

    # Add is_favorite field
    user_id = None
    try:
        user_id = get_jwt_identity()
    except Exception:
        pass
    if user_id:
        is_favorite = (
            db.session.query(UserFavourite)
            .filter_by(user_id=user_id, place_id=restaurant_id)
            .first()
            is not None
        )
        restaurant['is_favorite'] = is_favorite
    else:
        restaurant['is_favorite'] = False

    # Cache the response for 6 hours (without is_favorite, since it's user-specific)
    try:
        redis.set(cache_key, json.dumps(restaurant), ex=21600)
    except Exception as e:
        logger.warning('Redis is not available to set data: %s', e)

    return schema.dump(restaurant), 200


@blueprint.delete('/<restaurant_id>/')
def delete_restaurant(restaurant_id):
    """
    Delete a restaurant and all related data.
    
    This endpoint will:
    - Remove the restaurant from Neo4j database
    - Delete all user reviews of this restaurant
    - Remove restaurant from user favorites
    - Remove restaurant from user trips
    - Clear all related cache entries
    """
    try:
        # First check if restaurant exists and is actually a restaurant
        result = execute_neo4j_query(
            """
            MATCH (r:Restaurant)
            WHERE elementId(r) = $restaurant_id
            RETURN r.name as name, r.type as type
            """,
            {'restaurant_id': restaurant_id}
        )
        
        if not result:
            return {'error': 'Restaurant not found'}, 404
        
        restaurant_name = result[0]['name']
        
        # Use the comprehensive deletion utility
        deletion_summary = delete_place_and_related_data(restaurant_id)
        
        # Check if deletion was successful
        if not deletion_summary['place_deleted']:
            return {
                'error': 'Failed to delete restaurant',
                'details': deletion_summary['errors']
            }, 500
        
        # Prepare success response
        response = {
            'message': f'Restaurant "{restaurant_name}" has been successfully deleted',
            'summary': {
                'restaurant_deleted': deletion_summary['place_deleted'],
                'reviews_deleted': deletion_summary['reviews_deleted'],
                'favorites_removed': deletion_summary['favorites_deleted'],
                'trips_updated': deletion_summary['trips_updated'],
                'cache_cleared': deletion_summary['cache_cleared']
            }
        }
        
        # Include any non-critical errors as warnings
        if deletion_summary['errors']:
            response['warnings'] = deletion_summary['errors']
        
        return response, 200
        
    except Exception as e:
        logger.error(f"Error deleting restaurant {restaurant_id}: {str(e)}")
        return {
            'error': 'An unexpected error occurred while deleting the restaurant',
            'details': str(e)
        }, 500
