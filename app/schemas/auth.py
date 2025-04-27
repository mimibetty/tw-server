from marshmallow import ValidationError, fields, validates
from marshmallow.validate import Regexp

from app.constants import OTP_CODE_REGEX, PASSWORD_REGEX
from app.extensions import ma
from app.postgres import UserModel


class SignInSchema(ma.Schema):
    email = fields.Email(required=True)
    password = fields.String(
        required=True,
        validate=Regexp(PASSWORD_REGEX, error='Invalid password format.'),
    )


class SignUpSchema(ma.Schema):
    email = fields.Email(required=True)
    name = fields.String(required=True)
    password = fields.String(
        required=True,
        validate=Regexp(PASSWORD_REGEX, error='Invalid password format.'),
    )

    @validates('email')
    def validate_email(self, value):
        if UserModel.query.filter(UserModel.email == value).first():
            raise ValidationError('Email already exists.')


class SendOTPSchema(ma.Schema):
    email = fields.Email(required=True)
    reset = fields.Boolean(required=True)


class VerifyOTPSchema(ma.Schema):
    email = fields.Email(required=True)
    otp = fields.String(
        required=True,
        validate=Regexp(
            OTP_CODE_REGEX, error='Invalid one-time password format.'
        ),
    )

    @validates('email')
    def validate_email(self, value):
        user = UserModel.query.filter(UserModel.email == value).first()
        if not user:
            raise ValidationError('User not found.')
        if type(user) is UserModel and user.is_verified:
            raise ValidationError('User not verified.')


class MeSchema(ma.Schema):
    id = fields.String(dump_only=True)
    name = fields.String(dump_only=True)
    avatar = fields.String(dump_only=True)


class ForgotPasswordSchema(ma.Schema):
    email = fields.Email(required=True)
    otp = fields.String(
        required=True,
        validate=Regexp(
            OTP_CODE_REGEX, error='Invalid one-time password format.'
        ),
    )
    password = fields.String(
        required=True,
        validate=Regexp(PASSWORD_REGEX, error='Invalid password format.'),
    )
