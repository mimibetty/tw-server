import logging
import time

from flask import Blueprint, Response, request
from google import genai
from google.genai import types
from marshmallow import fields

from app.environments import GEMINI_API_KEY
from app.extensions import CamelCaseSchema

logger = logging.getLogger(__name__)
blueprint = Blueprint('conversations', __name__, url_prefix='/conversations')

# Initialize the Google Gemini client
client = genai.Client(api_key=GEMINI_API_KEY)

SYSTEM_INSTRUCTION = """You are a friendly, enthusiastic chatbot for a Vietnam tourism website. Deliver accurate, concise, and engaging responses about attractions, culture, cuisine, accommodations, transportation, and travel tips in a warm, welcoming tone to inspire excitement. Tailor answers to the user's query, emphasizing local insights. For place recommendations, suggest at least five unique locations, formatted as:
"- [Place Name] at [Full Address] ([Hours]): [Brief appeal]. [Entry fees, if applicable]."

For non-tourism questions, respond: "That's outside my Vietnam tourism focus." If unsure about a relevant detail, say: "I'm not certain, but check with local tourism offices or our website." Avoid fabricating details and ensure all suggestions are verifiable."""


class RequestMessageSchema(CamelCaseSchema):
    message = fields.Str(required=True, validate=lambda x: len(x) > 0)


def generate_stream(message):
    for chunk in client.models.generate_content_stream(
        model='gemini-2.0-flash',
        contents=[{'role': 'user', 'parts': [message]}],
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
        ),
    ):
        if chunk.text is not None:
            yield chunk.text
        time.sleep(0.1)


@blueprint.post('/')
def request_message():
    data = RequestMessageSchema().load(request.get_json())
    if not isinstance(data, dict) or 'message' not in data:
        return {'error': 'Invalid input data.'}, 400

    message = data['message']
    return Response(generate_stream(message), mimetype='text/event-stream')
