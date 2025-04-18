import re
from random import randint

from flask import Blueprint, abort, render_template, request
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt_identity,
    jwt_required,
)
from werkzeug.security import check_password_hash, generate_password_hash

from app.constants import (
    EMAIL_REGEX,
    INVALID_INPUT,
    OTP_CODE_REGEX,
    PASSWORD_REGEX,
)
from app.postgres import UserModel
from app.utils import create_response, send_async_email
from app.utils.cache import Cache

bp = Blueprint('auth', __name__, url_prefix='/auth')


@bp.post('/sign-in')
def sign_in():
    # Input validation
    email = request.json.get('email')
    password = request.json.get('password')
    if not (
        all([email, password])
        and re.match(EMAIL_REGEX, email)
        and re.match(PASSWORD_REGEX, password)
    ):
        abort(400, INVALID_INPUT)

    # Get user from database
    user = UserModel.query.filter(UserModel.email == email).first()
    if type(user) is not UserModel or not user.check_password(password):
        abort(400, 'Invalid email or password.')

    # Create JWT tokens
    access_token = create_access_token(identity=user.get_id())
    refresh_token = create_refresh_token(identity=user.get_id())
    return create_response(
        data={'accessToken': access_token, 'refreshToken': refresh_token}
    )


@bp.post('/refresh')
@jwt_required(refresh=True)
def refresh():
    identity = get_jwt_identity()
    access_token = create_access_token(identity=identity)
    return create_response(data={'accessToken': access_token})


@bp.post('/sign-up')
def sign_up():
    # Input validation
    name = request.json.get('name')
    email = request.json.get('email')
    password = request.json.get('password')
    if not (
        all([name, email, password])
        and re.match(EMAIL_REGEX, email)
        and re.match(PASSWORD_REGEX, password)
    ):
        abort(400)

    # Check if user already exists
    existing_user = UserModel.query.filter(UserModel.email == email).first()
    if type(existing_user) is UserModel:
        abort(400, 'Email already exists.')

    # Query database
    user = UserModel(email, password, name)
    user.add()
    return create_response()


@bp.post('/send-otp')
def send_otp():
    # Input validation
    email = request.json.get('email')
    reset = request.json.get('reset')
    if not (
        all([email, reset])
        and re.match(EMAIL_REGEX, email)
        and type(reset) is bool
    ):
        abort(400)

    # Check if user exists
    user: UserModel = UserModel.query.filter(
        UserModel.email == email
    ).first_or_404()
    if user.is_verified:
        abort(400, 'User already verified.')

    # Generate OTP code
    otp_code = ''.join([str(randint(0, 9)) for _ in range(6)])
    Cache.delete(f'otp_{email}')
    Cache.set(
        f'otp_{email}', generate_password_hash(otp_code), expire_in_minutes=5
    )

    # Send OTP code via email
    if reset:
        mail_html = render_template(
            'email_reset_password.html', name=user.name, otp_code=otp_code
        )
        send_async_email(
            subject='Reset Password', recipients=[user.email], html=mail_html
        )
    else:
        mail_html = render_template(
            'email_otp.html', name=user.name, otp_code=otp_code
        )
        send_async_email(
            subject='Email Verification',
            recipients=[user.email],
            html=mail_html,
        )
    return create_response(message='One-time password sent successfully.')


@bp.post('/verify-email')
def verify_email():
    # Input validation
    email = request.json.get('email')
    otp_code = request.json.get('otp_code')
    if not (
        all([email, otp_code])
        and re.match(EMAIL_REGEX, email)
        and re.match(OTP_CODE_REGEX, otp_code)
    ):
        abort(400)

    cached_data = Cache.get(f'otp_{email}')
    if not cached_data or not check_password_hash(cached_data, otp_code):
        abort(400, 'One-time password is invalid or expired.')

    # Update user verification status
    user: UserModel = UserModel.query.filter(
        UserModel.email == email
    ).first_or_404()
    if user.is_verified:
        abort(400, 'User already verified.')

    user.is_verified = True
    user.update()

    # Delete cache
    Cache.delete(f'otp_{email}')
    return create_response(message='Email verified successfully.')


@bp.get('/me')
@jwt_required()
def me():
    # Check cache
    identity = get_jwt_identity()
    try:
        cached_data = Cache.get(f'me_{identity}')
        if cached_data:
            return create_response(dat=cached_data)
    except Exception:
        pass

    # Get user from database
    user: UserModel = UserModel.query.filter(
        UserModel.id == identity
    ).first_or_404()

    # Response and cache
    data = {'id': user.id, 'avatar': user.avatar, 'name': user.name}
    try:
        Cache.set(f'me_{identity}', data)
    except Exception:
        pass

    return create_response(data=data)


@bp.post('/forgot-password')
def forgot_password():
    # Input validation
    email = request.json.get('email')
    otp_code = request.json.get('otp_code')
    new_password = request.json.get('new_password')
    if not (
        all([email, otp_code, new_password])
        and re.match(EMAIL_REGEX, email)
        and re.match(OTP_CODE_REGEX, otp_code)
        and re.match(PASSWORD_REGEX, new_password)
    ):
        abort(400)

    # Check cache
    cached_data = Cache.get(f'otp_{email}')
    if not cached_data or not check_password_hash(cached_data, otp_code):
        abort(400, 'One-time password is invalid or expired.')

    # Update user password
    user: UserModel = UserModel.query.filter(
        UserModel.email == email
    ).first_or_404()
    user.password = generate_password_hash(new_password)
    user.update()

    # Delete cache
    Cache.delete(f'otp_{email}')
    return create_response(message='Password reset successfully.')
