import logging
from datetime import datetime, date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from marshmallow import fields, ValidationError, validates, validate
from sqlalchemy import func, or_, and_
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from werkzeug.security import check_password_hash

from app.extensions import ma
from app.models import User, db
from app.utils import create_paging

logger = logging.getLogger(__name__)
blueprint = Blueprint('users', __name__, url_prefix='/users')


class UserSchema(ma.Schema):
    id = fields.UUID(dump_only=True)
    avatar = fields.String(allow_none=True)
    email = fields.Email(required=True)
    is_admin = fields.Boolean(dump_only=True)
    is_verified = fields.Boolean(dump_only=True)
    full_name = fields.String(required=True, validate=validate.Length(min=2, max=100))
    birthday = fields.Date(allow_none=True)
    phone_number = fields.String(allow_none=True, validate=validate.Length(max=20))
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
    password = fields.String(load_only=True)  # This ensures password is never serialized

    @validates('email')
    def validate_email(self, value):
        # Check if email is already taken (for updates, this should be handled differently)
        existing_user = User.query.filter_by(email=value).first()
        if existing_user:
            # This validation will be bypassed for updates by checking context
            if not hasattr(self.context, 'update_user_id') or existing_user.id != self.context.get('update_user_id'):
                raise ValidationError('Email is already registered')
        return value

    @validates('phone_number')
    def validate_phone_number(self, value):
        if value and not value.replace('+', '').replace('-', '').replace(' ', '').isdigit():
            raise ValidationError('Phone number must contain only digits, spaces, hyphens, and plus signs')
        return value

    @validates('birthday')
    def validate_birthday(self, value):
        if value and value > date.today():
            raise ValidationError('Birthday cannot be in the future')
        return value


class UserUpdateSchema(ma.Schema):
    # Regular user fields
    avatar = fields.String(allow_none=True)
    full_name = fields.String(validate=validate.Length(min=2, max=100))
    birthday = fields.Date(allow_none=True)
    phone_number = fields.String(allow_none=True, validate=validate.Length(max=20))
    
    # Admin-only fields
    is_admin = fields.Boolean(load_only=True)
    is_verified = fields.Boolean(load_only=True)
    email = fields.Email()
    
    @validates('phone_number')
    def validate_phone_number(self, value):
        if value and not value.replace('+', '').replace('-', '').replace(' ', '').isdigit():
            raise ValidationError('Phone number must contain only digits, spaces, hyphens, and plus signs')
        return value

    @validates('birthday')
    def validate_birthday(self, value):
        if value and value > date.today():
            raise ValidationError('Birthday cannot be in the future')
        return value

    @validates('is_admin')
    def validate_admin_change(self, value):
        # Only process if field was provided
        if value is None:
            return value
            
        # Check if user has admin privileges
        current_user_id = get_jwt_identity()
        current_user = User.query.filter_by(id=current_user_id).first()
        if not current_user or not current_user.is_admin:
            raise ValidationError('Only admins can modify admin status')

        # Get the target user from context
        target_user = self.context.get('target_user')
        if target_user and target_user.is_admin and value is False:
            # Count total admins
            admin_count = User.query.filter_by(is_admin=True).count()
            if admin_count <= 1:
                raise ValidationError('Cannot remove admin status from the last admin')
        return value

    @validates('email')
    def validate_email(self, value):
        # Only process if field was provided
        if value is None:
            return value
            
        # Check if user has admin privileges
        current_user_id = get_jwt_identity()
        current_user = User.query.filter_by(id=current_user_id).first()
        if not current_user or not current_user.is_admin:
            raise ValidationError('Only admins can modify email')

        # Check if email is already taken
        existing_user = User.query.filter_by(email=value).first()
        if existing_user:
            target_user = self.context.get('target_user')
            if not target_user or existing_user.id != target_user.id:
                raise ValidationError('Email is already registered')
        return value

    @validates('is_verified')
    def validate_verified(self, value):
        # Only process if field was provided
        if value is None:
            return value
            
        # Check if user has admin privileges
        current_user_id = get_jwt_identity()
        current_user = User.query.filter_by(id=current_user_id).first()
        if not current_user or not current_user.is_admin:
            raise ValidationError('Only admins can modify verification status')
        return value

    def load(self, data, *args, **kwargs):
        # Remove admin-only fields for non-admin users
        current_user_id = get_jwt_identity()
        current_user = User.query.filter_by(id=current_user_id).first()
        
        if not current_user or not current_user.is_admin:
            data = data.copy()
            admin_fields = ['is_admin', 'is_verified', 'email']
            for field in admin_fields:
                data.pop(field, None)
                
        return super().load(data, *args, **kwargs)


class UserQuerySchema(ma.Schema):
    page = fields.Integer(missing=1, validate=validate.Range(min=1))
    size = fields.Integer(missing=10, validate=validate.Range(min=1, max=100))
    name = fields.String(allow_none=True)
    order_by = fields.String(
        missing='created_at',
        validate=validate.OneOf(['created_at', 'full_name', 'email', 'updated_at'])
    )
    order_direction = fields.String(
        missing='desc',
        validate=validate.OneOf(['asc', 'desc'])
    )



@blueprint.get('/')
@jwt_required()
def get_users():
    """Get users with pagination and optional name search."""
    try:
        # Validate query parameters
        query_schema = UserQuerySchema()
        try:
            args = query_schema.load(request.args)
        except ValidationError as e:
            return jsonify({'error': 'Invalid query parameters', 'details': e.messages}), 400

        page = args['page']
        size = args['size']
        name_filter = args.get('name')
        order_by = args['order_by']
        order_direction = args['order_direction']

        # Build query
        query = User.query

        # Apply name filter if provided
        if name_filter:
            name_filter = f"%{name_filter.strip()}%"
            query = query.filter(
                or_(
                    User.full_name.ilike(name_filter),
                    User.email.ilike(name_filter)
                )
            )

        # Apply ordering
        order_column = getattr(User, order_by)
        if order_direction == 'desc':
            query = query.order_by(order_column.desc())
        else:
            query = query.order_by(order_column.asc())

        # Get total count for pagination
        total_count = query.count()

        # Apply pagination
        offset = (page - 1) * size
        users = query.offset(offset).limit(size).all()

        # Serialize data
        user_schema = UserSchema(many=True)  # No need to exclude password as it's now load_only
        users_data = user_schema.dump(users)

        # Create pagination response
        result = create_paging(
            data=users_data,
            page=page,
            size=size,
            offset=offset,
            total_count=total_count
        )

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error getting users: {str(e)}")
        return jsonify({'error': 'Failed to get users'}), 500


@blueprint.get('/<uuid:user_id>')
@jwt_required()
def get_user_detail(user_id):
    """Get detailed information about a specific user."""
    try:
        user = User.query.filter_by(id=user_id).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        # Serialize user data (excluding password)
        user_schema = UserSchema(exclude=['password'])
        user_data = user_schema.dump(user)

        # Add additional statistics if needed
        from app.models import UserFavourite, UserReview, UserTrip
        
        # Get user statistics
        favorites_count = UserFavourite.query.filter_by(user_id=user_id).count()
        reviews_count = UserReview.query.filter_by(user_id=user_id).count()
        trips_count = UserTrip.query.filter_by(user_id=user_id).count()
        
        # Get average rating given by user
        avg_rating_result = db.session.query(func.avg(UserReview.rating)).filter_by(user_id=user_id).scalar()
        avg_rating = round(float(avg_rating_result), 1) if avg_rating_result else 0.0

        user_data['statistics'] = {
            'favorites_count': favorites_count,
            'reviews_count': reviews_count,
            'trips_count': trips_count,
            'average_rating_given': avg_rating
        }

        return jsonify(user_data), 200

    except Exception as e:
        logger.error(f"Error getting user detail: {str(e)}")
        return jsonify({'error': 'Failed to get user detail'}), 500


@blueprint.patch('/<uuid:user_id>')
@jwt_required()
def update_user(user_id):
    """Update user information (partial update)."""
    try:
        # Check if requesting user has permission to update this user
        current_user_id = get_jwt_identity()
        current_user = User.query.filter_by(id=current_user_id).first()
        
        # Only allow users to update themselves or admins to update any user
        if str(current_user_id) != str(user_id) and not current_user.is_admin:
            return jsonify({'error': 'Permission denied'}), 403

        # Get the user to update
        user = User.query.filter_by(id=user_id).first()
        if not user:
            return jsonify({'error': 'User not found'}), 404

        # Parse and validate request data
        try:
            data = request.get_json()
            if not data:
                return jsonify({'error': 'Request body must be valid JSON'}), 400
        except Exception as e:
            logger.error(f'JSON parsing error: {str(e)}')
            return jsonify({'error': 'Invalid JSON format'}), 400

        # Validate input data with context
        update_schema = UserUpdateSchema(context={'target_user': user})
        try:
            validated_data = update_schema.load(data)
        except ValidationError as e:
            return jsonify({'error': 'Validation failed', 'details': e.messages}), 400

        # Update only provided fields
        for field, value in validated_data.items():
            if hasattr(user, field):
                setattr(user, field, value)

        db.session.commit()

        # Return updated user data
        user_schema = UserSchema()
        user_data = user_schema.dump(user)

        return jsonify(user_data), 200

    except IntegrityError as e:
        db.session.rollback()
        logger.error(f'Integrity error updating user: {str(e)}')
        if 'users_email_key' in str(e):
            return jsonify({'error': 'Email is already registered'}), 400
        return jsonify({'error': 'Failed to update user due to data constraint'}), 400
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f'Error updating user: {str(e)}')
        return jsonify({'error': 'Failed to update user'}), 500


@blueprint.delete('/<uuid:user_id>')
@jwt_required()
def delete_user(user_id):
    """Delete a user (admin only or self-deletion)."""
    try:
        # Check permissions
        current_user_id = get_jwt_identity()
        current_user = User.query.filter_by(id=current_user_id).first()
        
        # Only allow admins to delete any user, or users to delete themselves
        if str(current_user_id) != str(user_id) and not current_user.is_admin:
            return jsonify({'error': 'Permission denied'}), 403

        # Get the user to delete
        user = User.query.filter_by(id=user_id).first()
        if not user:
            return jsonify({'error': 'User not found'}), 404

        # Prevent deletion of the last admin
        if user.is_admin:
            admin_count = User.query.filter_by(is_admin=True).count()
            if admin_count <= 1:
                return jsonify({'error': 'Cannot delete the last admin user'}), 400

        # Store user info for response
        deleted_user_info = {
            'id': str(user.id),
            'full_name': user.full_name,
            'email': user.email
        }

        # Delete the user (this will cascade to related records due to foreign key constraints)
        db.session.delete(user)
        db.session.commit()

        return jsonify({
            'message': 'User deleted successfully',
            'deleted_user': deleted_user_info
        }), 200

    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f'Error deleting user: {str(e)}')
        return jsonify({'error': 'Failed to delete user'}), 500



@blueprint.patch('/me')
@jwt_required()
def update_current_user():
    """Update current authenticated user's information."""
    try:
        user_id = get_jwt_identity()
        user = User.query.filter_by(id=user_id).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404

        # Parse and validate request data
        try:
            data = request.get_json()
            if not data:
                return jsonify({'error': 'Request body must be valid JSON'}), 400
        except Exception as e:
            logger.error(f'JSON parsing error: {str(e)}')
            return jsonify({'error': 'Invalid JSON format'}), 400

        # Validate input data
        update_schema = UserUpdateSchema()
        try:
            validated_data = update_schema.load(data)
        except ValidationError as e:
            return jsonify({'error': 'Validation failed', 'details': e.messages}), 400

        # Update only provided fields
        for field, value in validated_data.items():
            if hasattr(user, field):
                setattr(user, field, value)

        db.session.commit()

        # Return updated user data
        user_schema = UserSchema(exclude=['password'])
        user_data = user_schema.dump(user)

        return jsonify(user_data), 200

    except IntegrityError as e:
        db.session.rollback()
        logger.error(f'Integrity error updating user: {str(e)}')
        return jsonify({'error': 'Failed to update user due to data constraint'}), 400
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f'Error updating user: {str(e)}')
        return jsonify({'error': 'Failed to update user'}), 500 
    

    
@blueprint.get('/me')
@jwt_required()
def get_current_user():
    """Get current authenticated user's information."""
    try:
        user_id = get_jwt_identity()
        user = User.query.filter_by(id=user_id).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404

        # Serialize user data (excluding password)
        user_schema = UserSchema(exclude=['password'])
        user_data = user_schema.dump(user)

        return jsonify(user_data), 200

    except Exception as e:
        logger.error(f"Error getting current user: {str(e)}")
        return jsonify({'error': 'Failed to get user information'}), 500
