from marshmallow import ValidationError, fields, validates

from app.extensions import ma
from app.postgres import UserConversationsModel


class CreateChatMessageSchema(ma.Schema):
    conversation_id = fields.String(
        required=True,
        allow_none=True,
        error_messages={'required': 'Conversation ID is required.'},
    )
    text = fields.String(
        required=True, error_messages={'required': 'Text is required.'}
    )

    @validates('conversation_id')
    def validate_conversation_id(self, value):
        if value:
            conversation_id = UserConversationsModel.query.filter(
                UserConversationsModel.id == value
            ).first()
            if not conversation_id:
                raise ValidationError('Conversation ID does not exist.')


class GetChatHistorySchema(ma.Schema):
    id = fields.String(dump_only=True)
