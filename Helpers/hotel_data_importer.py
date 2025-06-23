#!/usr/bin/env python
"""
Hotel Data Importer

A standalone script to fetch hotel data from Apify API and insert it into the database
via the API endpoints. This script is not part of the main application.

Usage:
    python Helpers/hotel_data_importer.py
"""

import logging
import os
import sys
import time
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger('hotel_importer')


def fetch_hotel_data(url: str, limit: int = 100) -> List[Dict[str, Any]]:
    """
    Fetch hotel data from external API

    Args:
        url: The API URL to fetch data from
        limit: Maximum number of items to return

    Returns:
        List of hotel data dictionaries or empty list if fetch fails
    """
    try:
        logger.info(f'Fetching data from {url}')
        response = requests.get(url)
        response.raise_for_status()  # Raise exception for HTTP errors

        data = response.json()
        logger.info(f'Fetched {len(data)} hotels from API')

        # Limit to specified number of items
        return data[:limit] if data else []
    except Exception as e:
        logger.error(f'Failed to fetch data from API: {str(e)}')
        return []


def process_hotel_data(hotel: Dict[str, Any], postal_code: str) -> Dict[str, Any]:
    """
    Process raw hotel data into format suitable for API insertion

    Args:
        hotel: Raw hotel data from API
        postal_code: Postal code of the city where the hotel is located

    Returns:
        Processed hotel data dictionary
    """
    # Process photos (limit to 30)
    if 'photos' in hotel and hotel['photos'] and len(hotel['photos']) > 30:
        hotel['photos'] = hotel['photos'][:30]

    # Process rating histogram - convert from object to list format
    if 'ratingHistogram' in hotel and isinstance(hotel['ratingHistogram'], dict):
        rh = hotel['ratingHistogram']
        hotel['ratingHistogram'] = [
            rh.get('count1', 0),
            rh.get('count2', 0),
            rh.get('count3', 0),
            rh.get('count4', 0),
            rh.get('count5', 0),
        ]

    # Extract and clean street address
    street = ''
    if 'address' in hotel:
        if isinstance(hotel['address'], dict) and 'street' in hotel['address']:
            street = hotel['address']['street']
        elif isinstance(hotel['address'], str):
            street = hotel['address']

        # Remove unwanted suffixes
        suffixes_to_remove = [
            f', Da Nang {postal_code} Vietnam',
            f', Da Nang {postal_code}',
            ', Da Nang Vietnam',
            ', Da Nang',
        ]
        for suffix in suffixes_to_remove:
            if street.endswith(suffix):
                street = street[: -len(suffix)]
                break

    # Prepare data matching the API schema from hotels.py
    hotel_data = {
        'name': hotel.get('name', ''),
        'image': hotel.get('image', ''),
        'latitude': hotel.get('latitude', 0),
        'longitude': hotel.get('longitude', 0),
        'rawRanking': hotel.get('rawRanking', 0),
        'ratingHistogram': hotel.get('ratingHistogram', [0, 0, 0, 0, 0]),
        'street': street,
        'email': hotel.get('email'),
        'phone': hotel.get('phone'),
        'website': hotel.get('website'),
        'photos': hotel.get('photos', []),
        'aiReviewsSummary': hotel.get('aiReviewsSummary'),
        'description': hotel.get('description'),
        'numberOfRooms': hotel.get('numberOfRooms'),
        'priceRange': hotel.get('priceRange'),
        'hotelClass': hotel.get('hotelClass'),
        'features': hotel.get('amenities', []),
        'priceLevels': [],
    }

    # Add price level if available
    if hotel.get('priceLevel'):
        hotel_data['priceLevels'] = [hotel.get('priceLevel')]

    # Calculate rating from histogram if available
    if (
        isinstance(hotel_data['ratingHistogram'], list)
        and len(hotel_data['ratingHistogram']) == 5
    ):
        rh = hotel_data['ratingHistogram']
        total = sum(rh)
        if total > 0:
            calculated_rating = sum((i + 1) * rh[i] for i in range(5)) / total
            hotel_data['rating'] = round(calculated_rating, 1)
        else:
            hotel_data['rating'] = 0
    else:
        hotel_data['rating'] = 0

    # Add city information
    hotel_data['city'] = {'postalCode': postal_code}

    return hotel_data


def insert_hotel_via_api(
    hotel_data: Dict[str, Any], api_url: str, token: str
) -> Optional[Dict[str, Any]]:
    """
    Insert a hotel by making a POST request to the API

    Args:
        hotel_data: Processed hotel data dictionary
        api_url: URL of the hotels API endpoint
        token: JWT token for authorization

    Returns:
        The API response if successful, None otherwise
    """
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}',
    }

    try:
        logger.info(f'Inserting hotel: {hotel_data["name"]}')
        response = requests.post(api_url, json=hotel_data, headers=headers)

        if response.status_code == 201:
            logger.info(f'Successfully inserted hotel: {hotel_data["name"]}')
            return response.json()
        else:
            logger.error(
                f'Failed to insert hotel: {hotel_data["name"]} - Status: {response.status_code}'
            )
            logger.error(f'Response: {response.text}')
            return None
    except Exception as e:
        logger.error(f'Error inserting hotel {hotel_data["name"]}: {str(e)}')
        return None


def bulk_insert_hotels(
    postal_code: str,
    api_url: str,
    token: str,
    limit: int = 100,
    delay: float = 0.5,
) -> Dict[str, Any]:
    """
    Fetch and insert multiple hotels via the API

    Args:
        postal_code: Postal code of the city where hotels should be added
        api_url: URL of the hotels API endpoint
        token: JWT token for authorization
        limit: Maximum number of hotels to insert
        delay: Delay between API calls in seconds

    Returns:
        Dictionary with insertion statistics
    """
    # Fetch data from API
    url = 'https://api.apify.com/v2/datasets/mm4bRWRtil7de60mo/items?clean=true&fields=amenities,photos,aiReviewsSummary,ratingHistogram,image,email,hotelClass,priceRange,description,priceLevel,rawRanking,numberOfRooms,longitude,latitude,address,name,phone,website,travelerChoiceAward&format=json'
    data = fetch_hotel_data(url, limit)

    if not data:
        return {
            'success': False,
            'error': 'Failed to fetch data from API or no data returned',
        }

    inserted = 0
    errors = []

    for hotel in data:
        try:
            # Process the hotel data
            hotel_data = process_hotel_data(hotel, postal_code)

            # Skip hotels without required fields
            if (
                not hotel_data['name']
                or not hotel_data['latitude']
                or not hotel_data['longitude']
            ):
                errors.append(
                    f'Missing required fields for hotel: {hotel_data.get("name", "unknown")}'
                )
                continue

            # Insert the hotel via the API
            result = insert_hotel_via_api(hotel_data, api_url, token)

            if result:
                inserted += 1
            else:
                errors.append(f'Failed to create hotel: {hotel_data["name"]}')

            # Add delay between requests to avoid overwhelming the API
            if delay > 0:
                time.sleep(delay)

        except Exception as e:
            errors.append(f'{hotel.get("name", "Unknown hotel")}: {str(e)}')

    return {
        'success': True,
        'data': {'inserted': inserted, 'errors': errors, 'total': len(data)},
    }


def main():
    """
    Main function to run the hotel data import process.
    All configuration variables are directly defined in this function for simplicity.

    To customize the import process, simply modify the variables here instead of
    changing command line arguments.
    """
    # Direct variable assignment instead of using argparse
    postal_code = '550000'  # Default city code for Da Nang

    # Get import limit from environment variable or use default
    try:
        limit = int(os.getenv('IMPORT_LIMIT', '5'))
    except (ValueError, TypeError):
        limit = 5  # Default number of hotels to import if env var is invalid

    api_url = 'http://127.0.0.1:8000/api/hotels/'  # URL of the hotels API endpoint

    # Get JWT token from environment variable
    token = os.getenv('JWT_TOKEN')
    if not token:
        logger.error(
            'JWT_TOKEN not found in environment variables. Please add it to your .env file.'
        )
        return {
            'success': False,
            'error': 'JWT_TOKEN not found in environment variables',
        }

    delay = 0.5  # Delay between API calls in seconds

    logger.info('Starting hotel data import process...')
    logger.info(f'Target city postal code: {postal_code}')
    logger.info(f'Importing up to {limit} hotels (set via IMPORT_LIMIT env var)')

    result = bulk_insert_hotels(
        postal_code=postal_code,
        api_url=api_url,
        token=token,
        limit=limit,
        delay=delay,
    )

    if result['success']:
        logger.info(f'Successfully imported {result["data"]["inserted"]} hotels')
        if result['data']['errors']:
            logger.info(f'Errors: {len(result["data"]["errors"])}')
            for i, error in enumerate(result['data']['errors'][:5]):
                logger.error(f'Error {i + 1}: {error}')

            if len(result['data']['errors']) > 5:
                logger.info(f'... and {len(result["data"]["errors"]) - 5} more errors')
    else:
        logger.error(f'Import process failed: {result.get("error", "Unknown error")}')

    logger.info('Hotel data import process completed!')

    return result


if __name__ == '__main__':
    main()
