import json
import logging

from flask import Blueprint, request
from marshmallow import ValidationError, fields, pre_load, validates

from app.extensions import CamelCaseSchema
from app.utils import create_paging, execute_neo4j_query, get_redis

logger = logging.getLogger(__name__)
blueprint = Blueprint('restaurants', __name__, url_prefix='/restaurants')


class SimplifiedHourSchema(CamelCaseSchema):
    open = fields.String(required=True)
    close = fields.String(required=True)


class HoursSchema(CamelCaseSchema):
    monday = fields.Nested(SimplifiedHourSchema, allow_none=True)
    tuesday = fields.Nested(SimplifiedHourSchema, allow_none=True)
    wednesday = fields.Nested(SimplifiedHourSchema, allow_none=True)
    thursday = fields.Nested(SimplifiedHourSchema, allow_none=True)
    friday = fields.Nested(SimplifiedHourSchema, allow_none=True)
    saturday = fields.Nested(SimplifiedHourSchema, allow_none=True)
    sunday = fields.Nested(SimplifiedHourSchema, allow_none=True)
    timezone = fields.String(allow_none=True)


class AttachCitySchema(CamelCaseSchema):
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


class ShortRestaurantSchema(CamelCaseSchema):
    created_at = fields.String(dump_only=True)
    element_id = fields.String(dump_only=True)
    city = fields.Nested(AttachCitySchema, required=True)
    email = fields.Email(required=False, allow_none=True)
    image = fields.String(required=True)
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
        # Set default rating_histogram to [0,0,0,0,0] if not provided
        if 'rating_histogram' not in data and 'ratingHistogram' not in data:
            data['ratingHistogram'] = [0, 0, 0, 0, 0]
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
        elif (
            'ratingHistogram' in data
            and isinstance(data['ratingHistogram'], list)
            and len(data['ratingHistogram']) == 5
        ):
            rh = data['ratingHistogram']
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
    # Common fields
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

    def on_bind_field(self, field_name, field_obj):
        super().on_bind_field(field_name, field_obj)


@blueprint.post('/')
def create_restaurant():
    data = RestaurantSchema().load(request.json)

    # Extract city postal code from the request data
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
def get_restaurants():
    # Get query parameters for pagination
    page = request.args.get('page', default=1, type=int)
    size = request.args.get('size', default=10, type=int)
    offset = (page - 1) * size

    # Check if the result is cached
    redis = get_redis()
    cache_key = f'restaurants:page={page}:size={size}'
    try:
        cached_response = redis.get(cache_key)
        if cached_response:
            return json.loads(cached_response), 200
    except Exception as e:
        logger.warning('Redis is not available to get data: %s', e)

    # Get the total count of restaurants
    total_count_result = execute_neo4j_query(
        """
        MATCH (r:Restaurant)
        RETURN count(r) AS total_count
        """
    )
    total_count = total_count_result[0]['total_count']

    # Get the restaurants with pagination, their price_levels, and city
    result = execute_neo4j_query(
        """
        MATCH (r:Restaurant)
        OPTIONAL MATCH (r)-[:HAS_PRICE_LEVEL]->(pl:PriceLevel)
        OPTIONAL MATCH (r)-[:LOCATED_IN]->(c:City)
        RETURN r, elementId(r) AS element_id, collect(DISTINCT pl.level) AS price_levels, c AS city
        ORDER BY r.raw_ranking DESC
        SKIP $offset
        LIMIT $size
        """,
        {'offset': offset, 'size': size},
    )

    # Add element_id, price_levels, and city to each restaurant record
    for record in result:
        record['r']['element_id'] = record['element_id']
        record['r']['price_levels'] = record['price_levels']
        if record['city']:
            record['r']['city'] = record['city']
        del record['element_id']
        del record['price_levels']
        del record['city']

    # Create paginated response
    response = create_paging(
        data=ShortRestaurantSchema(many=True).dump(
            [record['r'] for record in result]
        ),
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


@blueprint.get('/<restaurant_id>/short-details')
def get_short_restaurant(restaurant_id):
    schema = ShortRestaurantSchema()

    # Check if the result is cached
    redis = get_redis()
    cache_key = f'restaurants:short-details:{restaurant_id}'
    try:
        cached_response = redis.get(cache_key)
        if cached_response:
            return schema.dump(json.loads(cached_response)), 200
    except Exception as e:
        logger.warning('Redis is not available to get data: %s', e)

    # Get the restaurant details along with price_levels and city
    result = execute_neo4j_query(
        """
        MATCH (r:Restaurant)
        WHERE elementId(r) = $restaurant_id
        OPTIONAL MATCH (r)-[:HAS_PRICE_LEVEL]->(pl:PriceLevel)
        OPTIONAL MATCH (r)-[:LOCATED_IN]->(c:City)
        RETURN r, elementId(r) AS element_id, collect(DISTINCT pl.level) AS price_levels, c AS city
        """,
        {'restaurant_id': restaurant_id},
    )

    if not result:
        return {'error': 'Restaurant not found'}, 404

    restaurant = result[0]['r']
    restaurant['element_id'] = result[0]['element_id']
    restaurant['price_levels'] = result[0]['price_levels']
    if result[0]['city']:
        restaurant['city'] = result[0]['city']

    # Cache the response for 6 hours
    try:
        redis.set(cache_key, json.dumps(restaurant), ex=21600)
    except Exception as e:
        logger.warning('Redis is not available to set data: %s', e)

    return schema.dump(restaurant), 200


@blueprint.get('/<restaurant_id>/details')
def get_restaurant(restaurant_id):
    schema = RestaurantSchema()

    # Check if the result is cached
    redis = get_redis()
    cache_key = f'restaurants:{restaurant_id}'
    try:
        cached_response = redis.get(cache_key)
        if cached_response:
            return schema.dump(json.loads(cached_response)), 200
    except Exception as e:
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

    # Cache the response for 6 hours
    try:
        redis.set(cache_key, json.dumps(restaurant), ex=21600)
    except Exception as e:
        logger.warning('Redis is not available to set data: %s', e)

    return schema.dump(restaurant), 200
