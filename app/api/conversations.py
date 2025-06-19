import json
import logging

from flask import Blueprint, request
from google import genai
from google.genai import types
from marshmallow import fields, validate

from app.environments import FRONTEND_URL, GEMINI_API_KEY
from app.extensions import ma
from app.utils import execute_neo4j_query, get_redis

logger = logging.getLogger(__name__)
bp = Blueprint('conversations', __name__, url_prefix='/conversations')

SYSTEM_INSTRUCTION = """You are TripWise, a knowledgeable and friendly virtual assistant for Da Nang's official tourism platform. Your mission is to help visitors discover the best of Da Nang, Vietnam through personalized recommendations and expert local insights.

## Core Guidelines
- Maintain a warm, professional, and enthusiastic tone
- Provide accurate, helpful information specific to Da Nang
- Keep responses concise yet informative
- Always consider user context and preferences when making recommendations

## 1. General Tourism Support
Handle inquiries about:
- Popular attractions and hidden gems
- Best times to visit and seasonal activities
- Local transportation options and getting around
- Cultural experiences and local customs
- Weather conditions and what to pack
- Budget planning and cost considerations

## 2. Hotel Recommendations
When users ask about accommodations:
- Call `get_hotel_list()` to access current hotel data
- Consider user preferences: budget range, location, amenities, travel style
- **Formatting for listed hotels**: - [<name>]({url}/hotel/<id>): <description>
- **Formatting for unlisted hotels**: - <name>: <description>
- Provide detailed descriptions (minimum 2 sentences) highlighting:
    - Prime location benefits and nearby attractions
    - Unique amenities, services, or selling points
    - Target guest type (business, family, luxury, budget)

## 3. Dining Recommendations
For restaurant and food inquiries:
- Call `get_restaurant_list()` to access current restaurant data
- Match recommendations to user interests: cuisine type, dining style, budget, location
- **Formatting for listed restaurants**: - [<name>]({url}/restaurant/<id>): <description>
- **Formatting for unlisted restaurants**: - <name>: <description>
- Craft engaging descriptions (minimum 2 sentences) covering:
    - Signature dishes and cuisine specialties
    - Dining atmosphere and experience highlights
    - Price range and best times to visit

## 4. Attractions & Activities
For sightseeing and activity requests:
- Call `get_attraction_list()` to access current attraction data
- Tailor suggestions based on interests: nature, culture, adventure, family activities
- **Formatting for listed attractions**: - [<name>]({url}/thing-to-do/<id>): <description>
- **Formatting for unlisted attractions**: - <name>: <description>
- Create compelling descriptions (minimum 2 sentences) including:
    - What makes the attraction unique or must-see
    - Visitor experience and practical details
    - Best times to visit and any special considerations

## 5. Off-Topic Queries
For non-tourism related questions:
- Politely redirect: "I specialize in Da Nang travel planning! How can I help you explore this beautiful coastal city?"
- Offer to help with travel-related aspects if there's any connection

## Response Quality Standards
- Always prioritize user safety and current information
- Include practical tips when relevant (opening hours, booking advice, etc.)
- Group related recommendations logically
- End responses with an invitation for follow-up questions when appropriate
""".format(url=FRONTEND_URL)


# Function
def get_hotel_list():
    cache_key = 'hotel_list:assistant'
    redis = get_redis()
    try:
        cached_result = redis.get(cache_key)
        if cached_result:
            return json.loads(cached_result)
    except Exception:
        pass

    result = execute_neo4j_query(
        """
        MATCH (h:Hotel)
        RETURN
            elementId(h) AS id,
            h.name AS name
        ORDER BY h.raw_ranking DESC
        """,
    )
    if not result:
        return []

    # Cache the result for 6 hours
    try:
        redis.setex(cache_key, 21600, json.dumps(result))
    except Exception:
        pass

    return result


def get_restaurant_list():
    cache_key = 'restaurant_list:assistant'
    redis = get_redis()
    try:
        cached_result = redis.get(cache_key)
        if cached_result:
            return json.loads(cached_result)
    except Exception:
        pass

    result = execute_neo4j_query(
        """
        MATCH (r:Restaurant)
        RETURN
            elementId(r) AS id,
            r.name AS name
        ORDER BY r.raw_ranking DESC
        """,
    )
    if not result:
        return []

    # Cache the result for 6 hours
    try:
        redis.setex(cache_key, 21600, json.dumps(result))
    except Exception:
        pass

    return result


def get_attraction_list():
    cache_key = 'attraction_list:assistant'
    redis = get_redis()
    try:
        cached_result = redis.get(cache_key)
        if cached_result:
            return json.loads(cached_result)
    except Exception:
        pass

    result = execute_neo4j_query(
        """
        MATCH (r:ThingToDo)
        RETURN
            elementId(r) AS id,
            r.name AS name
        ORDER BY r.raw_ranking DESC
        """,
    )
    if not result:
        return []

    # Cache the result for 6 hours
    try:
        redis.setex(cache_key, 21600, json.dumps(result))
    except Exception:
        pass

    return result


# Define the function declaration for the model
get_hotel_list_function = {
    'name': 'get_hotel_list',
    'description': 'Get a list of hotels in Da Nang, Vietnam',
    'parameters': {
        'type': 'object',
    },
}

get_restaurant_list_function = {
    'name': 'get_restaurant_list',
    'description': 'Get a list of restaurants in Da Nang, Vietnam',
    'parameters': {
        'type': 'object',
    },
}

get_attraction_list_function = {
    'name': 'get_attraction_list',
    'description': 'Get a list of attractions and things to do in Da Nang, Vietnam',
    'parameters': {
        'type': 'object',
    },
}

# Configure the Gemini
client = genai.Client(api_key=GEMINI_API_KEY)
tools = types.Tool(
    function_declarations=[
        get_hotel_list_function,
        get_restaurant_list_function,
        get_attraction_list_function,
    ]
)
config = types.GenerateContentConfig(
    system_instruction=SYSTEM_INSTRUCTION, tools=[tools], temperature=0.8
)


class RequestSchema(ma.Schema):
    contents = fields.List(
        fields.Dict(), required=True, validate=validate.Length(min=1)
    )


@bp.post('/')
def create_response():
    data = RequestSchema().load(request.get_json())
    contents: list = data['contents']

    response = client.models.generate_content(
        model='gemini-2.0-flash', contents=contents, config=config
    )
    tool_call = response.candidates[0].content.parts[0].function_call

    #  Process the function call
    if tool_call:
        result = None
        if tool_call.name == 'get_hotel_list':
            result = get_hotel_list()
        elif tool_call.name == 'get_restaurant_list':
            result = get_restaurant_list()

        # Create a function response part
        function_response_part = {
            'function_response': {
                'name': tool_call.name,
                'response': {'result': result},
            }
        }

        # Append function call and result of the function execution to contents
        contents.append(
            {
                'role': 'model',
                'parts': [
                    {
                        'function_call': {
                            'name': tool_call.name,
                            'args': tool_call.args,
                        }
                    }
                ],
            }
        )
        contents.append({'role': 'user', 'parts': [function_response_part]})

        final_response = client.models.generate_content(
            model='gemini-2.0-flash',
            config=config,
            contents=contents,
        )
        contents.append(
            {'role': 'model', 'parts': [{'text': final_response.text}]}
        )
    else:
        contents.append({'role': 'model', 'parts': [{'text': response.text}]})

    return {'contents': contents}, 200
