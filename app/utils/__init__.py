def get_neo4j():
    """Create a Neo4j driver instance."""
    from neo4j import GraphDatabase

    from ..environments import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USERNAME

    return GraphDatabase.driver(
        NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD)
    )


def request_gemini(contents: str, model: str = 'gemini-2.0-flash'):
    """Request the Gemini API to generate content."""
    from google import genai

    from ..environments import GEMINI_API_KEY

    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(model=model, contents=contents)
    return response.text


def send_async_email(recipients: list[str], subject: str, html: str):
    """Send an email asynchronously."""
    from threading import Thread

    from flask_mail import Message

    from .. import AppContext
    from ..extensions import mail

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


def generate_otp_code(length: int = 6) -> str:
    """Generate a random OTP code."""
    from random import randint

    return ''.join([str(randint(0, 9)) for _ in range(length)])
