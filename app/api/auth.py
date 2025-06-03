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
from sqlalchemy import select, func
from werkzeug.security import check_password_hash

from app.extensions import ma
from app.models import User, db, UserFavourite, UserReview, UserTrip
from app.utils import get_redis

logger = logging.getLogger(__name__)
blueprint = Blueprint('auth', __name__, url_prefix='/auth')


# Sign up
class SignUpSchema(ma.SQLAlchemyAutoSchema):
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


@blueprint.post('/sign-up/')
def sign_up():
    schema = SignUpSchema()
    user = schema.load(request.json)
    db.session.add(user)
    db.session.commit()

    return schema.dump(user), 201


# Sign in
class SignInRequestSchema(ma.Schema):
    email = fields.Email(required=True, load_only=True)
    password = fields.String(required=True, load_only=True)


class SignInResponseSchema(ma.Schema):
    access_token = fields.String(required=True, dump_only=True)
    refresh_token = fields.String(required=True, dump_only=True)


@blueprint.post('/sign-in/')
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
class RefreshTokenResponseSchema(ma.Schema):
    access_token = fields.String(required=True, dump_only=True)


@blueprint.post('/refresh/')
@jwt_required(refresh=True)
def refresh_token():
    identity = get_jwt_identity()
    access_token = create_access_token(identity=identity)
    return RefreshTokenResponseSchema().dump(
        {'access_token': access_token}
    ), 200


# Me
class MeSchema(ma.Schema):
    id = fields.UUID(dump_only=True)
    avatar = fields.String(dump_only=True, allow_none=True)
    email = fields.Email(dump_only=True)
    is_admin = fields.Boolean(dump_only=True)
    is_verified = fields.Boolean(dump_only=True)
    full_name = fields.String(dump_only=True)
    birthday = fields.Date(dump_only=True, allow_none=True)
    phone_number = fields.String(dump_only=True, allow_none=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)


@blueprint.get('/me/')
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
        return {'error': 'User not found'}, 404

    # Get user data
    response = MeSchema().dump(user)
    
    # Add user statistics
    # Get user statistics
    favorites_count = db.session.query(UserFavourite).filter_by(user_id=user_id).count()
    reviews_count = db.session.query(UserReview).filter_by(user_id=user_id).count()
    trips_count = db.session.query(UserTrip).filter_by(user_id=user_id).count()
    
    # Get average rating given by user
    avg_rating_result = db.session.query(func.avg(UserReview.rating)).filter_by(user_id=user_id).scalar()
    avg_rating = round(float(avg_rating_result), 1) if avg_rating_result else 0.0
    
    response['statistics'] = {
        'favorites_count': favorites_count,
        'reviews_count': reviews_count,
        'trips_count': trips_count,
        'average_rating_given': avg_rating
    }

    # Cache the user data in Redis in 6 hours
    try:
        redis.set(redis_key, json.dumps(response), ex=21600)
    except Exception as e:
        logger.warning('Redis is not available to set data: %s', e)

    return response, 200
