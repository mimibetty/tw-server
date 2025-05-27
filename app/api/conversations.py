import logging

from flask import Blueprint, request
from google import genai
from google.genai import types
from marshmallow import fields
from sqlalchemy import select

from app.environments import FRONTEND_URL, GEMINI_API_KEY
from app.extensions import ma
from app.models import VectorItem, db
from app.utils import execute_neo4j_query

logger = logging.getLogger(__name__)
blueprint = Blueprint('conversations', __name__, url_prefix='/conversations')

# Configuration
TEXT_MODEL_ID = 'models/text-embedding-004'
GEMINI_MODEL_ID = 'gemini-2.0-flash'

client = genai.Client(api_key=GEMINI_API_KEY)


def embed_fn(name: str, description: str):
    return (
        client.models.embed_content(
            model=TEXT_MODEL_ID,
            contents=[name, description],
            config=types.EmbedContentConfig(task_type='RETRIEVAL_DOCUMENT'),
        )
        .embeddings[0]
        .values
    )


# Schema
class RequestMessageSchema(ma.Schema):
    message = fields.Str(required=True, validate=lambda x: len(x) > 0)


@blueprint.post('/embed')
def embed_system():
    places = execute_neo4j_query("""
    MATCH (n)
    WHERE (n:Hotel OR n:Restaurant OR n:ThingToDo)
        AND n.description IS NOT NULL
    RETURN
        elementId(n) AS elementId,
        n.name AS name,
        n.description AS description,
        n.ai_reviews_summary AS ai_summary
    ORDER BY n.raw_ranking DESC
    """)
    if not places:
        return {'message': 'No places found.'}, 404

    # Clear existing embeddings and create extension
    db.session.query(VectorItem).delete()
    db.session.commit()

    # Process each place
    for place in places:
        place_name = place['name']
        description = place['description']
        if place['ai_summary']:
            description += f'\nSummary: {place["ai_summary"]}'

        item = VectorItem(
            place_id=place['elementId'],
            embedding=embed_fn(name=place_name, description=description),
        )
        db.session.add(item)
        db.session.commit()

    return {'message': 'Embeddings created successfully.'}, 201


def suggest_places_with_short_description(description):
    # Embed the message
    query_embedding = (
        client.models.embed_content(
            model=TEXT_MODEL_ID,
            contents=[description],
            config=types.EmbedContentConfig(task_type='RETRIEVAL_QUERY'),
        )
        .embeddings[0]
        .values
    )

    # Find similar places with threshold
    threshold = 0.88
    similar_places = db.session.scalars(
        select(VectorItem)
        .filter(VectorItem.embedding.l2_distance(query_embedding) < threshold)
        .limit(3)
    ).all()
    if not similar_places:
        return []

    similar_place_ids = [item.place_id for item in similar_places]
    similar_places_details = execute_neo4j_query(
        """
        MATCH (n)
        WHERE
            elementId(n) IN $place_ids
        RETURN
            elementId(n) AS elementId,
            n.name AS name,
            n.description AS description,
            lower(n.type) AS type
        """,
        {'place_ids': similar_place_ids},
    )
    if not similar_places_details:
        return []

    return [
        {
            'element_id': place['elementId'],
            'name': place['name'],
            'description': place['description'],
            'type': place['type'],
        }
        for place in similar_places_details
    ]


# Define the function declaration for the model
suggest_places_function = {
    'name': 'suggest_places_with_short_description',
    'description': 'Suggest places based on a short description.',
    'parameters': {
        'type': 'object',
        'properties': {
            'description': {
                'type': 'string',
                'description': 'A short description of the place.',
            },
        },
        'required': ['description'],
    },
}

# Configure the tools
tools = types.Tool(function_declarations=[suggest_places_function])
config = types.GenerateContentConfig(
    system_instruction=(
        'You are a knowledgeable and friendly assistant specializing in tourism in Da Nang, Vietnam.',
        ' When users request recommendations, generate a concise description based on their input and use the suggest_places_with_short_description function to retrieve a list of relevant places.',
        f' For each recommendations, format the response as [**{{name}}**]({FRONTEND_URL}/{{type}}/{{element_id}}): {{description}}',
        ' Format all responses in clear, well-structured Markdown, using headings, bullet points, or numbered lists as appropriate for readability.',
        " If a user's question is unrelated to tourism in Da Nang, politely decline to answer and explain that your expertise is limited to Da Nang tourism, offering to assist with a relevant query instead.",
        " If the user's request is ambiguous, ask for clarification to provide the most accurate suggestions.",
    ),
    tools=[tools],
)


@blueprint.post('/')
def find_similar():
    request_data = RequestMessageSchema().load(request.get_json())
    message = request_data['message']

    # Define user prompt
    contents = [
        types.Content(role='user', parts=[types.Part(text=message)]),
    ]

    # Send request with function declarations
    response = client.models.generate_content(
        model=GEMINI_MODEL_ID, contents=contents, config=config
    )

    # Check for a function call
    if response.candidates[0].content.parts[0].function_call:
        tool_call = response.candidates[0].content.parts[0].function_call
        if tool_call.name == 'suggest_places_with_short_description':
            result = suggest_places_with_short_description(**tool_call.args)

            # Create a function response part
            function_response_part = types.Part.from_function_response(
                name=tool_call.name, response={'result': result}
            )

            # Append function call and result of the function execution to contents
            contents.append(
                types.Content(
                    role='model', parts=[types.Part(function_call=tool_call)]
                )
            )
            contents.append(
                types.Content(role='user', parts=[function_response_part])
            )

            final_response = client.models.generate_content(
                model=GEMINI_MODEL_ID, contents=contents, config=config
            )
            return {'message': final_response.text}, 200
    else:
        return {'message': response.text}, 200
