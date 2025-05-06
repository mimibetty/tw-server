from flask import Blueprint, abort, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.postgres import (
    MessagesModel,
    UserConversationsModel,
)
from app.schemas.chat import (
    ChatMessageSchema,
    CreateChatMessageSchema,
    GetChatHistorySchema,
)
from app.utils import request_gemini
from app.utils.response import APIResponse

bp = Blueprint('chat', __name__, url_prefix='/chat')


@bp.post('/')
@jwt_required()
def create_chat_message():
    identity = get_jwt_identity()
    inputs = CreateChatMessageSchema().load(request.json)

    # Save chat conversation if it doesn't exist
    if not UserConversationsModel.query.filter(
        UserConversationsModel.id == inputs['id']
    ).first():
        new_conversation = UserConversationsModel(
            conversation_id=inputs['id'], user_id=identity
        )
        new_conversation.add()

    # Request to Gemini API
    chat_response = request_gemini(contents=inputs['text'])

    # Save user message to the database
    user_message = MessagesModel(
        conversation_id=inputs['id'], text=inputs['text'], is_user=True
    )
    user_message.add()

    # Save bot message to the database
    bot_message = MessagesModel(
        conversation_id=inputs['id'], text=chat_response, is_user=False
    )
    bot_message.add()

    return APIResponse.success(
        data=ChatMessageSchema().dump(bot_message), status=201
    )


@bp.get('')
@jwt_required()
def get_chat_history():
    identity = get_jwt_identity()
    conversations = (
        UserConversationsModel.query.filter(
            UserConversationsModel.user_id == identity
        )
        .order_by(UserConversationsModel.created_at.desc())
        .all()
    )
    return APIResponse.success(
        data=GetChatHistorySchema(many=True).dump(conversations)
    )


@bp.get('/messages')
@jwt_required()
def get_history_messages():
    conversation_id = request.args.get('id')
    if not conversation_id:
        abort(400, 'Conversation ID is required.')

    identity = get_jwt_identity()
    if not UserConversationsModel.query.filter(
        UserConversationsModel.user_id == identity,
        UserConversationsModel.id == conversation_id,
    ).first():
        return APIResponse.success(data=[])

    result = (
        MessagesModel.query.filter(
            MessagesModel.conversation_id == conversation_id
        )
        .order_by(MessagesModel.created_at.desc())
        .all()
    )
    return APIResponse.success(data=ChatMessageSchema(many=True).dump(result))
