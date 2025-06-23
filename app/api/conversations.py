import json
import logging

from flask import Blueprint, request
from google import genai
from google.genai import types
from marshmallow import fields, validate
from sqlalchemy import select

from app.environments import FRONTEND_URL, GEMINI_API_KEY
from app.extensions import ma
from app.models import VectorItem, db
from app.utils import execute_neo4j_query, get_redis

logger = logging.getLogger(__name__)
bp = Blueprint('conversations', __name__, url_prefix='/conversations')

# Constants
GEMINI_MODEL = 'gemini-2.0-flash'
EMBEDDING_MODEL = 'text-embedding-004'
SYSTEM_INSTRUCTION = """You are TripWise Assistant, an AI travel companion for TripWise - a comprehensive travel platform specializing in Da Nang, Vietnam. Your role is to help users discover, plan, and enhance their travel experiences in this beautiful coastal city.

## Your Capabilities:
- Provide personalized recommendations for hotels, restaurants, and things to do in Da Nang
- Access real-time information about top-rated places and attractions
- Help users find specific places by name using advanced search
- Offer travel tips, local insights, and cultural information about Da Nang
- Assist with trip planning, itinerary suggestions, and activity recommendations

## Your Personality:
- Friendly, knowledgeable, and enthusiastic about travel
- Local expert with deep understanding of Da Nang's culture, cuisine, and attractions
- Helpful and patient, always ready to provide detailed information
- Encouraging users to explore and discover new experiences

## Guidelines:
- Always prioritize user safety and provide accurate, up-to-date information
- Be respectful of local customs and culture when making recommendations
- Provide specific, actionable advice with relevant details
- When recommending places, include why they're special and what users can expect
- Offer alternatives and options to suit different preferences and budgets
- Use the available tools to provide the most current and relevant recommendations

## Place Recommendations with Specific Conditions:
When users request places with specific conditions (e.g., "romantic restaurants", "budget hotels", "family-friendly attractions"), follow this process:
1. Use your knowledge of Da Nang to suggest relevant place names that match their criteria
2. Use the get_places_by_names function to find the URL details for those places
3. Format recommendations as clickable links: [Place Name](URL)
4. If a place isn't found in the database, still mention it but without a link
5. Provide context about why each place fits their specific requirements

## Da Nang Context:
Da Nang is Vietnam's third-largest city, known for its beautiful beaches, rich history, delicious cuisine, and proximity to UNESCO World Heritage sites like Hoi An and My Son. The city offers a perfect blend of modern amenities and traditional Vietnamese culture.

Remember: Your goal is to make every user's trip to Da Nang memorable and enjoyable by providing personalized, helpful, and accurate travel assistance."""


# Function
def get_top_places(type: str):
    cache_key = f'top_list:{type.lower()}:assistant'
    redis = get_redis()
    try:
        cached_result = redis.get(cache_key)
        if cached_result:
            return json.loads(cached_result)
    except Exception:
        pass

    # Define queries based on type
    if type.lower() == 'hotel':
        query = """
        MATCH (h:Hotel)
        RETURN elementId(h) AS id, h.name AS name
        ORDER BY h.raw_ranking DESC LIMIT 5
        """
    elif type.lower() == 'restaurant':
        query = """
        MATCH (r:Restaurant)
        RETURN elementId(r) AS id, r.name AS name
        ORDER BY r.raw_ranking DESC LIMIT 5
        """
    elif type.lower() == 'thing-to-do':
        query = """
        MATCH (a:ThingToDo)
        RETURN elementId(a) AS id, a.name AS name
        ORDER BY a.raw_ranking DESC LIMIT 5
        """
    else:
        return []

    result = execute_neo4j_query(query)
    if not result:
        return []

    response = []
    for item in result:
        response.append(
            {
                'name': item['name'],
                'url': f'{FRONTEND_URL}/{type.lower()}/{item["id"]}',
            }
        )

    # Cache the result for 6 hours
    try:
        redis.setex(cache_key, 21600, json.dumps(response))
    except Exception:
        pass

    return response


def get_places_by_names(names: list[str]):
    result = []
    for name in names:
        embeddings = (
            client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=name,
                config=types.EmbedContentConfig(task_type='RETRIEVAL_QUERY'),
            )
            .embeddings[0]
            .values
        )

        # Find the most similar place using cosine similarity
        query_result = db.session.scalar(
            select(VectorItem)
            .filter(VectorItem.embedding.cosine_distance(embeddings) <= 2)
            .limit(1)
        )
        if query_result:
            result.append(
                {
                    'name': name,
                    'url': f'{FRONTEND_URL}/{query_result.type}/{query_result.place_id}',
                }
            )

    return result


# Define the function declaration for the model
get_top_places_function = {
    'name': 'get_top_places',
    'description': 'Retrieve the top 5 highest-rated places of a specific category in Da Nang, Vietnam. Returns a list of places with URLs to detailed place information pages and names.',
    'parameters': {
        'type': 'object',
        'properties': {
            'type': {
                'type': 'string',
                'enum': ['hotel', 'restaurant', 'thing-to-do'],
                'description': 'Category of places to retrieve: "hotel" for accommodations, "restaurant" for dining establishments, or "thing-to-do" for tourist attractions and activities',
            },
        },
        'required': ['type'],
    },
}

get_places_by_names_function = {
    'name': 'get_places_by_names',
    'description': 'Find specific places in Da Nang by their names using semantic search. Returns a list of places with URLs to detailed place information pages and names.',
    'parameters': {
        'type': 'object',
        'properties': {
            'names': {
                'type': 'array',
                'items': {'type': 'string'},
                'description': 'List of place names to search for',
            },
        },
        'required': ['names'],
    },
}

# Configure the Gemini client and tools
client = genai.Client(api_key=GEMINI_API_KEY)
tools = types.Tool(
    function_declarations=[
        get_top_places_function,
        get_places_by_names_function,
    ]
)
config = types.GenerateContentConfig(
    system_instruction=SYSTEM_INSTRUCTION, tools=[tools], temperature=0.7
)


class RequestSchema(ma.Schema):
    contents = fields.List(
        fields.Dict(), required=True, validate=validate.Length(min=1)
    )


@bp.post('/embed')
def embed_content():
    result = execute_neo4j_query("""
    MATCH (p)
    WHERE p:Hotel OR p:Restaurant OR p:ThingToDo
    RETURN elementId(p) AS id, p.name AS name, labels(p)[0] AS label
    ORDER BY p.raw_ranking DESC
    """)

    if not result:
        return {'message': 'No places found'}, 404

    # Clear existing embeddings
    db.session.query(VectorItem).delete()
    db.session.commit()

    for item in result:
        embeddings = (
            client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=item['name'],
                config=types.EmbedContentConfig(
                    task_type='RETRIEVAL_DOCUMENT'
                ),
            )
            .embeddings[0]
            .values
        )

        vector_item = VectorItem(
            place_id=item['id'],
            embedding=embeddings,
            type=item['label'].lower()
            if item['label'] != 'ThingToDo'
            else 'thing-to-do',
        )
        db.session.add(vector_item)
        db.session.commit()

    return {'message': 'Embedding completed successfully'}, 200


@bp.post('/')
def create_response():
    data = RequestSchema().load(request.get_json())
    contents: list = data['contents']

    response = client.models.generate_content(
        model=GEMINI_MODEL, contents=contents, config=config
    )
    # Process the function call
    if response.candidates[0].content.parts[0].function_call:
        tool_call = response.candidates[0].content.parts[0].function_call

        result = None
        if tool_call.name == 'get_top_places':
            result = get_top_places(**tool_call.args)
        elif tool_call.name == 'get_places_by_names':
            result = get_places_by_names(**tool_call.args)

        # Append function call and result of the function execution to contents
        contents.extend(
            [
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
                },
                {
                    'role': 'user',
                    'parts': [
                        {
                            'function_response': {
                                'name': tool_call.name,
                                'response': {'result': result},
                            }
                        }
                    ],
                },
            ]
        )

        # Generate final response using the function result
        final_response = client.models.generate_content(
            model=GEMINI_MODEL, config=config, contents=contents
        )
        contents.append(
            {'role': 'model', 'parts': [{'text': final_response.text}]}
        )
    else:
        contents.append({'role': 'model', 'parts': [{'text': response.text}]})

    return {'contents': contents}, 200
