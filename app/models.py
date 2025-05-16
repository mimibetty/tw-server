import uuid
from datetime import datetime

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import CheckConstraint, ForeignKey, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from werkzeug.security import generate_password_hash

from app.environments import TIMEZONE


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)


class BaseModel(db.Model):
    __abstract__ = True

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, default=lambda: datetime.now(TIMEZONE)
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=lambda: datetime.now(TIMEZONE),
        onupdate=lambda: datetime.now(TIMEZONE),
    )


class User(BaseModel):
    __tablename__ = 'users'

    avatar: Mapped[str] = mapped_column(nullable=True)
    email: Mapped[str] = mapped_column(unique=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(default=False)
    is_verified: Mapped[bool] = mapped_column(default=False)
    full_name: Mapped[str] = mapped_column(nullable=False)
    password: Mapped[str] = mapped_column(nullable=False)

    def __setattr__(self, key, value):
        if key == 'password' and value is not None:
            value = generate_password_hash(value)
        super().__setattr__(key, value)


class UserFavourite(BaseModel):
    __tablename__ = 'user_favourites'

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey('users.id'), nullable=False
    )
    place_id: Mapped[str] = mapped_column(nullable=False)

    # Relationships
    user: Mapped[User] = relationship(
        'User', backref='user_favourites', foreign_keys=[user_id]
    )


class UserReview(BaseModel):
    __tablename__ = 'user_reviews'

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey('users.id'), nullable=False
    )
    place_id: Mapped[str] = mapped_column(nullable=False)
    review: Mapped[str] = mapped_column(nullable=False)
    rating: Mapped[int] = mapped_column(nullable=False, default=1)

    # Relationships
    user: Mapped[User] = relationship(
        'User', backref='user_reviews', foreign_keys=[user_id]
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint('user_id', 'place_id', name='unique_user_review'),
        CheckConstraint(
            'rating >= 1 AND rating <= 5', name='check_rating_range'
        ),
    )


class UserTrip(BaseModel):
    __tablename__ = 'user_trips'

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey('users.id'), nullable=False
    )
    name: Mapped[str] = mapped_column(nullable=False)

    # Relationships
    user: Mapped[User] = relationship(
        'User', backref='user_trips', foreign_keys=[user_id]
    )


class Trip(BaseModel):
    __tablename__ = 'trips'

    trip_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey('user_trips.id'), nullable=False
    )
    place_id: Mapped[str] = mapped_column(nullable=False)
    order: Mapped[int] = mapped_column(nullable=False, default=0)

    # Relationships
    user_trip: Mapped[UserTrip] = relationship(
        'UserTrip', backref='trips', foreign_keys=[trip_id]
    )
