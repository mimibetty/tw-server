import logging
import re

from flask import Blueprint, abort, render_template, request
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt_identity,
    jwt_required,
)

from app.constants import (
    EMAIL_REGEX,
    INVALID_INPUT,
    OTP_CODE_REGEX,
    PASSWORD_REGEX,
)
from app.postgres import UserModel
from app.utils import generate_otp_code
from app.utils.cache import Cache
from app.utils.response import APIResponse

logger = logging.getLogger(__name__)
bp = Blueprint('auth', __name__, url_prefix='/auth')


@bp.post('/sign-in')
def sign_in():
    data = request.get_json()
    email = data['email']
    password = data['password']

    if not (
        all([email, password])
        and re.match(EMAIL_REGEX, email)
        and re.match(PASSWORD_REGEX, password)
    ):
        abort(400, INVALID_INPUT)

    # Get user from database
    user: UserModel = UserModel.query.filter(
        UserModel.email == email
    ).first_or_404()
    if not user.check_password(password):
        abort(400, 'Invalid email or password')

    # Create JWT tokens
    access_token = create_access_token(identity=user.get_id())
    refresh_token = create_refresh_token(identity=user.get_id())
    return APIResponse.success(
        message='Sign in successfully',
        payload={'accessToken': access_token, 'refreshToken': refresh_token},
    )


@bp.post('/refresh')
@jwt_required(refresh=True)
def refresh():
    identity = get_jwt_identity()
    access_token = create_access_token(identity=identity)
    return APIResponse.success(
        message='Token refreshed successfully',
        payload={'accessToken': access_token},
    )


@bp.post('/sign-up')
def sign_up():
    data = request.get_json()
    name = data['name']
    email = data['email']
    password = data['password']

    if not (
        all([name, email, password])
        and re.match(EMAIL_REGEX, email)
        and re.match(PASSWORD_REGEX, password)
    ):
        abort(400, INVALID_INPUT)

    # Check if user already exists
    existing_user = UserModel.query.filter(UserModel.email == email).first()
    if type(existing_user) is UserModel:
        abort(400, 'Email already exists')

    # Query database
    user = UserModel(email, password, name)
    user.add()
    return APIResponse.success(message='Sign up successfully', status=201)


@bp.post('/send-otp')
def send_otp():
    from werkzeug.security import generate_password_hash

    from app.utils import send_async_email

    data = request.get_json()
    email = data['email']
    reset = bool(data['reset'])

    if not (
        all([email, reset])
        and re.match(EMAIL_REGEX, email)
        and type(reset) is bool
    ):
        abort(400, INVALID_INPUT)

    # Check if user exists
    user: UserModel = UserModel.query.filter(
        UserModel.email == email
    ).first_or_404()

    if not reset and user.is_verified:
        abort(400, 'User already verified')

    # Generate OTP code
    otp_code = generate_otp_code()
    Cache.delete('otp', email)
    Cache.set(
        'otp', email, generate_password_hash(otp_code), expire_in_minutes=5
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

    return APIResponse.success(message='One-time password sent successfully')


@bp.post('/verify-email')
def verify_email():
    from werkzeug.security import check_password_hash

    data = request.get_json()
    email = data['email']
    otp_code = data['otp_code']

    if not (
        all([email, otp_code])
        and re.match(EMAIL_REGEX, email)
        and re.match(OTP_CODE_REGEX, otp_code)
    ):
        abort(400, INVALID_INPUT)

    cached_data = Cache.get('otp', email)
    if not cached_data or not check_password_hash(cached_data, otp_code):
        abort(400, 'One-time password is invalid or expired')

    # Update user verification status
    user: UserModel = UserModel.query.filter(
        UserModel.email == email
    ).first_or_404()
    if user.is_verified:
        abort(400, 'User already verified')

    user.is_verified = True
    user.update()

    # Delete cache
    Cache.delete('otp', email)
    return APIResponse.success(message='Email verified successfully')


@bp.get('/me')
@jwt_required()
def me():
    # Check cache
    identity = get_jwt_identity()
    try:
        cached_data = Cache.get('me', identity)
        if cached_data:
            return APIResponse.success(payload=cached_data)
    except Exception:
        pass

    # Get user from database
    user: UserModel = UserModel.query.filter(
        UserModel.id == identity
    ).first_or_404()

    data = {'id': user.id, 'avatar': user.avatar, 'name': user.name}
    try:
        Cache.set('me', identity, data)
    except Exception as e:
        logger.error(f'Error caching ME endpoint: {e}')

    return APIResponse.success(payload=data)


@bp.post('/forgot-password')
def forgot_password():
    from werkzeug.security import check_password_hash, generate_password_hash

    # Input validation
    data = request.get_json()
    email = data['email']
    otp_code = data['otp_code']
    new_password = data['new_password']

    if not (
        all([email, otp_code, new_password])
        and re.match(EMAIL_REGEX, email)
        and re.match(OTP_CODE_REGEX, otp_code)
        and re.match(PASSWORD_REGEX, new_password)
    ):
        abort(400, INVALID_INPUT)

    # Check cache
    cached_data = Cache.get('otp', email)
    if not cached_data or not check_password_hash(cached_data, otp_code):
        abort(400, 'One-time password is invalid or expired')

    # Update user password
    user: UserModel = UserModel.query.filter(
        UserModel.email == email
    ).first_or_404()
    user.password = generate_password_hash(new_password)
    user.update()

    # Delete cache
    Cache.delete('otp', email)
    return APIResponse.success(message='Password reset successfully')
