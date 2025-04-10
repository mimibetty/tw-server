from flask import Blueprint, abort, request

from app.database.postgres import UserModel
from app.schemas.users import UserSchema
from app.utils import create_response

bp = Blueprint('users', __name__, url_prefix='/users')


@bp.get('/')
def get_users():
    # Pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)

    # Filter parameters
    email = request.args.get('email', None, type=str)
    order_by = request.args.get('order_by', '-created_at', str)

    query = UserModel.query
    if email:
        query = query.filter(UserModel.email.ilike(f'%{email}%'))

    match order_by:
        case '-created_at':
            query = query.order_by(UserModel.created_at.desc())
        case 'created_at':
            query = query.order_by(UserModel.created_at.asc())
        case '-updated_at':
            query = query.order_by(UserModel.updated_at.desc())
        case 'updated_at':
            query = query.order_by(UserModel.updated_at.asc())
        case '-email':
            query = query.order_by(UserModel.email.desc())
        case 'email':
            query = query.order_by(UserModel.email.asc())
        case _:
            abort(400, 'Invalid parameter')

    users: list[UserModel] = query.paginate(
        page, per_page, max_per_page=50, error_out=False
    )
    return create_response(
        message='Users retrieved successfully',
        data=UserSchema().dump(users, many=True),
    )


@bp.post('/')
def create_user():
    user: UserModel = UserSchema().load(request.get_json())
    user.add()
    return create_response(data=UserSchema().dump(user), status=201)


@bp.get('/<user_id>')
def retrieve_user(user_id: str):
    user = UserModel.query.get_or_404(user_id)
    return create_response(
        message='User retrieved successfully',
        data=UserSchema().dump(user),
    )


@bp.put('/<user_id>')
def update_user(user_id: str):
    user = UserModel.query.get_or_404(user_id)
    updated_user: UserModel = UserSchema().load(
        data=request.get_json(), instance=user, partial=True
    )
    updated_user.save()
    return create_response(
        message='User updated successfully',
        data=UserSchema().dump(updated_user),
    )


@bp.delete('/<user_id>')
def delete_user(user_id: str):
    user: UserModel = UserModel.query.get_or_404(user_id)
    user.delete()
    return create_response(message='User deleted successfully', status=204)
