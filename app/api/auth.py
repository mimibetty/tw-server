import random

from flask import Blueprint, abort, render_template, request
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt_identity,
    jwt_required,
)
from werkzeug.security import check_password_hash, generate_password_hash

from app.database.postgres import UserModel
from app.schemas.auth import (
    LoginSchema,
    MeSchema,
    RegisterSchema,
    SendEmailOTPSchema,
    VerifyEmailSchema,
)
from app.utils import create_response, send_async_email
from app.utils.cache import Cache

bp = Blueprint('auth', __name__, url_prefix='/auth')


@bp.post('/sign-in')
def sign_in():
    data = LoginSchema().load(request.get_json())
    user = UserModel.query.filter(UserModel.email == data['email']).first()
    if type(user) is not UserModel or not user.check_password(data['password']):
        abort(400, 'Invalid email or password.')

    # Create JWT tokens
    access_token = create_access_token(identity=str(user.id))
    refresh_token = create_refresh_token(identity=str(user.id))
    return create_response(
        message='Signed in successfully.',
        data={
            'access_token': access_token,
            'refresh_token': refresh_token,
        },
    )


@bp.post('/refresh')
@jwt_required(refresh=True)
def refresh():
    identity = get_jwt_identity()
    access_token = create_access_token(identity=identity)
    return create_response(
        message='Token refreshed successfully.',
        data={'access_token': access_token},
    )


@bp.post('/sign-up')
def sign_up():
    data = RegisterSchema().load(request.get_json())
    user = UserModel(**data)
    user.add()
    return create_response(message='Signed up successfully.', status=200)


@bp.post('/send-otp')
def send_otp():
    data = SendEmailOTPSchema().load(request.get_json())
    user = UserModel.query.filter(UserModel.email == data['email']).first()
    if type(user) is not UserModel:
        abort(404, 'User not found.')
    if user.is_verified:
        abort(400, 'User already verified.')

    # Generate OTP code
    otp_code = ''.join([str(random.randint(0, 9)) for _ in range(6)])
    Cache.set(
        f'otp_{data["email"]}',
        generate_password_hash(otp_code),
        expire_in_minutes=5,
    )

    # Send OTP code to user's email
    mail_html = render_template(
        'email_otp.html', name=user.name, otp_code=otp_code
    )
    send_async_email(
        subject='Email Verification', recipients=[user.email], html=mail_html
    )
    return create_response(message='OTP code sent successfully.')


@bp.post('/verify-email')
def verify_email():
    data = VerifyEmailSchema().load(request.get_json())
    cached_data = Cache.get(f'otp_{data["email"]}')
    if not cached_data or not check_password_hash(
        cached_data, data['otp_code']
    ):
        abort(400, 'Invalid OTP code.')

    # Get user from database
    user = UserModel.query.filter(UserModel.email == data['email']).first()
    if type(user) is not UserModel:
        abort(404, 'User not found.')
    if user.is_verified:
        abort(400, 'User already verified.')
    user.is_verified = True
    user.update()

    # Delete OTP cache
    Cache.delete(f'otp_{data["email"]}')
    return create_response(message='Email verified successfully.')


@bp.get('/me')
@jwt_required()
def me():
    # Check cache
    identity = get_jwt_identity()
    cached_data = Cache.get(f'me_{identity}')
    if cached_data:
        return create_response(message='User found.', data=cached_data)

    # Get user from database
    user = UserModel.query.filter(UserModel.id == identity).first()
    if type(user) is not UserModel:
        abort(404, 'User not found.')

    # Response and cache
    response = MeSchema().dump(user)
    Cache.set(f'me_{identity}', response)
    return create_response(message='User found.', data=response)
