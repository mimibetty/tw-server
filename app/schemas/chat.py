from marshmallow import fields

from app.extensions import ma


class CreateChatMessageSchema(ma.Schema):
    conversation_id = fields.String(
        required=True,
        allow_none=True,
        error_messages={'required': 'Conversation ID is required.'},
    )
    text = fields.String(
        required=True, error_messages={'required': 'Text is required.'}
    )


class GetChatHistorySchema(ma.Schema):
    id = fields.String(dump_only=True)


class ChatMessageSchema(ma.Schema):
    id = fields.String(load_only=True)
    text = fields.String()
    is_user = fields.Boolean(dump_only=True)
