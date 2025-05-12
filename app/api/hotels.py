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
    
    # Process rating histogram - convert from object to list format
    if 'ratingHistogram' in data and isinstance(data['ratingHistogram'], dict):
        rh = data['ratingHistogram']
        data['ratingHistogram'] = [
            rh.get('count1', 0),
            rh.get('count2', 0),
            rh.get('count3', 0),
            rh.get('count4', 0),
            rh.get('count5', 0),
        ]
    
    # For backwards compatibility
    if 'rating_histogram' in data and 'ratingHistogram' not in data:
        data['ratingHistogram'] = data.pop('rating_histogram')
        
    # Clean up address field: it will be processed in the schema's pre_load method
    # Remove fields not in schema
    for field in ['rating', 'numberOfReviews', 'addressObj']:
        data.pop(field, None)
        
    schema = HotelSchema()
    inputs = schema.load(data)
    return APIResponse.success(data=inputs, status=201)


@bp.post('/bulk')
def bulk_insert_hotels():
    """
    Fetch hotels from a resource and insert them into Neo4j under city postal_code '550000',
    directly linking them to the city node. Also creates amenity nodes linked to each hotel.
    Returns a summary dict.
    """
    print('Starting bulk_insert_hotels')
    url = 'https://api.apify.com/v2/datasets/mm4bRWRtil7de60mo/items?clean=true&fields=amenities,photos,aiReviewsSummary,ratingHistogram,image,email,hotelClass,priceRange,description,priceLevel,rawRanking,numberOfRooms,longitude,latitude,address,name,phone,website,travelerChoiceAward&format=json'
    response = requests.get(url)
    data = response.json()
    if not data:
        return APIResponse.error('No data from API', status=400)

    # Limit to 20 items for testing
    data = data[:20]
    print(f'Fetched {len(data)} hotels from API')

    # Find city node with postal code 550000
    city_result = execute_neo4j_query(
        """
        MATCH (c:City {postal_code: $postal_code})
        RETURN c
        """,
        {'postal_code': '550000'},
    )
    if not city_result:
        return APIResponse.error(
            'City with postal code 550000 not found', status=404
        )

    inserted = 0
    errors = []
    schema = HotelSchema()

    for loc in data:
        try:
            # Process photos (limit to 30)
            if 'photos' in loc and len(loc['photos']) > 30:
                loc['photos'] = loc['photos'][:30]
                
            # Process rating histogram - convert from object to list format
            if 'ratingHistogram' in loc and isinstance(loc['ratingHistogram'], dict):
                rh = loc['ratingHistogram']
                loc['ratingHistogram'] = [
                    rh.get('count1', 0),
                    rh.get('count2', 0),
                    rh.get('count3', 0),
                    rh.get('count4', 0),
                    rh.get('count5', 0),
                ]
            
            # For backwards compatibility
            if 'rating_histogram' in loc and 'ratingHistogram' not in loc:
                loc['ratingHistogram'] = loc.pop('rating_histogram')

            # Validate with schema (pre_load processing will handle conversions)
            hotel_data = schema.load(loc)
            hotel_id = str(uuid.uuid4())
            created_at = datetime.now(timezone.utc).isoformat()

            # Extract address components
            address_data = hotel_data.get('address', {})
            street = address_data.get('street', '')
            
            # Create the hotel node and link directly to city
            hotel_create_result = execute_neo4j_query(
                """
                MATCH (c:City {postal_code: $postal_code})
                MERGE (h:Hotel {
                    name: $name,
                    longitude: $longitude,
                    latitude: $latitude
                })
                ON CREATE SET
                    h.id = $id,
                    h.created_at = $created_at,
                    h.address = $address,
                    h.description = $description,
                    h.aiReviewsSummary = $aiReviewsSummary,
                    h.image = $image,
                    h.email = $email,
                    h.priceRange = $priceRange,
                    h.rawRanking = $rawRanking,
                    h.numberOfRooms = $numberOfRooms,
                    h.phone = $phone,
                    h.website = $website,
                    h.photos = $photos,
                    h.ratingHistogram = $ratingHistogram,
                    h.travelerChoiceAward = $travelerChoiceAward
                ON MATCH SET
                    h.address = $address,
                    h.description = $description,
                    h.aiReviewsSummary = $aiReviewsSummary,
                    h.image = $image,
                    h.email = $email,
                    h.priceRange = $priceRange,
                    h.rawRanking = $rawRanking,
                    h.numberOfRooms = $numberOfRooms,
                    h.phone = $phone,
                    h.website = $website,
                    h.photos = $photos,
                    h.ratingHistogram = $ratingHistogram,
                    h.travelerChoiceAward = $travelerChoiceAward
                MERGE (c)-[:HAS_PLACE]->(h)
                RETURN h
                """,
                {
                    'postal_code': '550000',
                    'id': hotel_id,
                    'created_at': created_at,
                    'name': hotel_data.get('name'),
                    'address': street,  # Store only the street part in Neo4j
                    'description': hotel_data.get('description'),
                    'longitude': hotel_data.get('longitude'),
                    'latitude': hotel_data.get('latitude'),
                    'aiReviewsSummary': hotel_data.get('aiReviewsSummary'),
                    'image': hotel_data.get('image'),
                    'email': hotel_data.get('email'),
                    'priceRange': hotel_data.get('priceRange'),
                    'rawRanking': hotel_data.get('rawRanking'),
                    'numberOfRooms': hotel_data.get('numberOfRooms'),
                    'phone': hotel_data.get('phone'),
                    'website': hotel_data.get('website'),
                    'photos': hotel_data.get('photos'),
                    'ratingHistogram': hotel_data.get('ratingHistogram'),
                    'travelerChoiceAward': hotel_data.get(
                        'travelerChoiceAward'
                    ),
                },
            )

            # Process amenities in batches to improve performance
            if hotel_data.get('amenities'):
                amenities_query = """
                MATCH (h:Hotel {name: $hotel_name, longitude: $longitude, latitude: $latitude})
                UNWIND $amenities as amenity_name
                MERGE (a:Amenity {name: amenity_name})
                MERGE (h)-[:HAS_AMENITY]->(a)
                """
                execute_neo4j_query(
                    amenities_query,
                    {
                        'hotel_name': hotel_data.get('name'),
                        'longitude': hotel_data.get('longitude'),
                        'latitude': hotel_data.get('latitude'),
                        'amenities': hotel_data.get('amenities', []),
                    },
                )

            # Create and link PriceLevel node if it exists
            if hotel_data.get('priceLevel'):
                execute_neo4j_query(
                    """
                    MATCH (h:Hotel {name: $hotel_name, longitude: $longitude, latitude: $latitude})
                    MERGE (p:PriceLevel {level: $price_level})
                    MERGE (h)-[:HAS_PRICE_LEVEL]->(p)
                    """,
                    {
                        'hotel_name': hotel_data.get('name'),
                        'longitude': hotel_data.get('longitude'),
                        'latitude': hotel_data.get('latitude'),
                        'price_level': hotel_data.get('priceLevel'),
                    },
                )

            # Create and link HotelClass node if it exists
            if hotel_data.get('hotelClass') is not None:
                try:
                    # Convert hotelClass to float (it might come as string like "5.0")
                    hotel_class_value = float(hotel_data.get('hotelClass'))

                    # For 0.0 values, create a relationship with "undefined" value
                    if hotel_class_value == 0.0:
                        execute_neo4j_query(
                            """
                            MATCH (h:Hotel {name: $hotel_name, longitude: $longitude, latitude: $latitude})
                            MERGE (hc:HotelClass {class: $hotel_class})
                            MERGE (h)-[:HAS_CLASS]->(hc)
                            """,
                            {
                                'hotel_name': hotel_data.get('name'),
                                'longitude': hotel_data.get('longitude'),
                                'latitude': hotel_data.get('latitude'),
                                'hotel_class': 'undefined',
                            },
                        )
                    else:
                        execute_neo4j_query(
                            """
                            MATCH (h:Hotel {name: $hotel_name, longitude: $longitude, latitude: $latitude})
                            MERGE (hc:HotelClass {class: $hotel_class})
                            MERGE (h)-[:HAS_CLASS]->(hc)
                            """,
                            {
                                'hotel_name': hotel_data.get('name'),
                                'longitude': hotel_data.get('longitude'),
                                'latitude': hotel_data.get('latitude'),
                                'hotel_class': hotel_class_value,
                            },
                        )
                except (ValueError, TypeError) as e:
                    # If conversion fails, ignore this relationship
                    print(
                        f"Warning: Could not convert hotelClass '{hotel_data.get('hotelClass')}' to float for hotel {hotel_data.get('name')}"
                    )
                    pass

            inserted += 1
        except Exception as e:
            errors.append(f'{loc.get("name")}: {str(e)}')

    return APIResponse.success(
        data={'inserted': inserted, 'errors': errors}, status=200
    )


@bp.get('')
def get_hotels():
    page = max(request.args.get('page', default=1, type=int), 1)
    per_page = min(request.args.get('per_page', default=10, type=int), 50)
    sort_order = request.args.get('order', default='desc', type=str).lower()
    sort_order = 'ASC' if sort_order == 'asc' else 'DESC'

    # Get filter parameters
    amenity = request.args.get('amenity')
    price_level = request.args.get('price_level')
    hotel_class = request.args.get('hotel_class')
    min_rating = request.args.get('min_rating', type=float)
    award_winners = request.args.get('award_winners', type=bool, default=False)

    # Build query based on filters
    query_params = {'offset': (page - 1) * per_page, 'limit': per_page}
    match_clause = 'MATCH (h:Hotel)'
    where_clauses = []

    if amenity:
        match_clause += (
            '\nMATCH (h)-[:HAS_AMENITY]->(a:Amenity {name: $amenity})'
        )
        query_params['amenity'] = amenity

    if price_level:
        match_clause += '\nMATCH (h)-[:HAS_PRICE_LEVEL]->(p:PriceLevel {level: $price_level})'
        query_params['price_level'] = price_level

    if hotel_class:
        try:
            # Convert to float for proper comparison with the stored float value
            hotel_class_value = float(hotel_class)
            match_clause += '\nMATCH (h)-[:HAS_CLASS]->(hc:HotelClass {class: $hotel_class})'
            query_params['hotel_class'] = hotel_class_value
        except (ValueError, TypeError):
            # If conversion fails, return empty results
            return APIResponse.error(
                f'Invalid hotel_class parameter: {hotel_class}. Must be a valid number.',
                status=400,
            )

    if min_rating:
        where_clauses.append('h.rawRanking >= $min_rating')
        query_params['min_rating'] = min_rating

    if award_winners:
        where_clauses.append('h.travelerChoiceAward = true')

    where_clause = (
        '\nWHERE ' + ' AND '.join(where_clauses) if where_clauses else ''
    )

    # Query the database for total records
    count_query = (
        match_clause + where_clause + '\nRETURN count(h) as total_records'
    )
    total_records_result = execute_neo4j_query(count_query, query_params)

    # Query the database for paginated results with amenities, price levels, and hotel classes
    results_query = f"""
    {match_clause}
    {where_clause}
    WITH h
    OPTIONAL MATCH (h)-[:HAS_AMENITY]->(a:Amenity)
    OPTIONAL MATCH (h)-[:HAS_PRICE_LEVEL]->(p:PriceLevel)
    OPTIONAL MATCH (h)-[:HAS_CLASS]->(hc:HotelClass)
    WITH h, collect(DISTINCT a.name) as amenities, collect(DISTINCT p.level) as price_levels, collect(DISTINCT hc.class) as hotel_classes
    RETURN h, amenities, price_levels, hotel_classes
    ORDER BY h.rawRanking {sort_order}
    SKIP $offset LIMIT $limit
    """

    results = execute_neo4j_query(results_query, query_params)

    # Process the results
    schema = HotelSchema()
    hotels = []
    
    for item in results:
        hotel = schema.dump(item.get('h'))
        neo4j_node = item.get('h', {})

        # Ensure id field is included
        if 'id' not in hotel and neo4j_node.get('id'):
            hotel['id'] = neo4j_node.get('id')

        # Add amenities from the query results
        if not hotel.get('amenities') and item.get('amenities'):
            hotel['amenities'] = item.get('amenities')

        # Add priceLevels
        hotel['priceLevels'] = item.get('price_levels', [])

        # Convert hotelClasses from list to single string value
        hotel_classes = item.get('hotel_classes', [])
        # Take the first class value if exists, otherwise null
        if hotel_classes and len(hotel_classes) > 0:
            cls_value = str(hotel_classes[0])
            if cls_value == "0.0" or cls_value == "undefined":
                hotel['hotelClass'] = None
            else:
                hotel['hotelClass'] = cls_value
        else:
            hotel['hotelClass'] = None
        
        # Get street directly from the Neo4j node's address property
        street = neo4j_node.get('address', '')
        
        # Set structured address with the retrieved street
        hotel['address'] = {
            'street': street if street else '',
            'city': {
                'name': 'Da Nang',
                'postalCode': '550000'
            }
        }

        # Calculate rating and round to 1 decimal place
        rh = hotel.get('ratingHistogram')
        if not rh and 'rating_histogram' in hotel:
            # For backward compatibility
            rh = hotel.get('rating_histogram')
            # Migrate the field name
            hotel['ratingHistogram'] = rh
            hotel.pop('rating_histogram', None)
            
        if rh and isinstance(rh, list) and len(rh) == 5:
            total = sum(rh)
            if total > 0:
                rating = sum((i + 1) * rh[i] for i in range(5)) / total
                rating = round(rating, 1)  # Round to 1 decimal place
            else:
                rating = None
        else:
            rating = None
        hotel['rating'] = rating
        
        # Remove snake_case fields that have camelCase equivalents
        hotel.pop('price_levels', None)
        hotel.pop('hotel_classes', None)
        
        hotels.append(hotel)

    return APIResponse.paginate(
        data=hotels,
        page=page,
        per_page=per_page,
        total_records=total_records_result[0]['total_records'],
    )


@bp.get('/<id>')
def get_hotel_by_id(id):
    # Query the database for the specific hotel with amenities, price levels, and hotel classes
    result = execute_neo4j_query(
        """
        MATCH (h:Hotel {id: $id})
        OPTIONAL MATCH (h)-[:HAS_AMENITY]->(a:Amenity)
        OPTIONAL MATCH (h)-[:HAS_PRICE_LEVEL]->(p:PriceLevel)
        OPTIONAL MATCH (h)-[:HAS_CLASS]->(hc:HotelClass)
        WITH h, collect(DISTINCT a.name) as amenities, collect(DISTINCT p.level) as price_levels, collect(DISTINCT hc.class) as hotel_classes
        RETURN h, amenities, price_levels, hotel_classes
        """,
        {'id': id},
    )

    if not result:
        return APIResponse.error('Hotel not found', status=404)

    # Process the result
    schema = HotelSchema()
    item = result[0]
    hotel = schema.dump(item.get('h'))
    neo4j_node = item.get('h', {})

    # Add amenities from the query results
    if not hotel.get('amenities') and item.get('amenities'):
        hotel['amenities'] = item.get('amenities')

    # Add priceLevels
    hotel['priceLevels'] = item.get('price_levels', [])

    # Convert hotelClasses from list to single string value
    hotel_classes = item.get('hotel_classes', [])
    # Take the first class value if exists, otherwise null
    if hotel_classes and len(hotel_classes) > 0:
        cls_value = str(hotel_classes[0])
        if cls_value == "0.0" or cls_value == "undefined":
            hotel['hotelClass'] = None
        else:
            hotel['hotelClass'] = cls_value
    else:
        hotel['hotelClass'] = None
    
    # Get street directly from the Neo4j node's address property
    street = neo4j_node.get('address', '')
    
    # Set structured address with the retrieved street
    hotel['address'] = {
        'street': street if street else '',
        'city': {
            'name': 'Da Nang',
            'postalCode': '550000'
        }
    }

    # Calculate rating and round to 1 decimal place
    rh = hotel.get('ratingHistogram')
    if not rh and 'rating_histogram' in hotel:
        # For backward compatibility
        rh = hotel.get('rating_histogram')
        # Migrate the field name
        hotel['ratingHistogram'] = rh
        hotel.pop('rating_histogram', None)
        
    if rh and isinstance(rh, list) and len(rh) == 5:
        total = sum(rh)
        if total > 0:
            rating = sum((i + 1) * rh[i] for i in range(5)) / total
            rating = round(rating, 1)  # Round to 1 decimal place
        else:
            rating = None
    else:
        rating = None
    hotel['rating'] = rating
    
    # Remove snake_case fields that have camelCase equivalents
    hotel.pop('price_levels', None)
    hotel.pop('hotel_classes', None)

    return APIResponse.success(data=hotel)
