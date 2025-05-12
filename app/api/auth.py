import re

from flask import Blueprint, request
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt_identity,
    jwt_required,
)
from marshmallow import ValidationError, fields, validates
from werkzeug.security import check_password_hash

from app.extensions import CamelCaseAutoSchema, CamelCaseSchema
from app.models import User, db

blueprint = Blueprint('auth', __name__, url_prefix='/auth')


# Sign up
class SignUpSchema(CamelCaseAutoSchema):
    email = fields.Email(required=True)
    password = fields.String(load_only=True)

    class Meta:
        fields = ('email', 'full_name', 'password')
        model = User
        load_instance = True

    @validates('email')
    def validate_email(self, email):
        user = User.query.filter(User.email == email).first()
        if user:
            raise ValidationError('Email already exists')
        return email

    @validates('password')
    def validate_password(self, password):
        pattern = r'^(?=.*[A-Za-z])(?=.*\d)[A-Za-z\d@$!%*?&]{8,}$'
        if not re.match(pattern, password):
            raise ValidationError(
                'Password must be at least 8 characters long, include at least one letter and one number'
            )
        return password


@blueprint.post('/sign-up')
def sign_up():
    schema = SignUpSchema()
    user = schema.load(request.json)
    db.session.add(user)
    db.session.commit()

    return schema.dump(user), 201


# Sign in
class SignInRequestSchema(CamelCaseSchema):
    email = fields.Email(required=True, load_only=True)
    password = fields.String(required=True, load_only=True)


class SignInResponseSchema(CamelCaseSchema):
    access_token = fields.String(required=True, dump_only=True)
    refresh_token = fields.String(required=True, dump_only=True)


@blueprint.post('/sign-in')
def sign_in():
    data = SignInRequestSchema().load(request.json)
    user = User.query.filter(User.email == data['email']).first()
    if type(user) is not User or not check_password_hash(
        user.password, data['password']
    ):
        return {'error': 'Invalid email or password'}, 401

    access_token = create_access_token(identity=str(user.id))
    refresh_token = create_refresh_token(identity=str(user.id))
    return SignInResponseSchema().dump(
        {'access_token': access_token, 'refresh_token': refresh_token}
    ), 200


# Refresh token
class RefreshTokenResponseSchema(CamelCaseSchema):
    access_token = fields.String(required=True, dump_only=True)


@blueprint.post('/refresh')
@jwt_required(refresh=True)
def refresh_token():
    identity = get_jwt_identity()
    access_token = create_access_token(identity=identity)
    return RefreshTokenResponseSchema().dump(
        {'access_token': access_token}
    ), 200
