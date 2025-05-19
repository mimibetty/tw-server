import json
import logging

from flask import Blueprint, request
from marshmallow import ValidationError, fields, pre_load, validates

from app.extensions import CamelCaseSchema
from app.utils import create_paging, execute_neo4j_query, get_redis

logger = logging.getLogger(__name__)
blueprint = Blueprint('things_to_do', __name__, url_prefix='/things-to-do')


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


class ShortThingToDoSchema(CamelCaseSchema):
    created_at = fields.String(dump_only=True)
    element_id = fields.String(dump_only=True)
    city = fields.Nested(AttachCitySchema, required=True)
    email = fields.Email(required=False, allow_none=True)
    image = fields.String(required=True)
    latitude = fields.Float(required=True)
    longitude = fields.Float(required=True)
    name = fields.String(required=True)
    rating = fields.Float(required=False, allow_none=True)
    rating_histogram = fields.List(
        fields.Integer(), required=False, default=list
    )
    raw_ranking = fields.Float(required=True, load_only=True)
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


class ThingToDoSchema(ShortThingToDoSchema):
    # Common fields
    phone = fields.String(required=False, allow_none=True)
    photos = fields.List(fields.String(), required=False, default=list)
    website = fields.String(required=False, allow_none=True)

    # Thing-to-do specific fields
    description = fields.String(required=False, allow_none=True)
    subtypes = fields.List(fields.String(), required=False, default=list)
    subcategories = fields.List(fields.String(), required=False, default=list)

    def on_bind_field(self, field_name, field_obj):
        super().on_bind_field(field_name, field_obj)


@blueprint.post('/')
def create_thing_to_do():
    schema = ThingToDoSchema()
    data = schema.load(request.json)

    # Extract city postal code from the request data
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
def get_things_to_do():
    # Get query parameters for pagination
    page = request.args.get('page', default=1, type=int)
    size = request.args.get('size', default=10, type=int)
    offset = (page - 1) * size
    sort_order = request.args.get('order', default='desc', type=str)
    sort_order = 'DESC' if sort_order.upper() == 'DESC' else 'ASC'

    # Check if the result is cached
    redis = get_redis()
    cache_key = f'things-to-do:page={page}:size={size}:order={sort_order}'
    try:
        cached_response = redis.get(cache_key)
        if cached_response:
            return json.loads(cached_response), 200
    except Exception as e:
        logger.warning('Redis is not available to get data: %s', e)

    # Get the total count of things to do
    total_count_result = execute_neo4j_query(
        """
        MATCH (t:ThingToDo)
        RETURN count(t) AS total_count
        """
    )
    total_count = total_count_result[0]['total_count']

    # Get the things to do with pagination, including city
    result = execute_neo4j_query(
        f"""
        MATCH (t:ThingToDo)-[:LOCATED_IN]->(c:City)
        OPTIONAL MATCH (t)-[:HAS_SUBTYPE]->(st:Subtype)
        OPTIONAL MATCH (t)-[:HAS_SUBCATEGORY]->(sc:Subcategory)
        WITH t, c, collect(DISTINCT st.name) AS subtypes, collect(DISTINCT sc.name) AS subcategories
        RETURN t, elementId(t) AS element_id, c, subtypes, subcategories
        ORDER BY t.raw_ranking {sort_order}
        SKIP $offset
        LIMIT $size
        """,
        {'offset': offset, 'size': size},
    )

    # Process each thing to do record
    processed_results = []
    for record in result:
        thing = record['t']
        thing['element_id'] = record['element_id']
        thing['subtypes'] = record['subtypes']
        thing['subcategories'] = record['subcategories']
        thing['city'] = record['c']

        # Calculate rating if not present
        if 'rating' not in thing or thing['rating'] is None:
            rh = thing.get('rating_histogram', [])
            if rh and isinstance(rh, list) and len(rh) == 5:
                total = sum(rh)
                if total > 0:
                    rating = sum((i + 1) * rh[i] for i in range(5)) / total
                    thing['rating'] = round(rating, 1)

        processed_results.append(thing)

    # Create paginated response
    response = create_paging(
        data=ThingToDoSchema(many=True).dump(processed_results),
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


@blueprint.get('/<thing_to_do_id>/short-details')
def get_short_thing_to_do(thing_to_do_id):
    schema = ShortThingToDoSchema()

    # Check if the result is cached
    redis = get_redis()
    cache_key = f'things-to-do:short-details:{thing_to_do_id}'
    try:
        cached_response = redis.get(cache_key)
        if cached_response:
            return schema.dump(json.loads(cached_response)), 200
    except Exception as e:
        logger.warning('Redis is not available to get data: %s', e)

    # Get the short details of the thing to do
    result = execute_neo4j_query(
        """
        MATCH (t:ThingToDo)
        WHERE elementId(t) = $thing_to_do_id
        RETURN t, elementId(t) AS element_id
        """,
        {'thing_to_do_id': thing_to_do_id},
    )

    if not result:
        return {'error': 'Thing to do not found'}, 404

    thing_to_do = result[0]['t']
    thing_to_do['element_id'] = result[0]['element_id']

    # Cache the response for 6 hours
    try:
        redis.set(cache_key, json.dumps(thing_to_do), ex=21600)
    except Exception as e:
        logger.warning('Redis is not available to set data: %s', e)

    return schema.dump(thing_to_do), 200


@blueprint.get('/<thing_to_do_id>/details')
def get_thing_to_do(thing_to_do_id):
    schema = ThingToDoSchema()

    # Check if the result is cached
    redis = get_redis()
    cache_key = f'things-to-do:{thing_to_do_id}'
    try:
        cached_response = redis.get(cache_key)
        if cached_response:
            return schema.dump(json.loads(cached_response)), 200
    except Exception as e:
        logger.warning('Redis is not available to get data: %s', e)

    # Get the thing to do details along with subtypes, subcategories
    result = execute_neo4j_query(
        """
        MATCH (t:ThingToDo)
        WHERE elementId(t) = $thing_to_do_id
        OPTIONAL MATCH (t)-[:HAS_SUBTYPE]->(st:Subtype)
        OPTIONAL MATCH (t)-[:HAS_SUBCATEGORY]->(sc:Subcategory)
        RETURN
            t,
            elementId(t) AS element_id,
            collect(DISTINCT st.name) AS subtypes,
            collect(DISTINCT sc.name) AS subcategories
        """,
        {'thing_to_do_id': thing_to_do_id},
    )

    if not result:
        return {'error': 'Thing to do not found'}, 404

    thing_to_do = result[0]['t']
    thing_to_do['element_id'] = result[0]['element_id']
    thing_to_do['subtypes'] = result[0]['subtypes']
    thing_to_do['subcategories'] = result[0]['subcategories']

    # Calculate rating if not present
    if 'rating' not in thing_to_do or thing_to_do['rating'] is None:
        rh = thing_to_do.get('rating_histogram', [])
        if rh and isinstance(rh, list) and len(rh) == 5:
            total = sum(rh)
            if total > 0:
                rating = sum((i + 1) * rh[i] for i in range(5)) / total
                thing_to_do['rating'] = round(rating, 1)

    # Cache the response for 6 hours
    try:
        redis.set(cache_key, json.dumps(thing_to_do), ex=21600)
    except Exception as e:
        logger.warning('Redis is not available to set data: %s', e)

    return schema.dump(thing_to_do), 200
