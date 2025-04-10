import uuid

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import (
    ARRAY,
    UUID,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase
from werkzeug.security import check_password_hash, generate_password_hash


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)


class BaseModel(db.Model):
    """Base model for all models."""

    __abstract__ = True

    # Common fields for all models
    id = Column(
        UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4
    )
    created_at = Column(
        DateTime(timezone=True), server_default=func.current_timestamp()
    )
    updated_at = Column(
        DateTime(timezone=True),
        onupdate=func.current_timestamp(),
        server_default=func.current_timestamp(),
    )

    def add(self):
        """Add a new record to the database."""
        try:
            db.session.add(self)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            raise e

    def update(self):
        """Update an existing record in the database."""
        try:
            db.session.merge(self)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            raise e

    def delete(self):
        """Delete a record from the database."""
        try:
            db.session.delete(self)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            raise e

    def __repr__(self):
        return f'<{self.__class__.__name__} {self.id}>'


class UserModel(BaseModel):
    __tablename__ = 'users'

    # Fields
    avatar = Column(String(255), nullable=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    is_admin = Column(Boolean, nullable=False, default=False)
    is_verified = Column(Boolean, nullable=False, default=False)
    name = Column(String(255), nullable=False)
    password = Column(String(255), nullable=False)

    def __init__(
        self, email: str, password: str, name: str, is_admin: bool = False
    ):
        super().__init__()
        self.email = email
        self.password = generate_password_hash(password)
        self.name = name
        self.is_admin = is_admin

    def check_password(self, password: str) -> bool:
        """Check if the provided password matches the stored password."""
        return check_password_hash(self.password, password)


class UserReviewModel(BaseModel):
    __tablename__ = 'user_reviews'

    # Fields
    images = Column(ARRAY(String(255)), nullable=True)
    place_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    rating = Column(Integer, nullable=False)
    text = Column(String(255), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)

    # Constraints to ensure a user can review a place only once and rating is between 1 to 5
    __table_args__ = (
        UniqueConstraint(
            'place_id', 'user_id', name='unique_place_user_review'
        ),
        CheckConstraint(
            'rating >= 1 AND rating <= 5', name='check_rating_range'
        ),
    )

    def __init__(
        self,
        place_id: str,
        rating: int,
        text: str,
        user_id: str,
        images: list[str] = None,
    ):
        super().__init__()
        self.place_id = place_id
        self.text = text
        self.rating = rating
        self.user_id = user_id
        self.images = images if images else []


class ReviewReactionModel(BaseModel):
    __tablename__ = 'review_reactions'

    # Fields
    review_id = Column(
        UUID(as_uuid=True), ForeignKey('reviews.id'), index=True, nullable=False
    )
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)

    # Constraint to ensure that a user can only react to a review once
    __table_args__ = UniqueConstraint(
        'review_id', 'user_id', name='unique_review_user'
    )

    def __init__(self, review_id: str, user_id: str):
        super().__init__()
        self.review_id = review_id
        self.user_id = user_id


class UserFavoriteModel(BaseModel):
    __tablename__ = 'user_favorites'

    # Fields
    place_id = Column(UUID(as_uuid=True), index=True, nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)

    # Constraint to ensure that a user can only save a place once
    __table_args__ = UniqueConstraint(
        'place_id', 'user_id', name='unique_place_user'
    )

    def __init__(self, place_id: str, user_id: str):
        super().__init__()
        self.place_id = place_id
        self.user_id = user_id
