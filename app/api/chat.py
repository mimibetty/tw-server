from flask import Blueprint, abort, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.constants import MAX_PAGINATION_PER_PAGE
from app.postgres import UserConversationsModel, UserMessagesModel
from app.schemas.chat import CreateChatMessageSchema, GetChatHistorySchema
from app.utils import request_gemini
from app.utils.response import APIResponse

bp = Blueprint('chat', __name__, url_prefix='/chat')


@bp.post('/')
@jwt_required()
def create_chat_message():
    identity = get_jwt_identity()
    inputs = CreateChatMessageSchema().load(request.json)

    # Save chat conversation if it doesn't exist
    conversation_id = inputs['conversation_id']
    if not conversation_id:
        new_conversation = UserConversationsModel(user_id=identity)
        new_conversation.add()
        conversation_id = new_conversation.id

    # Request to Gemini API
    chat_response = request_gemini(contents=inputs['text'])

    # Save user message to the database
    user_message = UserMessagesModel(
        conversation_id=conversation_id, text=inputs['text']
    )
    user_message.add()

    # Save bot message to the database
    bot_message = UserMessagesModel(
        conversation_id=conversation_id, text=chat_response
    )
    bot_message.add()

    return APIResponse.success(
        data={'conversation_id': conversation_id, 'message': chat_response},
        status=201,
    )


@bp.get('')
@jwt_required()
def get_chat_history():
    identity = get_jwt_identity()
    conversations = UserConversationsModel.query.filter(
        UserConversationsModel.user_id == identity
    ).all()
    return APIResponse.success(
        data=GetChatHistorySchema(many=True).dump(conversations)
    )


@bp.get('/<conversation_id>')
@jwt_required()
def get_chat_messages(conversation_id):
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)

    identity = get_jwt_identity()
    if not UserConversationsModel.query.filter(
        UserConversationsModel.user_id == identity,
        UserConversationsModel.id == conversation_id,
    ).first():
        abort(404, 'Conversation not found.')

    result = (
        UserMessagesModel.query.filter(
            UserMessagesModel.conversation_id == conversation_id
        )
        .order_by(UserMessagesModel.created_at.desc())
        .paginate(
            page=page, per_page=per_page, max_per_page=MAX_PAGINATION_PER_PAGE
        )
    )
    return APIResponse.paginate(
        data=result.items,
        total_records=result.total,
        page=result.page,
        per_page=result.per_page,
    )
