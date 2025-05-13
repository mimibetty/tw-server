import json
import logging

from flask import Blueprint, request
from marshmallow import ValidationError, fields, validates

from app.extensions import CamelCaseSchema
from app.utils import create_paging, execute_neo4j_query, get_redis

logger = logging.getLogger(__name__)
blueprint = Blueprint('hotels', __name__, url_prefix='/hotels')


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


class ShortHotelSchema(CamelCaseSchema):
    created_at = fields.String(dump_only=True)
    element_id = fields.String(dump_only=True)
    city = fields.Nested(AttachCitySchema, required=True)
    email = fields.Email(required=True, allow_none=True)
    image = fields.String(required=True)
    latitude = fields.Float(required=True)
    longitude = fields.Float(required=True)
    name = fields.String(required=True)
    price_levels = fields.List(fields.String(), required=True)
    rating = fields.Float(required=True)
    rating_histogram = fields.List(fields.Integer(), required=True)
    raw_ranking = fields.Float(required=True, load_only=True)
    street = fields.String(required=True)
    type = fields.String(dump_only=True)

    @validates('rating')
    def validate_rating(self, value: float):
        if value < 0 or value > 5:
            raise ValidationError('Rating must be between 0 and 5')
        return value

    @validates('rating_histogram')
    def validate_rating_histogram(self, value: list):
        if len(value) != 5:
            raise ValidationError(
                'Rating histogram must contain exactly 5 integers'
            )
        if not all(isinstance(i, int) and i > 0 for i in value):
            raise ValidationError(
                'Rating histogram must be a list of 5 positive integers'
            )
        return value

    @validates('raw_ranking')
    def validate_raw_ranking(self, value: float):
        if value < 0 or value > 5:
            raise ValidationError('Raw ranking must be between 0 and 5')
        return value


class HotelSchema(ShortHotelSchema):
    # Common fields
    phone = fields.String(required=True, allow_none=True)
    photos = fields.List(fields.String(), required=True)
    website = fields.String(required=True, allow_none=True)

    # Specific fields
    ai_reviews_summary = fields.String(required=True)
    description = fields.String(required=True, allow_none=True)
    features = fields.List(fields.String(), required=True)
    hotel_class = fields.String(required=True)
    number_of_rooms = fields.Integer(required=True)

    @validates('number_of_rooms')
    def validate_number_of_rooms(self, value: int):
        if value <= 0:
            raise ValidationError('Number of rooms must be a positive integer')
        return value


@blueprint.post('/')
def create_hotel():
    data = HotelSchema().load(request.json)

    # Extract city postal code from the request data
    city_postal_code = data['city']['postal_code']

    # Create the hotel and attach it to the city in Neo4j
    result = execute_neo4j_query(
        """
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
                    type: 'HOTEL',
                    website: $website,
                    created_at:
                        apoc.date.format(timestamp(), 'ms', 'yyyy-MM-dd HH:mm', 'GMT+7')
                })
        MERGE (h)-[:LOCATED_IN]->(c)

        // Handle features
        WITH h, c, $features AS features
        UNWIND features AS feature_name
        MERGE (a:Feature {name: feature_name})
        MERGE (h)-[:HAS_FEATURE]->(a)

        // Handle hotel_class
        WITH h, c, $hotel_class AS hotel_class
        MERGE (hc:HotelClass {name: hotel_class})
        MERGE (h)-[:BELONGS_TO_CLASS]->(hc)

        // Handle price_levels
        WITH h, c, $price_levels AS price_levels
        UNWIND price_levels AS price_level
        MERGE (pl:PriceLevel {level: price_level})
        MERGE (h)-[:HAS_PRICE_LEVEL]->(pl)

        // Return hotel with related data
        RETURN
            h,
            elementId(h) AS element_id,
            [(h)-[:BELONGS_TO_CLASS]->(hc:HotelClass) | hc.name ][0] AS hotel_class,
            c
        """,
        {
            'postal_code': city_postal_code,
            'name': data['name'],
            'image': data['image'],
            'latitude': data['latitude'],
            'longitude': data['longitude'],
            'photos': data['photos'],
            'price_levels': data['price_levels'],
            'rating': data['rating'],
            'rating_histogram': data['rating_histogram'],
            'raw_ranking': data['raw_ranking'],
            'ai_reviews_summary': data['ai_reviews_summary'],
            'features': data['features'],
            'description': data['description'],
            'email': data['email'],
            'hotel_class': data['hotel_class'],
            'number_of_rooms': data['number_of_rooms'],
            'phone': data['phone'],
            'website': data['website'],
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
    return ShortHotelSchema().dump(hotel), 201


@blueprint.get('/')
def get_hotels():
    # Get query parameters for pagination
    page = request.args.get('page', default=1, type=int)
    size = request.args.get('size', default=10, type=int)
    offset = (page - 1) * size

    # Check if the result is cached
    redis = get_redis()
    cache_key = f'hotels:page={page}:size={size}'
    cached_response = redis.get(cache_key)
    if cached_response:
        return json.loads(cached_response), 200

    # Get the total count of hotels
    total_count_result = execute_neo4j_query(
        """
        MATCH (h:Hotel)
        RETURN count(h) AS total_count
        """
    )
    total_count = total_count_result[0]['total_count']

    # Get the hotels with pagination
    result = execute_neo4j_query(
        """
        MATCH (h:Hotel)
        RETURN h, elementId(h) AS element_id
        ORDER BY h.raw_ranking DESC
        SKIP $offset
        LIMIT $size
        """,
        {'offset': offset, 'size': size},
    )

    # Add element_id to each hotel record
    for record in result:
        record['h']['element_id'] = record['element_id']
        del record['element_id']

    # Create paginated response
    response = create_paging(
        data=ShortHotelSchema(many=True).dump(
            [record['h'] for record in result]
        ),
        page=page,
        size=size,
        offset=offset,
        total_count=total_count,
    )

    # Cache the response for 6 hours
    redis.set(cache_key, json.dumps(response), ex=21600)

    return response, 200


@blueprint.get('/<hotel_id>')
def get_hotel(hotel_id):
    # Check if the result is cached
    redis = get_redis()
    cache_key = f'hotels:{hotel_id}'
    cached_response = redis.get(cache_key)
    if cached_response:
        return json.loads(cached_response), 200

    # Get the hotel details along with features, price_levels, and hotel_class
    result = execute_neo4j_query(
        """
        MATCH (h:Hotel)
        WHERE elementId(h) = $hotel_id
        OPTIONAL MATCH (h)-[:HAS_FEATURE]->(f:Feature)
        OPTIONAL MATCH (h)-[:HAS_PRICE_LEVEL]->(pl:PriceLevel)
        OPTIONAL MATCH (h)-[:BELONGS_TO_CLASS]->(hc:HotelClass)
        RETURN
            h,
            elementId(h) AS element_id,
            collect(DISTINCT f.name) AS features,
            collect(DISTINCT pl.level) AS price_levels,
            hc.name AS hotel_class
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

    # Cache the response for 6 hours
    redis.set(cache_key, json.dumps(hotel), ex=21600)

    return HotelSchema().dump(hotel), 200
