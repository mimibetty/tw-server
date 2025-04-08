from marshmallow import ValidationError, fields, validate, validates

from app.constants import PASSWORD_REGEX
from app.database.postgres import UserModel
from app.extensions import ma


class UserSchema(ma.SQLAlchemyAutoSchema):
    id = fields.UUID(dump_only=True)
    created_at = fields.NaiveDateTime(dump_only=True)
    updated_at = fields.NaiveDateTime(dump_only=True)
    email = fields.String(
        required=True,
        validate=validate.Email(error='Invalid email address'),
    )
    password = fields.String(
        required=True,
        validate=[
            validate.Length(
                min=8, error='Password must be at least 8 characters long'
            ),
            validate.Length(
                max=32, error='Password must be at most 32 characters long'
            ),
            validate.Regexp(
                regex=PASSWORD_REGEX, error='Invalid password format'
            ),
        ],
    )
    name = fields.String(required=True)
    is_admin = fields.Boolean(dump_only=True)
    is_verified = fields.Boolean(dump_only=True)

    @validates('email')
    def validate_username(self, value):
        user = UserModel.query.filter(UserModel.email == value).first()
        if user:
            raise ValidationError('Email already exists')

    class Meta:
        model = UserModel
        load_instance = True
        fields = [
            'id',
            'created_at',
            'updated_at',
            'email',
            'password',
            'name',
            'is_admin',
            'is_verified',
        ]
