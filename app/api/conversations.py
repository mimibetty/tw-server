import logging

from flask import Blueprint
from flask_jwt_extended import get_jwt_identity, jwt_required
from google import genai
from sqlalchemy import select

from app.environments import GEMINI_API_KEY
from app.extensions import CamelCaseAutoSchema
from app.models import UserConversation, db

logger = logging.getLogger(__name__)
blueprint = Blueprint('conversations', __name__, url_prefix='/conversations')

# Initialize the Google Gemini client
client = genai.Client(api_key=GEMINI_API_KEY)


class UserConversationSchema(CamelCaseAutoSchema):
    class Meta:
        model = UserConversation
        load_instance = True


@blueprint.get('/')
@jwt_required()
def get_conversations():
    user_id = get_jwt_identity()
    user_conversations = db.session.execute(
        select(UserConversation).filter_by(user_id=user_id)
    ).scalars()
    return UserConversationSchema(many=True).dump(user_conversations)


class ConversationMessageSchema(CamelCaseAutoSchema):
    class Meta:
        model = UserConversation
        load_instance = True


@blueprint.get('/<conversation_id>')
@jwt_required()
def get_conversation(conversation_id):
    user_id = get_jwt_identity()
    user_conversation = db.session.execute(
        select(UserConversation).filter_by(id=conversation_id, user_id=user_id)
    ).scalar_one_or_none()
    if type(user_conversation) is not UserConversation:
        return {'error': 'Conversation not found'}, 404


@blueprint.post('/')
def create_message_in_conversation():
    pass


@blueprint.delete('/<conversation_id>')
@jwt_required()
def delete_conversation(conversation_id: str):
    user_id = get_jwt_identity()

    user_conversation = db.session.execute(
        select(UserConversation).filter_by(id=conversation_id, user_id=user_id)
    ).scalar_one_or_none()
    if type(user_conversation) is not UserConversation:
        return {'error': 'Conversation not found'}, 404

    db.session.delete(user_conversation)
    db.session.commit()
    return 204
