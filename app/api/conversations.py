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


class RequestMessageSchema(CamelCaseSchema):
    message = fields.Str(required=True, validate=lambda x: len(x) > 0)


def generate_stream(contents):
    for chunk in client.models.generate_content_stream(
        model='gemini-2.0-flash',
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction="You are a friendly and knowledgeable assistant for a website dedicated to tourism in Da Nang - Quang Nam, Vietnam. Provide accurate, engaging, and concise answers about attractions, culture, cuisine, and travel tips, using a warm, welcoming tone to inspire excitement about visiting. If a question is unrelated to Da Nang or tourism, respond with: 'That question seems outside my focus on Da Nang - Quang Nam tourism.' If unsure about a relevant question, suggest checking with local resources or the website for more details.",
            temperature=1,
            safety_settings=[
                types.SafetySetting(
                    category='HARM_CATEGORY_HATE_SPEECH',
                    threshold='BLOCK_ONLY_HIGH',
                )
            ],
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
