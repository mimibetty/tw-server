from marshmallow import fields

from app.extensions import ma


class SignInSchema(ma.Schema):
    email = fields.Email(required=True)
    password = fields.String(required=True)


class SignUpSchema(ma.Schema):
    name = fields.String(required=True)
    email = fields.Email(required=True)
    password = fields.String(required=True)


class SendOTPSchema(ma.Schema):
    email = fields.Email(required=True)
    reset = fields.Boolean(required=True)


class VerifyOTPSchema(ma.Schema):
    email = fields.Email(required=True)
    otp = fields.String(required=True)


class MeSchema(ma.Schema):
    id = fields.String(dump_only=True)
    name = fields.String(dump_only=True)
    avatar = fields.String(dump_only=True)


class ForgotPasswordSchema(ma.Schema):
    email = fields.Email(required=True)
    password = fields.String(required=True)
    otp = fields.String(required=True)
