from flask import Blueprint, abort
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.postgres import UserModel
from app.schemas.users import UserProfileSchema
from app.utils.cache import Cache
from app.utils.response import APIResponse

bp = Blueprint('users', __name__, url_prefix='/users')


@bp.get('/profile')
@jwt_required()
def get_user():
    user_id = get_jwt_identity()
    # Check if the user data is cached
    try:
        cached_data = Cache.get('users', user_id)
        if cached_data:
            return APIResponse.success(data=cached_data)
    except Exception:
        pass

    # Fetch user data from the database
    user = UserModel.query.get(user_id)
    if type(user) is not UserModel:
        abort(404, 'User not found')

    # Cache the user data
    data = UserProfileSchema().dump(user)
    try:
        Cache.set(f'user_{user_id}', data)
    except Exception:
        pass

    return APIResponse.success(data=data)
