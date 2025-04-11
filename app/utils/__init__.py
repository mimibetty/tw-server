import json

from flask import Response
from flask_mail import Message
from google import genai

from app.environments import GEMINI_API_KEY


def create_response(data=None, message: str = 'Success', status: int = 200):
    body = json.dumps(
        {'data': data, 'message': message, 'status': status}, sort_keys=True
    )
    return Response(response=body, status=status, mimetype='application/json')


def request_gemini(contents: str, model: str = 'gemini-2.0-flash'):
    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(model=model, contents=contents)
    return response.text


def send_async_email(recipients: list[str], subject: str, html: str):
    from threading import Thread

    from app import AppContext
    from app.extensions import mail

    def send_email(message: Message):
        app = AppContext().get_app()
        with app.app_context():
            mail.send(message)

    message = Message(
        subject=subject,
        sender=('TripWise', 'tripwise@no-reply.com'),
        recipients=recipients,
    )
    message.html = html
    thread = Thread(target=send_email, args=(message,))
    thread.start()
