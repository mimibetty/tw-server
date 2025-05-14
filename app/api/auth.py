import json
import logging
import re

from flask import Blueprint, request
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt_identity,
    jwt_required,
)
from marshmallow import ValidationError, fields, validates
from sqlalchemy import select
from werkzeug.security import check_password_hash

from app.extensions import CamelCaseAutoSchema, CamelCaseSchema
from app.models import User, db
from app.utils import get_redis

logger = logging.getLogger(__name__)
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
        user = db.session.execute(
            select(User).filter_by(email=email)
        ).scalar_one_or_none()
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
    user = db.session.execute(
        select(User).filter_by(email=data['email'])
    ).scalar_one_or_none()
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


# Me
class MeSchema(CamelCaseSchema):
    id = fields.UUID(dump_only=True)
    avatar = fields.String(dump_only=True)
    full_name = fields.String(dump_only=True)


@blueprint.get('/me')
@jwt_required()
def get_me():
    user_id = get_jwt_identity()

    # Check if the result is cached
    redis = get_redis()
    redis_key = f'user:{user_id}'
    try:
        cached_user = redis.get(redis_key)
        if cached_user:
            return json.loads(cached_user), 200
    except Exception as e:
        logger.warning('Redis is not available to get data: %s', e)

    user = db.session.execute(
        select(User).filter_by(id=user_id)
    ).scalar_one_or_none()
    if type(user) is not User:
        return {'message': 'User not found'}, 404

    # Cache the user data in Redis in 6 hours
    response = MeSchema().dump(user)
    try:
        redis.set(redis_key, json.dumps(response), ex=21600)
    except Exception as e:
        logger.warning('Redis is not available to set data: %s', e)

    return response, 200
