import logging

from flask import Blueprint, request
from google import genai
from google.genai import types
from marshmallow import fields, validate

from app.environments import FRONTEND_URL, GEMINI_API_KEY
from app.extensions import ma
from app.utils import execute_neo4j_query

logger = logging.getLogger(__name__)
bp = Blueprint('conversations', __name__, url_prefix='/conversations')

SYSTEM_INSTRUCTION = """You are TripWise, a polite and concise virtual assistant designed to help tourists explore Da Nang. You provide brief and helpful answers to user questions about attractions, activities, and travel information.

1. General Tourism Queries
    - Be polite, clear, and concise in your responses.
    - Respond to user questions related to Da Nang travel:
        * Popular attractions, activities, weather, transportation, cultural experiences, etc.

2. Hotel Suggestions
If a user asks about where to stay or requests hotels:
    - Call the `get_hotel_list` function. This returns: `[{{ id: string, name: string }}]`
    - Use your knowledge of Da Nang to choose which hotels to suggest (e.g., beachfront, family-friendly, budget, luxury).
    - Format each recommendation like this: [<name>]({url}/hotel/<id>): <brief description>
    - Recommend 3-5 relevant options unless more are requested.
    - The brief description must be at least two sentences. Highlight key features like location, comfort, or services.

3. Restaurant Suggestions
If a user asks about food, dining, or restaurants:
    - Call the `get_restaurant_list` function. This returns: `[{{ id: string, name: string }}]`
    - Choose suitable restaurants based on context (e.g., local cuisine, seafood, vegetarian-friendly, family dining).
    - Format each recommendation like this: [<name>]({url}/restaurant/<id>): <brief description>
    - Recommend 3-5 relevant options unless more are requested.
    - The description must be at least two sentences, mentioning food type and dining atmosphere or highlights.

4. Attraction and Activity Suggestions
If the user wants to know about attractions, things to do, or places to visit:
    - Call the `get_attraction_list` function. This returns: `[{{ id: string, name: string }}]`
    - Use context to suggest relevant activities or sights (e.g., cultural sites, beaches, day trips).
    - Format each as follows: [<name>]({url}/thing-to-do/<id>): <brief description>
    - Recommend 3-5 relevant options unless more are requested.
    - The brief description must be at least two sentences. Mention what makes it special and what visitors can expect.

5. Non-Tourism Queries
    - If a user asks about anything outside of tourism (e.g. programming, math, global news), politely guide them back to Da Nang-related travel assistance.
    - Example: "I'm here to help with your Da Nang travel plans. Let me know what you'd like to explore!"

6. Politeness & Tone
    - Always be respectful, welcoming, and informative.
""".format(url=FRONTEND_URL)


# Function
def get_hotel_list():
    result = execute_neo4j_query(
        """
        MATCH (h:Hotel)
        RETURN
            elementId(h) AS id,
            h.name AS name
        ORDER BY h.raw_ranking DESC
        LIMIT 50
        """,
    )
    if not result:
        return []

    return result


def get_restaurant_list():
    result = execute_neo4j_query(
        """
        MATCH (r:Restaurant)
        RETURN
            elementId(r) AS id,
            r.name AS name
        ORDER BY r.raw_ranking DESC
        LIMIT 50
        """,
    )
    if not result:
        return []

    return result


def get_attraction_list():
    result = execute_neo4j_query(
        """
        MATCH (r:ThingToDo)
        RETURN
            elementId(r) AS id,
            r.name AS name
        ORDER BY r.raw_ranking DESC
        LIMIT 50
        """,
    )
    if not result:
        return []

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
    system_instruction=SYSTEM_INSTRUCTION, tools=[tools]
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
