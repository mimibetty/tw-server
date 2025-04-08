from marshmallow import ValidationError, fields, validate, validates

from app.constants import OTP_CODE_REGEX, PASSWORD_REGEX
from app.database.postgres import UserModel
from app.extensions import ma


class RegisterSchema(ma.Schema):
    name = fields.String(required=True)
    email = fields.String(
        required=True,
        validate=validate.Email(error='Invalid email address.'),
    )
    password = fields.String(
        required=True,
        validate=validate.Regexp(
            PASSWORD_REGEX, error='Invalid password format.'
        ),
    )

    @validates('email')
    def validate_email(self, value):
        user = UserModel.query.filter(UserModel.email == value).first()
        if user:
            raise ValidationError('Email already exists.')


class LoginSchema(ma.Schema):
    email = fields.String(
        required=True,
        validate=validate.Email(error='Invalid email address.'),
    )
    password = fields.String(
        required=True,
        validate=validate.Regexp(
            PASSWORD_REGEX, error='Invalid password format.'
        ),
    )


class MeSchema(ma.SQLAlchemyAutoSchema):
    class Meta:
        model = UserModel
        fields = [
            'created_at',
            'email',
            'id',
            'is_admin',
            'is_verified',
            'name',
            'updated_at',
        ]


class SendEmailOTPSchema(ma.Schema):
    email = fields.String(
        required=True,
        validate=validate.Email(error='Invalid email address'),
    )


class VerifyEmailSchema(ma.Schema):
    email = fields.String(
        required=True,
        validate=validate.Email(error='Invalid email address'),
    )
    otp_code = fields.String(
        required=True,
        validate=validate.Regexp(
            OTP_CODE_REGEX, error='Invalid OTP code format'
        ),
    )
