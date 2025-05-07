import uuid
from datetime import datetime, timezone
import requests
from flask import Blueprint, request
from app.schemas.hotels import HotelSchema
from app.utils.response import APIResponse
from app.utils import execute_neo4j_query

bp = Blueprint('hotels', __name__, url_prefix='/hotels')

@bp.post('')
def create_hotel():
    data = request.json.copy()
    # Convert ratingHistogram to rating_histogram (list of int)
    if 'ratingHistogram' in data:
        rh = data['ratingHistogram']
        data['rating_histogram'] = [
            rh.get('count1', 0),
            rh.get('count2', 0),
            rh.get('count3', 0),
            rh.get('count4', 0),
            rh.get('count5', 0),
        ]
        del data['ratingHistogram']
    # Clean up address field: remove ', Da Nang 550000 Vietnam' if present
    if 'address' in data and isinstance(data['address'], str):
        suffix = ', Da Nang 550000 Vietnam'
        if data['address'].endswith(suffix):
            data['address'] = data['address'][:-len(suffix)].rstrip(', ')
    # Remove fields not in schema
    for field in ['rating', 'numberOfReviews', 'addressObj']:
        data.pop(field, None)
    schema = HotelSchema()
    inputs = schema.load(data)
    return APIResponse.success(data=inputs, status=201)

@bp.post('/bulk')
def bulk_insert_hotels():
    """
    Fetch 10 hotels from a resource and insert them into Neo4j under city postal_code '550000',
    as children of the hotels category.
    Returns a summary dict.
    """
    url = "https://api.apify.com/v2/datasets/mm4bRWRtil7de60mo/items?clean=true&fields=amenities,photos,aiReviewsSummary,ratingHistogram,categoryReviewScores,image,webUrl,email,numberOfReviews,hotelClass,priceRange,description,priceLevel,addressObj,localName,travelerChoiceAward,website,rawRanking,numberOfRooms,whatsAppRedirectUrl,longitude,latitude,address,name,phone&format=json"
    response = requests.get(url)
    data = response.json()
    if not data:
        return APIResponse.error('No data from API', status=400)
    data = data[:20]
    print(f"Fetched {len(data)} hotels from API")
    # Find hotels category node for city 550000
    result = execute_neo4j_query(
        '''
        MATCH (c:City {postal_code: $postal_code})-[:HAS_CATEGORY]->(cat:Category {name: "hotels"})
        RETURN cat
        ''',
        {'postal_code': '550000'}
    )
    if not result:
        return APIResponse.error('hotels category not found for city 550000', status=404)
    category_id = result[0]['cat']['id']
    inserted = 0
    errors = []
    schema = HotelSchema()
    for loc in data:
        try:
            # Convert ratingHistogram to rating_histogram (list of int)
            rating_histogram = loc.get('ratingHistogram') or {}
            rating_histogram_schema = [
                rating_histogram.get('count1', 0),
                rating_histogram.get('count2', 0),
                rating_histogram.get('count3', 0),
                rating_histogram.get('count4', 0),
                rating_histogram.get('count5', 0),
            ]
            schema_input = dict(loc)
            schema_input['rating_histogram'] = rating_histogram_schema
            schema_input.pop('ratingHistogram', None)
            # Remove addressObj completely
            schema_input.pop('addressObj', None)
            # Clean up address field: remove ', Da Nang 550000 Vietnam' if present
            if 'address' in schema_input and isinstance(schema_input['address'], str):
                suffix = ', Da Nang 550000 Vietnam'
                if schema_input['address'].endswith(suffix):
                    schema_input['address'] = schema_input['address'][:-len(suffix)].rstrip(', ')
            # Remove fields not in schema
            for field in ['rating', 'numberOfReviews', 'addressObj']:
                schema_input.pop(field, None)
            # Validate with schema
            hotel_data = schema.load(schema_input)
            hotel_id = str(uuid.uuid4())
            created_at = datetime.now(timezone.utc).isoformat()
            execute_neo4j_query(
                '''
                MATCH (cat:Category {id: $category_id})
                MERGE (h:Hotel {
                    name: $name,
                    longitude: $longitude,
                    latitude: $latitude
                })
                ON CREATE SET
                    h.id = $id,
                    h.created_at = $created_at,
                    h.amenities = $amenities,
                    h.photos = $photos,
                    h.aiReviewsSummary = $aiReviewsSummary,
                    h.image = $image,
                    h.webUrl = $webUrl,
                    h.email = $email,
                    h.hotelClass = $hotelClass,
                    h.priceRange = $priceRange,
                    h.description = $description,
                    h.localAddress = $localAddress,
                    h.priceLevel = $priceLevel,
                    h.addressObj = $addressObj,
                    h.localName = $localName,
                    h.travelerChoiceAward = $travelerChoiceAward,
                    h.website = $website,
                    h.rawRanking = $rawRanking,
                    h.numberOfRooms = $numberOfRooms,
                    h.whatsAppRedirectUrl = $whatsAppRedirectUrl,
                    h.address = $address,
                    h.phone = $phone,
                    h.rating_histogram = $rating_histogram
                ON MATCH SET
                    h.amenities = $amenities,
                    h.photos = $photos,
                    h.aiReviewsSummary = $aiReviewsSummary,
                    h.image = $image,
                    h.webUrl = $webUrl,
                    h.email = $email,
                    h.hotelClass = $hotelClass,
                    h.priceRange = $priceRange,
                    h.description = $description,
                    h.localAddress = $localAddress,
                    h.priceLevel = $priceLevel,
                    h.addressObj = $addressObj,
                    h.localName = $localName,
                    h.travelerChoiceAward = $travelerChoiceAward,
                    h.website = $website,
                    h.rawRanking = $rawRanking,
                    h.numberOfRooms = $numberOfRooms,
                    h.whatsAppRedirectUrl = $whatsAppRedirectUrl,
                    h.address = $address,
                    h.phone = $phone,
                    h.rating_histogram = $rating_histogram
                MERGE (cat)-[:HAS_PLACE]->(h)
                ''',
                {
                    'category_id': category_id,
                    'id': hotel_id,
                    'created_at': created_at,
                    'name': hotel_data.get('name'),
                    'longitude': hotel_data.get('longitude'),
                    'latitude': hotel_data.get('latitude'),
                    'amenities': hotel_data.get('amenities'),
                    'photos': hotel_data.get('photos'),
                    'aiReviewsSummary': hotel_data.get('aiReviewsSummary'),
                    'image': hotel_data.get('image'),
                    'webUrl': hotel_data.get('webUrl'),
                    'email': hotel_data.get('email'),
                    'hotelClass': hotel_data.get('hotelClass'),
                    'priceRange': hotel_data.get('priceRange'),
                    'description': hotel_data.get('description'),
                    'localAddress': hotel_data.get('localAddress'),
                    'priceLevel': hotel_data.get('priceLevel'),
                    'addressObj': hotel_data.get('addressObj'),
                    'localName': hotel_data.get('localName'),
                    'travelerChoiceAward': hotel_data.get('travelerChoiceAward'),
                    'website': hotel_data.get('website'),
                    'rawRanking': hotel_data.get('rawRanking'),
                    'numberOfRooms': hotel_data.get('numberOfRooms'),
                    'whatsAppRedirectUrl': hotel_data.get('whatsAppRedirectUrl'),
                    'address': hotel_data.get('address'),
                    'phone': hotel_data.get('phone'),
                    'rating_histogram': hotel_data.get('rating_histogram'),
                }
            )
            inserted += 1
        except Exception as e:
            errors.append(f"{loc.get('name')}: {e}")
    return APIResponse.success(data={'inserted': inserted, 'errors': errors}, status=200)

@bp.get('')
def get_hotels():
    page = max(request.args.get('page', default=1, type=int), 1)
    per_page = min(request.args.get('per_page', default=10, type=int), 50)
    sort_order = request.args.get('order', default='desc', type=str).lower()
    sort_order = 'ASC' if sort_order == 'asc' else 'DESC'
    total_records_result = execute_neo4j_query(
        'MATCH (h:Hotel) RETURN count(h) as total_records'
    )
    results = execute_neo4j_query(
        f"""
        MATCH (h:Hotel)
        RETURN h
        ORDER BY h.rawRanking {sort_order}
        SKIP $offset LIMIT $limit
        """,
        {'offset': (page - 1) * per_page, 'limit': per_page},
    )
    schema = HotelSchema()
    hotels = []
    for item in results:
        hotel = schema.dump(item.get('h'))
        rh = hotel.get('rating_histogram')
        if rh and isinstance(rh, list) and len(rh) == 5:
            total = sum(rh)
            if total > 0:
                overall_rating = sum((i + 1) * rh[i] for i in range(5)) / total
            else:
                overall_rating = None
        else:
            overall_rating = None
        hotel['overall_rating'] = overall_rating
        hotels.append(hotel)
    return APIResponse.paginate(
        data=hotels,
        page=page,
        per_page=per_page,
        total_records=total_records_result[0]['total_records'],
    )
