#!/usr/bin/env python
"""
Things To Do Data Importer

A standalone script to fetch attractions/things to do data from Apify API and insert it into the database
via the API endpoints. This script is not part of the main application.

Usage:
    python Helpers/things_to_do_importer.py
"""

import json
import logging
import os
import re
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
logger = logging.getLogger('things_to_do_importer')


def read_sample_data(filename: str = 'data.txt') -> List[Dict[str, Any]]:
    """
    Read sample data from the data.txt file

    Args:
        filename: Path to the data file

    Returns:
        List of attraction data dictionaries from the sample file
    """
    try:
        logger.info(f'Reading sample data from {filename}')
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()

        # Extract JSON objects from the file
        # The file format isn't pure JSON, so we need to extract the objects
        json_pattern = r'(\{[\s\S]*?\})'
        matches = re.findall(json_pattern, content)

        data = []
        for match in matches:
            try:
                # Try to parse each JSON object
                obj = json.loads(match)
                if isinstance(obj, dict) and 'name' in obj:
                    data.append(obj)
            except json.JSONDecodeError:
                continue

        logger.info(f'Found {len(data)} attractions in sample data')
        return data
    except Exception as e:
        logger.error(f'Failed to read sample data: {str(e)}')
        return []


def fetch_things_to_do_data(
    url: str, limit: int = 100
) -> List[Dict[str, Any]]:
    """
    Fetch things to do data from external API

    Args:
        url: The API URL to fetch data from
        limit: Maximum number of items to return

    Returns:
        List of attraction data dictionaries or empty list if fetch fails
    """
    try:
        logger.info(f'Fetching data from {url}')
        response = requests.get(url)
        response.raise_for_status()  # Raise exception for HTTP errors

        data = response.json()
        logger.info(f'Fetched {len(data)} attractions from API')

        # Limit to specified number of items
        return data[:limit] if data else []
    except Exception as e:
        logger.error(f'Failed to fetch data from API: {str(e)}')
        return []


def process_thing_to_do_data(
    attraction: Dict[str, Any], postal_code: str
) -> Dict[str, Any]:
    """
    Process raw attraction data into format suitable for API insertion

    Args:
        attraction: Raw attraction data from API
        postal_code: Postal code of the city where the attraction is located

    Returns:
        Processed attraction data dictionary
    """
    # Process photos (limit to 30)
    if (
        'photos' in attraction
        and attraction['photos']
        and len(attraction['photos']) > 30
    ):
        attraction['photos'] = attraction['photos'][:30]

    # Process rating histogram - convert from object to array format
    rating_histogram = [0, 0, 0, 0, 0]  # Default values
    if 'ratingHistogram' in attraction:
        if isinstance(attraction['ratingHistogram'], dict):
            # Convert from object format (count1, count2, etc.)
            rh = attraction['ratingHistogram']
            rating_histogram = [
                rh.get('count1', 0),
                rh.get('count2', 0),
                rh.get('count3', 0),
                rh.get('count4', 0),
                rh.get('count5', 0),
            ]
        elif (
            isinstance(attraction['ratingHistogram'], list)
            and len(attraction['ratingHistogram']) == 5
        ):
            # Already in array format
            rating_histogram = attraction['ratingHistogram']

    # Extract and clean street address
    street = ''
    if 'address' in attraction:
        if (
            isinstance(attraction['address'], dict)
            and 'street' in attraction['address']
        ):
            street = attraction['address']['street']
        elif isinstance(attraction['address'], str):
            street = attraction['address']

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

    # Handle subtypes - convert from 'subtype' to 'subtypes' if needed
    subtypes = []
    if 'subtypes' in attraction and isinstance(attraction['subtypes'], list):
        subtypes = attraction['subtypes']
    elif 'subtype' in attraction and isinstance(attraction['subtype'], list):
        subtypes = attraction['subtype']

    # Handle subcategories
    subcategories = []
    if 'subcategories' in attraction and isinstance(
        attraction['subcategories'], list
    ):
        subcategories = attraction['subcategories']

    # Prepare data matching the API schema from things_to_do.py
    thing_to_do_data = {
        'name': attraction.get('name', ''),
        'image': attraction.get('image', ''),
        'latitude': attraction.get('latitude', 0),
        'longitude': attraction.get('longitude', 0),
        'rawRanking': attraction.get('rawRanking', 0),
        'ratingHistogram': rating_histogram,
        'street': street,
        'email': attraction.get('email'),
        'phone': attraction.get('phone'),
        'website': attraction.get('website'),
        'photos': attraction.get('photos', []),
        'description': attraction.get('description'),
        'subtypes': subtypes,
        'subcategories': subcategories,
    }

    # Calculate rating from histogram if available
    if isinstance(rating_histogram, list) and len(rating_histogram) == 5:
        total = sum(rating_histogram)
        if total > 0:
            calculated_rating = (
                sum((i + 1) * rating_histogram[i] for i in range(5)) / total
            )
            thing_to_do_data['rating'] = round(calculated_rating, 1)
        else:
            thing_to_do_data['rating'] = 0
    else:
        thing_to_do_data['rating'] = 0

    # Add city information
    thing_to_do_data['city'] = {'postalCode': postal_code}

    return thing_to_do_data


def insert_thing_to_do_via_api(
    thing_to_do_data: Dict[str, Any], api_url: str, token: str
) -> Optional[Dict[str, Any]]:
    """
    Insert a thing to do by making a POST request to the API

    Args:
        thing_to_do_data: Processed attraction data dictionary
        api_url: URL of the things-to-do API endpoint
        token: JWT token for authorization

    Returns:
        The API response if successful, None otherwise
    """
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}',
    }

    try:
        logger.info(f'Inserting attraction: {thing_to_do_data["name"]}')
        response = requests.post(
            api_url, json=thing_to_do_data, headers=headers
        )

        if response.status_code == 201:
            logger.info(
                f'Successfully inserted attraction: {thing_to_do_data["name"]}'
            )
            return response.json()
        else:
            logger.error(
                f'Failed to insert attraction: {thing_to_do_data["name"]} - Status: {response.status_code}'
            )
            logger.error(f'Response: {response.text}')
            return None
    except Exception as e:
        logger.error(
            f'Error inserting attraction {thing_to_do_data["name"]}: {str(e)}'
        )
        return None


def bulk_insert_things_to_do(
    postal_code: str,
    api_url: str,
    token: str,
    limit: int = 100,
    delay: float = 0.5,
    use_sample_data: bool = False,
) -> Dict[str, Any]:
    """
    Fetch and insert multiple things to do via the API

    Args:
        postal_code: Postal code of the city where attractions should be added
        api_url: URL of the things-to-do API endpoint
        token: JWT token for authorization
        limit: Maximum number of attractions to insert
        delay: Delay between API calls in seconds
        use_sample_data: Whether to use sample data from data.txt instead of API

    Returns:
        Dictionary with insertion statistics
    """
    # Get data either from API or sample file
    data = []
    if use_sample_data:
        data = read_sample_data('data.txt')
    else:
        # Fetch data from API - using attractions dataset from Apify
        url = 'https://api.apify.com/v2/datasets/Z2rig8cqAIhDAlJqZ/items?clean=true&fields=name,address,description,longitude,latitude,ratingHistogram,subtype,subcategories,rawRanking,phone,website,image,photos&format=json'
        data = fetch_things_to_do_data(url, limit)

    if not data:
        return {
            'success': False,
            'error': 'Failed to fetch data from API or sample file or no data returned',
        }

    # Limit the data if needed
    data = data[:limit]

    inserted = 0
    errors = []

    for attraction in data:
        try:
            # Process the attraction data
            thing_to_do_data = process_thing_to_do_data(
                attraction, postal_code
            )

            # Skip attractions without required fields
            if (
                not thing_to_do_data['name']
                or not thing_to_do_data['latitude']
                or not thing_to_do_data['longitude']
            ):
                errors.append(
                    f'Missing required fields for attraction: {thing_to_do_data.get("name", "unknown")}'
                )
                continue

            # Log the data we're about to insert (for debugging)
            logger.info(
                f'Processed attraction data: {json.dumps(thing_to_do_data, indent=2)}'
            )

            # Insert the attraction via the API
            result = insert_thing_to_do_via_api(
                thing_to_do_data, api_url, token
            )

            if result:
                inserted += 1
            else:
                errors.append(
                    f'Failed to create attraction: {thing_to_do_data["name"]}'
                )

            # Add delay between requests to avoid overwhelming the API
            if delay > 0:
                time.sleep(delay)

        except Exception as e:
            errors.append(
                f'{attraction.get("name", "Unknown attraction")}: {str(e)}'
            )

    return {
        'success': True,
        'data': {'inserted': inserted, 'errors': errors, 'total': len(data)},
    }


def main():
    """
    Main function to run the things to do data import process.
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
        limit = (
            5  # Default number of attractions to import if env var is invalid
        )

    api_url = 'http://127.0.0.1:8000/api/things-to-do/'  # URL of the things-to-do API endpoint
    use_sample_data = (
        False  # Use API data by default, set to True only for testing
    )

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

    logger.info('Starting things to do data import process...')
    logger.info(f'Target city postal code: {postal_code}')
    logger.info(
        f'Importing up to {limit} attractions (set via IMPORT_LIMIT env var)'
    )
    logger.info(f'Using {"sample data" if use_sample_data else "API data"}')

    result = bulk_insert_things_to_do(
        postal_code=postal_code,
        api_url=api_url,
        token=token,
        limit=limit,
        delay=delay,
        use_sample_data=use_sample_data,
    )

    if result['success']:
        logger.info(
            f'Successfully imported {result["data"]["inserted"]} attractions'
        )
        if result['data']['errors']:
            logger.info(f'Errors: {len(result["data"]["errors"])}')
            for i, error in enumerate(result['data']['errors'][:5]):
                logger.error(f'Error {i + 1}: {error}')

            if len(result['data']['errors']) > 5:
                logger.info(
                    f'... and {len(result["data"]["errors"]) - 5} more errors'
                )
    else:
        logger.error(
            f'Import process failed: {result.get("error", "Unknown error")}'
        )

    logger.info('Things to do data import process completed!')

    return result


if __name__ == '__main__':
    main()
