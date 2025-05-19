#!/usr/bin/env python
"""
Restaurant Data Importer

A standalone script to fetch restaurant data from Apify API and insert it into the database
via the API endpoints. This script is not part of the main application.

Usage:
    python Helpers/restaurant_data_importer.py
"""
import json
import logging
import os
import requests
import sys
import time
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('restaurant_importer')

def fetch_restaurant_data(url: str, limit: int = 100) -> List[Dict[str, Any]]:
    """
    Fetch restaurant data from external API
    
    Args:
        url: The API URL to fetch data from
        limit: Maximum number of items to return
        
    Returns:
        List of restaurant data dictionaries or empty list if fetch fails
    """
    try:
        logger.info(f"Fetching data from {url}")
        response = requests.get(url)
        response.raise_for_status()  # Raise exception for HTTP errors
        
        data = response.json()
        logger.info(f"Fetched {len(data)} restaurants from API")
        
        # Limit to specified number of items
        return data[:limit] if data else []
    except Exception as e:
        logger.error(f"Failed to fetch data from API: {str(e)}")
        return []

def process_restaurant_data(restaurant: Dict[str, Any], postal_code: str) -> Dict[str, Any]:
    """
    Process raw restaurant data into format suitable for API insertion
    
    Args:
        restaurant: Raw restaurant data from API
        postal_code: Postal code of the city where the restaurant is located
        
    Returns:
        Processed restaurant data dictionary
    """
    # Process photos (limit to 30)
    if 'photos' in restaurant and restaurant['photos'] and len(restaurant['photos']) > 30:
        restaurant['photos'] = restaurant['photos'][:30]
    
    # Process rating histogram - convert from object to list format
    if 'ratingHistogram' in restaurant and isinstance(restaurant['ratingHistogram'], dict):
        rh = restaurant['ratingHistogram']
        restaurant['ratingHistogram'] = [
            rh.get('count1', 0),
            rh.get('count2', 0),
            rh.get('count3', 0),
            rh.get('count4', 0),
            rh.get('count5', 0),
        ]
    
    # Extract and clean street address
    street = ""
    if 'address' in restaurant:
        if isinstance(restaurant['address'], dict) and 'street' in restaurant['address']:
            street = restaurant['address']['street']
        elif isinstance(restaurant['address'], str):
            street = restaurant['address']
        
        # Remove unwanted suffixes
        suffixes_to_remove = [
            f", Da Nang {postal_code} Vietnam", 
            f", Da Nang {postal_code}", 
            ", Da Nang Vietnam",
            ", Da Nang"
        ]
        for suffix in suffixes_to_remove:
            if street.endswith(suffix):
                street = street[:-len(suffix)]
                break
    
    # Process hours if available - transform from weekRanges to day-specific format
    hours = None
    if 'hours' in restaurant and restaurant['hours']:
        try:
            hours_data = restaurant['hours']
            
            if isinstance(hours_data, dict) and 'weekRanges' in hours_data:
                # Create the expected hours schema
                days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
                transformed_hours = {}
                
                week_ranges = hours_data['weekRanges']
                for i, day in enumerate(days):
                    if i < len(week_ranges) and week_ranges[i] and len(week_ranges[i]) > 0:
                        # Use the first time range for the day (most restaurants have just one)
                        time_range = week_ranges[i][0]
                        transformed_hours[day] = {
                            'open': time_range.get('openHours', ''),
                            'close': time_range.get('closeHours', '')
                        }
                    else:
                        transformed_hours[day] = None
                
                hours = transformed_hours
            else:
                # Already in the correct format or close to it
                hours = hours_data
        except Exception as e:
            logger.warning(f"Error processing hours for {restaurant.get('name')}: {str(e)}")
            hours = None
    
    # Process cuisines 
    cuisines = []
    if 'cuisines' in restaurant and isinstance(restaurant['cuisines'], list):
        cuisines = restaurant['cuisines']
    elif 'cuisine' in restaurant and isinstance(restaurant['cuisine'], list):
        cuisines = restaurant['cuisine']
    elif 'cuisine' in restaurant and isinstance(restaurant['cuisine'], str):
        cuisines = [restaurant['cuisine']]
    
    # Process meal types
    meal_types = []
    if 'mealTypes' in restaurant and isinstance(restaurant['mealTypes'], list):
        meal_types = restaurant['mealTypes']
    
    # Process dietary restrictions
    dietary_restrictions = []
    if 'dietaryRestrictions' in restaurant and isinstance(restaurant['dietaryRestrictions'], list):
        dietary_restrictions = restaurant['dietaryRestrictions']
    
    # Process features
    features = []
    if 'features' in restaurant and isinstance(restaurant['features'], list):
        features = restaurant['features']
    elif 'amenities' in restaurant and isinstance(restaurant['amenities'], list):
        features = restaurant['amenities']
    
    # Process dishes
    dishes = []
    if 'dishes' in restaurant and isinstance(restaurant['dishes'], list):
        dishes = restaurant['dishes']

    # Prepare data matching the API schema from restaurants.py
    restaurant_data = {
        'name': restaurant.get('name', ''),
        'image': restaurant.get('image', ''),
        'latitude': restaurant.get('latitude', 0),
        'longitude': restaurant.get('longitude', 0),
        'rawRanking': restaurant.get('rawRanking', 0),
        'ratingHistogram': restaurant.get('ratingHistogram', [0, 0, 0, 0, 0]),
        'street': street,
        'email': restaurant.get('email'),
        'phone': restaurant.get('phone'),
        'website': restaurant.get('website'),
        'photos': restaurant.get('photos', []),
        'description': restaurant.get('description'),
        'menuWebUrl': restaurant.get('menuWebUrl') or restaurant.get('menu_url'),
        'hours': hours,
        'dishes': dishes,
        'features': features,
        'dietaryRestrictions': dietary_restrictions,
        'mealTypes': meal_types,
        'cuisines': cuisines,
        'travelerChoiceAward': restaurant.get('travelerChoiceAward', False)
    }
    
    # Add price level if available
    if restaurant.get('priceLevel'):
        if isinstance(restaurant['priceLevel'], list):
            restaurant_data['priceLevels'] = restaurant['priceLevel']
        else:
            restaurant_data['priceLevels'] = [restaurant['priceLevel']]
    else:
        # Include default empty list for priceLevels
        restaurant_data['priceLevels'] = []
    
    # If priceLevel contains strings like "$$ - $$$", split to array of values
    if isinstance(restaurant_data.get('priceLevels'), list) and len(restaurant_data['priceLevels']) == 1:
        price_level = restaurant_data['priceLevels'][0]
        if isinstance(price_level, str) and ' - ' in price_level:
            parts = [p.strip() for p in price_level.split(' - ')]
            restaurant_data['priceLevels'] = parts
    
    # Calculate rating from histogram if available
    if isinstance(restaurant_data['ratingHistogram'], list) and len(restaurant_data['ratingHistogram']) == 5:
        rh = restaurant_data['ratingHistogram']
        total = sum(rh)
        if total > 0:
            calculated_rating = sum((i + 1) * rh[i] for i in range(5)) / total
            restaurant_data['rating'] = round(calculated_rating, 1)
        else:
            restaurant_data['rating'] = 0
    else:
        restaurant_data['rating'] = 0
    
    # Add city information
    restaurant_data['city'] = {'postalCode': postal_code}
    
    return restaurant_data

def insert_restaurant_via_api(restaurant_data: Dict[str, Any], api_url: str, token: str) -> Optional[Dict[str, Any]]:
    """
    Insert a restaurant by making a POST request to the API
    
    Args:
        restaurant_data: Processed restaurant data dictionary
        api_url: URL of the restaurants API endpoint
        token: JWT token for authorization
        
    Returns:
        The API response if successful, None otherwise
    """
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}'
    }
    
    try:
        logger.info(f"Inserting restaurant: {restaurant_data['name']}")
        response = requests.post(api_url, json=restaurant_data, headers=headers)
        
        if response.status_code == 201:
            logger.info(f"Successfully inserted restaurant: {restaurant_data['name']}")
            return response.json()
        else:
            logger.error(f"Failed to insert restaurant: {restaurant_data['name']} - Status: {response.status_code}")
            logger.error(f"Response: {response.text}")
            return None
    except Exception as e:
        logger.error(f"Error inserting restaurant {restaurant_data['name']}: {str(e)}")
        return None

def bulk_insert_restaurants(postal_code: str, api_url: str, token: str, limit: int = 100, delay: float = 0.5) -> Dict[str, Any]:
    """
    Fetch and insert multiple restaurants via the API
    
    Args:
        postal_code: Postal code of the city where restaurants should be added
        api_url: URL of the restaurants API endpoint
        token: JWT token for authorization
        limit: Maximum number of restaurants to insert
        delay: Delay between API calls in seconds
        
    Returns:
        Dictionary with insertion statistics
    """
    # Fetch data from API
    url = 'https://api.apify.com/v2/datasets/hgtjsHgPrFjllcChK/items?clean=true&fields=name,description,phone,address,latitude,longitude,mealTypes,cuisines,dishes,features,dietaryRestrictions,hours,ratingHistogram,website,email,rawRanking,menuWebUrl,priceLevel,image,photos&format=json'
    data = fetch_restaurant_data(url, limit)
    
    if not data:
        return {
            'success': False,
            'error': 'Failed to fetch data from API or no data returned'
        }
    
    # Limit the data if needed
    data = data[:limit]
    
    inserted = 0
    errors = []
    
    for restaurant in data:
        try:
            # Process the restaurant data
            restaurant_data = process_restaurant_data(restaurant, postal_code)
            
            # Skip restaurants without required fields
            if not restaurant_data['name'] or not restaurant_data['latitude'] or not restaurant_data['longitude'] or not restaurant_data.get('image'):
                errors.append(f"Missing required fields for restaurant: {restaurant_data.get('name', 'unknown')}")
                continue
            
            # Insert the restaurant via the API
            result = insert_restaurant_via_api(restaurant_data, api_url, token)
            
            if result:
                inserted += 1
            else:
                errors.append(f"Failed to create restaurant: {restaurant_data['name']}")
                
            # Add delay between requests to avoid overwhelming the API
            if delay > 0:
                time.sleep(delay)
                
        except Exception as e:
            errors.append(f"{restaurant.get('name', 'Unknown restaurant')}: {str(e)}")

    return {
        'success': True,
        'data': {
            'inserted': inserted,
            'errors': errors,
            'total': len(data)
        }
    }

def main():
    """
    Main function to run the restaurant data import process.
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
        limit = 5  # Default number of restaurants to import if env var is invalid
        
    api_url = 'http://127.0.0.1:8000/api/restaurants/'  # URL of the restaurants API endpoint
    
    # Get JWT token from environment variable
    token = os.getenv('JWT_TOKEN')
    if not token:
        logger.error("JWT_TOKEN not found in environment variables. Please add it to your .env file.")
        return {
            'success': False,
            'error': 'JWT_TOKEN not found in environment variables'
        }
    
    delay = 0.5  # Delay between API calls in seconds
    
    logger.info("Starting restaurant data import process...")
    logger.info(f"Target city postal code: {postal_code}")
    logger.info(f"Importing up to {limit} restaurants (set via IMPORT_LIMIT env var)")
    
    result = bulk_insert_restaurants(
        postal_code=postal_code,
        api_url=api_url,
        token=token,
        limit=limit,
        delay=delay
    )
    
    if result['success']:
        logger.info(f"Successfully imported {result['data']['inserted']} restaurants")
        if result['data']['errors']:
            logger.info(f"Errors: {len(result['data']['errors'])}")
            for i, error in enumerate(result['data']['errors'][:5]):
                logger.error(f"Error {i+1}: {error}")
            
            if len(result['data']['errors']) > 5:
                logger.info(f"... and {len(result['data']['errors']) - 5} more errors")
    else:
        logger.error(f"Import process failed: {result.get('error', 'Unknown error')}")
    
    logger.info("Restaurant data import process completed!")
    
    return result

if __name__ == '__main__':
    main() 