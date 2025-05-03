from flask import Blueprint, abort, render_template, request
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt_identity,
    jwt_required,
)
from werkzeug.security import check_password_hash, generate_password_hash

from app.postgres import UserModel
from app.schemas.auth import (
    ForgotPasswordSchema,
    MeSchema,
    SendOTPSchema,
    SignInSchema,
    SignUpSchema,
)
from app.utils import generate_otp_code, send_async_email
from app.utils.cache import Cache
from app.utils.response import APIResponse

bp = Blueprint('auth', __name__, url_prefix='/auth')


@bp.post('/sign-in')
def sign_in():
    inputs = SignInSchema().load(request.json)

    # Query user from database
    user = UserModel.query.filter(UserModel.email == inputs['email']).first()
    if not (
        type(user) is UserModel and user.check_password(inputs['password'])
    ):
        abort(400, 'Invalid email or password')

    # Create tokens
    access_token = create_access_token(identity=user.get_id())
    refresh_token = create_refresh_token(identity=user.get_id())
    return APIResponse.success(
        data={'access_token': access_token, 'refresh_token': refresh_token}
    )


@bp.post('/refresh')
@jwt_required(refresh=True)
def refresh():
    try:
        identity = get_jwt_identity()
        access_token = create_access_token(identity=identity)
        return APIResponse.success(data={'access_token': access_token})
    except Exception:
        abort(401, 'Unauthorized')


@bp.post('/sign-up')
def sign_up():
    inputs = SignUpSchema().load(request.json)
    user = UserModel(inputs['email'], inputs['password'], inputs['name'])
    user.add()
    return APIResponse.success(data={'email': user.email}, status=201)


@bp.post('/send-otp')
def send_otp():
    inputs = SendOTPSchema().load(request.json)
    user = UserModel.query.filter(UserModel.email == inputs['email']).first()

    if type(user) is not UserModel:
        abort(404, 'User not found')

    if not inputs['reset'] and user.is_verified:
        abort(400, 'User already verified')

    # Generate OTP code
    otp_code = generate_otp_code()

    # Save to cache
    Cache.delete('otp', inputs['email'])
    Cache.set(
        'otp',
        inputs['email'],
        generate_password_hash(otp_code),
        expire_in_minutes=5,
    )

    # Send OTP code to user's email
    if inputs['reset']:
        # Reset password email
        mail_html = render_template(
            'email_reset_password.html', name=user.name, otp_code=otp_code
        )
        send_async_email(
            subject='Reset Password',
            recipients=[user.email],
            html=mail_html,
        )
    else:
        # Verification email
        mail_html = render_template(
            'email_otp.html', name=user.name, otp_code=otp_code
        )
        send_async_email(
            subject='Email Verification',
            recipients=[user.email],
            html=mail_html,
        )
    return APIResponse.success()


@bp.post('/verify-email')
def verify_email():
    inputs = SendOTPSchema().load(request.json)

    # Check if cache exists
    cache = Cache.get('otp', inputs['email'])
    if not cache or not check_password_hash(cache, inputs['otp']):
        abort(400, 'One-time password is invalid or expired')

    # Query user from database
    user = UserModel.query.filter(UserModel.email == inputs['email']).first()
    if type(user) is not UserModel:
        abort(404, 'User not found')

    if user.is_verified:
        abort(400, 'User already verified')

    # Update user verification status
    user.is_verified = True
    user.update()

    # Delete cache
    Cache.delete('otp', inputs['email'])
    return APIResponse.success()


@bp.get('/me')
@jwt_required()
def me():
    try:
        identity = get_jwt_identity()
        # Check if cache exists
        try:
            cached_data = Cache.get('me', identity)
            if cached_data:
                return APIResponse.success(data=cached_data)
        except Exception:
            pass

        # Query user from database
        user = UserModel.query.get(identity)
        if type(user) is not UserModel:
            abort(404, 'User not found')

        # Save to cache
        data = MeSchema().dump(user)
        Cache.set('me', identity, data)
        return APIResponse.success(data=data)
    except Exception:
        abort(401, 'Unauthorized')


@bp.post('/forgot-password')
def forgot_password():
    inputs = ForgotPasswordSchema().load(request.json)

    # Check if cache exists
    cache = Cache.get('otp', inputs['email'])
    if not cache or not check_password_hash(cache, inputs['otp']):
        abort(400, 'One-time password is invalid or expired')

    # Update user password
    user = UserModel.query.filter(UserModel.email == inputs['email']).first()
    if type(user) is not UserModel:
        abort(404, 'User not found')

    user.password = generate_password_hash(inputs['password'])
    user.update()

    # Remove cache
    Cache.delete('otp', inputs['email'])
    return APIResponse.success()
