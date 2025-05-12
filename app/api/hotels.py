from flask import Blueprint, request
from marshmallow import ValidationError, fields, validates

from app.extensions import CamelCaseSchema
from app.utils import create_paging, execute_neo4j_query

blueprint = Blueprint('hotels', __name__, url_prefix='/hotels')


class CitySchema(CamelCaseSchema):
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


class HotelSchema(CamelCaseSchema):
    created_at = fields.String(dump_only=True)
    element_id = fields.String(dump_only=True)

    # Common fields
    city = fields.Nested(CitySchema)
    email = fields.Email(required=True, allow_none=True)
    image = fields.String(required=True)
    latitude = fields.Float(required=True)
    longitude = fields.Float(required=True)
    name = fields.String(required=True)
    phone = fields.String(required=True, allow_none=True)
    photos = fields.List(fields.String(), required=True)
    price_levels = fields.List(fields.String(), required=True)
    rating = fields.Float(required=True)
    rating_histogram = fields.List(fields.Integer(), required=True)
    raw_ranking = fields.Float(required=True)
    street = fields.String(required=True)
    type = fields.Constant('HOTEL', dump_only=True)
    website = fields.String(required=True, allow_none=True)

    # Specific fields
    ai_reviews_summary = fields.String(required=True)
    description = fields.String(required=True, allow_none=True)
    features = fields.List(fields.String(), required=True)
    hotel_class = fields.String(required=True)
    number_of_rooms = fields.Integer(required=True)

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

    @validates('number_of_rooms')
    def validate_number_of_rooms(self, value: int):
        if value <= 0:
            raise ValidationError('Number of rooms must be a positive integer')
        return value


@blueprint.post('/')
def create_hotel():
    schema = HotelSchema()
    data = schema.load(request.json)

    # Extract city postal code from the request data
    city_postal_code = data['city']['postal_code']

    # Create the hotel and attach it to the city in Neo4j
    result = execute_neo4j_query(
        """
        MATCH (c:City {postal_code: $postal_code})
        CREATE (h:Hotel {
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
            website: $website,
            created_at: timestamp()
        })
        MERGE (h)-[:LOCATED_IN]->(c)

        // Handle features
        WITH h, $features AS features
        UNWIND features AS feature_name
        MERGE (a:Feature {name: feature_name})
        MERGE (h)-[:HAS_FEATURE]->(a)

        // Handle hotel_class
        WITH h, $hotel_class AS hotel_class
        MERGE (hc:HotelClass {name: hotel_class})
        MERGE (h)-[:BELONGS_TO_CLASS]->(hc)

        // Handle price_levels
        WITH h, $price_levels AS price_levels
        UNWIND price_levels AS price_level
        MERGE (pl:PriceLevel {level: price_level})
        MERGE (h)-[:HAS_PRICE_LEVEL]->(pl)

        // Format created_at timestamp
        WITH h, apoc.date.format(h.created_at, 'ms', 'yyyy-MM-dd HH:mm', 'GMT+7') AS formatted_created_at
        SET h.created_at = formatted_created_at

        // Return hotel with related data
        RETURN h, elementId(h) AS element_id,
               [(h)-[:HAS_FEATURE]->(a:Feature) | a.name] AS features,
               [(h)-[:HAS_PRICE_LEVEL]->(pl:PriceLevel) | pl.level] AS price_levels,
               [(h)-[:BELONGS_TO_CLASS]->(hc:HotelClass) | hc.name][0] AS hotel_class
        ORDER BY features ASC, price_levels ASC
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

    hotel = result[0]['h']
    hotel['element_id'] = result[0]['element_id']
    hotel['features'] = result[0]['features']
    hotel['price_levels'] = result[0]['price_levels']
    hotel['hotel_class'] = result[0]['hotel_class']
    return schema.dump(hotel), 201


@blueprint.get('/')
def get_hotels():
    # Get pagination parameters from the request
    page = int(request.args.get('page', 1))
    size = int(request.args.get('size', 10))
    offset = (page - 1) * size

    # Query to get total count of hotels
    total_count_result = execute_neo4j_query(
        """
        MATCH (h:Hotel)
        RETURN count(h) AS total_count
        """
    )
    total_count = total_count_result[0]['total_count']

    # Query to get paginated hotels
    result = execute_neo4j_query(
        """
        MATCH (h:Hotel)-[:LOCATED_IN]->(c:City)
        RETURN h, elementId(h) AS element_id,
               [(h)-[:BELONGS_TO_CLASS]->(hc:HotelClass) | hc.name][0] AS hotel_class
        ORDER BY h.raw_ranking DESC
        SKIP $offset
        LIMIT $size
        """,
        {'offset': offset, 'size': size},
    )

    # Return empty list if no hotels found
    if not result:
        return create_paging([], page, size, offset, total_count), 200

    # Add the elementId and related data to each hotel
    hotels = []
    for record in result:
        hotel = record['h']
        hotel['element_id'] = record['element_id']
        hotel['hotel_class'] = record['hotel_class']

        # Get features and price levels
        features_result = execute_neo4j_query(
            """
            MATCH (h:Hotel)-[:HAS_FEATURE]->(a:Feature)
            WHERE elementId(h) = $hotel_id
            RETURN a.name AS feature
            """,
            {'hotel_id': hotel['element_id']},
        )
        hotel['features'] = [record['feature'] for record in features_result]

        price_levels_result = execute_neo4j_query(
            """
            MATCH (h:Hotel)-[:HAS_PRICE_LEVEL]->(pl:PriceLevel)
            WHERE elementId(h) = $hotel_id
            RETURN pl.level AS price_level
            """,
            {'hotel_id': hotel['element_id']},
        )
        hotel['price_levels'] = [
            record['price_level'] for record in price_levels_result
        ]
        hotels.append(hotel)

    # Create paginated response
    response = create_paging(
        data=HotelSchema(many=True).dump(hotels),
        page=page,
        size=size,
        offset=offset,
        total_count=total_count,
    )

    return response, 200
