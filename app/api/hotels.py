import json
import logging

from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from marshmallow import ValidationError, fields, pre_load, validates

from app.extensions import ma
from app.models import UserFavourite, db
from app.utils import create_paging, execute_neo4j_query, get_redis

logger = logging.getLogger(__name__)
blueprint = Blueprint('hotels', __name__, url_prefix='/hotels')


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


class ShortHotelSchema(ma.Schema):
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
    street = fields.String(required=True, allow_none=True)
    type = fields.String(dump_only=True)
    is_favorite = fields.Boolean(dump_only=True, default=False)

    def on_bind_field(self, field_name, field_obj):
        super().on_bind_field(field_name, field_obj)

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


class HotelSchema(ShortHotelSchema):
    # Common fields
    phone = fields.String(required=False, allow_none=True)
    photos = fields.List(fields.String(), required=False, default=list)
    website = fields.String(required=False, allow_none=True)

    # Specific fields
    ai_reviews_summary = fields.String(required=False, allow_none=True)
    description = fields.String(required=False, allow_none=True)
    features = fields.List(fields.String(), required=False, default=list)
    hotel_class = fields.String(required=False, allow_none=True)
    number_of_rooms = fields.Integer(required=False)
    price_range = fields.String(required=False, allow_none=True)

    @validates('number_of_rooms')
    def validate_number_of_rooms(self, value: int):
        if value is not None and value <= 0:
            raise ValidationError('Number of rooms must be a positive integer')
        return value


@blueprint.post('/')
def create_hotel():
    data = HotelSchema().load(request.get_json())
    city_postal_code = data['city']['postal_code']

    # Get data with defaults for empty lists
    features = data.get('features', [])
    price_levels = data.get('price_levels', [])

    # Base query to create hotel
    query = """
    MATCH (c:City {postal_code: $postal_code})
    CREATE
        (h:Hotel
            {
                name: $name,
                image: $image,
                latitude: $latitude,
                longitude: $longitude,
                photos: $photos,
                rating: $rating,
                rating_histogram: $rating_histogram,
                raw_ranking: $raw_ranking,
                ai_reviews_summary: $ai_reviews_summary,
                description: $description,
                email: $email,
                number_of_rooms: $number_of_rooms,
                phone: $phone,
                street: $street,
                type: 'HOTEL',
                website: $website,
                price_range: $price_range,
                created_at:
                    apoc.date.format(timestamp(), 'ms', 'yyyy-MM-dd HH:mm', 'GMT+7')
            })
    MERGE (h)-[:LOCATED_IN]->(c)
    """

    # Add features relationship if features list is not empty
    if features:
        query += """
        WITH h, c
        UNWIND $features AS feature_name
        MERGE (a:Feature {name: feature_name})
        MERGE (h)-[:HAS_FEATURE]->(a)
        """

    # Add price_levels relationship if price_levels list is not empty
    if price_levels:
        query += """
        WITH h, c
        UNWIND $price_levels AS price_level
        MERGE (pl:PriceLevel {level: price_level})
        MERGE (h)-[:HAS_PRICE_LEVEL]->(pl)
        """

    # Add hotel class relationship if hotel_class is provided
    if data.get('hotel_class'):
        query += """
        WITH h, c
        MERGE (hc:HotelClass {name: $hotel_class})
        MERGE (h)-[:BELONGS_TO_CLASS]->(hc)
        """

    # Finalize query to return data
    query += """
    RETURN
        h,
        elementId(h) AS element_id,
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
            'ai_reviews_summary': data.get('ai_reviews_summary'),
            'description': data.get('description'),
            'email': data.get('email'),
            'phone': data.get('phone'),
            'website': data.get('website'),
            'number_of_rooms': data.get('number_of_rooms'),
            'hotel_class': data.get('hotel_class'),
            'price_range': data.get('price_range'),
            'features': features,
            'street': data['street'],
        },
    )

    if not result:
        return {'error': 'Failed to create hotel.'}, 400

    # Delete cached hotel data
    redis = get_redis()
    keys_to_delete = redis.keys('hotels:*')
    if keys_to_delete:
        redis.delete(*keys_to_delete)

    hotel = result[0]['h']
    hotel['element_id'] = result[0]['element_id']
    hotel['city'] = result[0]['c']

    # Add hotel_class to the response if it was provided
    if data.get('hotel_class'):
        hotel['hotel_class'] = data['hotel_class']

    # Add price_levels to the response
    hotel['price_levels'] = price_levels

    return ShortHotelSchema().dump(hotel), 201


@blueprint.get('/')
@jwt_required(optional=True)
def get_hotels():
    # Get query parameters for pagination
    page = request.args.get('page', default=1, type=int)
    size = request.args.get('size', default=10, type=int)
    offset = (page - 1) * size

    user_id = None
    try:
        user_id = get_jwt_identity()
    except Exception:
        pass

    # Check if the result is cached
    redis = get_redis()
    cache_key = f'hotels:page={page}:size={size}'
    try:
        cached_response = redis.get(cache_key)
        if cached_response:
            hotels = json.loads(cached_response)
            # Add is_favorite field if user_id exists
            if user_id:
                hotel_ids = [hotel['element_id'] for hotel in hotels['data']]
                favourites = (
                    db.session.query(UserFavourite.place_id)
                    .filter(
                        UserFavourite.user_id == user_id,
                        UserFavourite.place_id.in_(hotel_ids),
                    )
                    .all()
                )
                favourite_ids = set(f[0] for f in favourites)
                for hotel in hotels['data']:
                    hotel['is_favorite'] = hotel['element_id'] in favourite_ids
            else:
                for hotel in hotels['data']:
                    hotel['is_favorite'] = False
            return hotels, 200
    except Exception as e:
        logger.warning('Redis is not available to get data: %s', e)

    # Get the total count of hotels
    total_count_result = execute_neo4j_query(
        """
        MATCH (h:Hotel)
        RETURN count(h) AS total_count
        """
    )
    total_count = total_count_result[0]['total_count']

    # Get the hotels with pagination, their price_levels, and city
    result = execute_neo4j_query(
        """
        MATCH (h:Hotel)
        OPTIONAL MATCH (h)-[:HAS_PRICE_LEVEL]->(pl:PriceLevel)
        OPTIONAL MATCH (h)-[:LOCATED_IN]->(c:City)
        RETURN h, elementId(h) AS element_id, collect(DISTINCT pl.level) AS price_levels, c AS city
        ORDER BY h.raw_ranking DESC
        SKIP $offset
        LIMIT $size
        """,
        {'offset': offset, 'size': size},
    )

    # Add element_id, price_levels, and city to each hotel record
    for record in result:
        record['h']['element_id'] = record['element_id']
        record['h']['price_levels'] = record['price_levels']
        record['h']['city'] = record['city']
        del record['element_id']
        del record['price_levels']
        del record['city']

    hotels_data = [record['h'] for record in result]

    # Add is_favorite field
    if user_id:
        hotel_ids = [hotel['element_id'] for hotel in hotels_data]
        favourites = (
            db.session.query(UserFavourite.place_id)
            .filter(
                UserFavourite.user_id == user_id,
                UserFavourite.place_id.in_(hotel_ids),
            )
            .all()
        )
        favourite_ids = set(f[0] for f in favourites)
        for hotel in hotels_data:
            hotel['is_favorite'] = hotel['element_id'] in favourite_ids
    else:
        for hotel in hotels_data:
            hotel['is_favorite'] = False

    # Create paginated response
    response = create_paging(
        data=ShortHotelSchema(many=True).dump(hotels_data),
        page=page,
        size=size,
        offset=offset,
        total_count=total_count,
    )

    # Cache the response for 6 hours (without is_favorite, since it's user-specific)
    try:
        redis.set(cache_key, json.dumps(response), ex=21600)
    except Exception as e:
        logger.warning('Redis is not available to set data: %s', e)

    return response, 200


@blueprint.get('/<hotel_id>/')
@jwt_required(optional=True)
def get_hotel(hotel_id):
    schema = HotelSchema()

    user_id = None
    try:
        user_id = get_jwt_identity()
    except Exception:
        pass

    # Check if the result is cached
    redis = get_redis()
    cache_key = f'hotels:{hotel_id}'
    try:
        cached_response = redis.get(cache_key)
        if cached_response:
            hotel = json.loads(cached_response)
            # Add is_favorite field if user_id exists
            if user_id:
                favourite = (
                    db.session.query(UserFavourite)
                    .filter(
                        UserFavourite.user_id == user_id,
                        UserFavourite.place_id == hotel_id,
                    )
                    .first()
                )
                hotel['is_favorite'] = bool(favourite)
            else:
                hotel['is_favorite'] = False
            return schema.dump(hotel), 200
    except Exception as e:
        logger.warning('Redis is not available to get data: %s', e)

    # Get the hotel details along with features, price_levels, hotel_class, and city
    result = execute_neo4j_query(
        """
        MATCH (h:Hotel)
        WHERE elementId(h) = $hotel_id
        OPTIONAL MATCH (h)-[:HAS_FEATURE]->(f:Feature)
        OPTIONAL MATCH (h)-[:HAS_PRICE_LEVEL]->(pl:PriceLevel)
        OPTIONAL MATCH (h)-[:BELONGS_TO_CLASS]->(hc:HotelClass)
        OPTIONAL MATCH (h)-[:LOCATED_IN]->(c:City)
        RETURN
            h,
            elementId(h) AS element_id,
            collect(DISTINCT f.name) AS features,
            collect(DISTINCT pl.level) AS price_levels,
            hc.name AS hotel_class,
            c AS city
        """,
        {'hotel_id': hotel_id},
    )

    if not result:
        return {'error': 'Hotel not found'}, 404

    hotel = result[0]['h']
    hotel['element_id'] = result[0]['element_id']
    hotel['features'] = result[0]['features']
    hotel['price_levels'] = result[0]['price_levels']
    hotel['hotel_class'] = result[0]['hotel_class']
    hotel['city'] = result[0]['city']

    # Add is_favorite field
    if user_id:
        favourite = (
            db.session.query(UserFavourite)
            .filter(
                UserFavourite.user_id == user_id,
                UserFavourite.place_id == hotel_id,
            )
            .first()
        )
        hotel['is_favorite'] = bool(favourite)
    else:
        hotel['is_favorite'] = False

    # Cache the response for 6 hours (without is_favorite, since it's user-specific)
    try:
        redis.set(cache_key, json.dumps(hotel), ex=21600)
    except Exception as e:
        logger.warning('Redis is not available to set data: %s', e)

    return schema.dump(hotel), 200
