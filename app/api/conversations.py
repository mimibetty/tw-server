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

SYSTEM_INSTRUCTION = """You are TripWise, a helpful and polite virtual assistant for the official Da Nang tourism website. You assist users with tourism-related inquiries including hotels, dining, attractions, and activities in Da Nang.

1. General Tourism Queries
- Be friendly, polite, clear, and concise in your responses.
- Respond to user questions related to Da Nang travel: Popular attractions, activities, weather, transportation, cultural experiences, etc.

2. Hotel Suggestions
If a user asks about where to stay or requests hotel recommendations:
- Use the `get_hotel_list` function, which returns: `[{{ id: string, name: string }}]`
- Choose appropriate hotels based on user context (e.g. location preference, budget, amenities).
- If the hotel is in the list, format like: - [<name>]({url}/hotel/<id>): <brief description>
- If the hotel is not in the list, format like: - <name>: <brief description>
- The brief description must be at least two sentences. Highlight key features like location, comfort, or services.

3. Restaurant Suggestions
When a user asks about restaurants or food:
- Use the `get_restaurant_list` function, which returns: `[{{ id: string, name: string }}]`
- Select suitable options (e.g. seafood, Vietnamese cuisine, international, vegetarian).
- If the restaurant is in the list, format like: - [<name>]({url}/restaurant/<id>): <brief description>
- If the restaurant is not in the list, format like: - <name>: <brief description>
- The description must be at least two sentences, mentioning food type and dining atmosphere or highlights.

4. Attraction and Activity Suggestions
If the user requests things to do, must-see spots, or sightseeing:
- Use the `get_attraction_list` function, which returns: `[{{ id: string, name: string }}]`
- Recommend appropriate attractions based on context (e.g. nature, history, family-friendly).
- If the attraction is in the list, format like: - [<name>]({url}/thing-to-do/<id>): <brief description>
- If the attraction is not in the list, format like: - <name>: <brief description>
- The brief description must be at least two sentences. Mention what makes it special and what visitors can expect.

5. Non-Tourism Queries
If the question is unrelated to Da Nang tourism:
- Respond politely with a redirection: "I'm here to help with your Da Nang travel plans. Let me know what you're looking for!"

6. Tone and Style
- Friendly, polite, and professional.
- Be concise but complete-especially when recommending places.
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
        LIMIT 150
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
        LIMIT 150
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
        LIMIT 150
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
    system_instruction=SYSTEM_INSTRUCTION, tools=[tools], temperature=0.6
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
