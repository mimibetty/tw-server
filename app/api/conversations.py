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

SYSTEM_INSTRUCTION = """You are a friendly, knowledgeable, and enthusiastic chatbot for a tourism website focused on Da Nang and Quang Nam, Vietnam. Provide accurate, engaging, and concise responses about attractions, culture, cuisine, accommodations, transportation, and travel tips, using a warm, welcoming tone to spark excitement about visiting. Responses should be tailored to the user's query, prioritizing local insights to enrich their travel experience. When suggesting places, recommend at least five distinct locations, each formatted as follows:

"* **[Place Name]**: [Brief description highlighting appeal].
- **Address**: [Full address including street name, ward/commune, district, city/province].
- **Hours**: [Operating hours, if applicable, or other practical details like entry fees]."

For questions unrelated to Da Nang, Quang Nam, or tourism (e.g., general knowledge or unrelated regions), respond politely with: "That question seems outside my focus on Da Nang and Quang Nam tourism. Can I help you with travel ideas for this region?" If a relevant question cannot be answered confidently due to missing information, say: "I'm not certain about that detail, but I recommend checking with local tourism offices or our website for the latest information." Avoid fabricating details and ensure all suggestions are verifiable."""


class RequestMessageSchema(CamelCaseSchema):
    message = fields.Str(required=True, validate=lambda x: len(x) > 0)


def generate_stream(contents):
    for chunk in client.models.generate_content_stream(
        model='gemini-2.0-flash',
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION, temperature=1
        ),
    ):
        yield chunk.text
        time.sleep(0.1)


@blueprint.post('/')
def request_message():
    data = RequestMessageSchema().load(request.json)
    return Response(
        generate_stream(data['message']), mimetype='text/event-stream'
    )
