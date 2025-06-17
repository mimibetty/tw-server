import uuid
from datetime import datetime, date

from flask_sqlalchemy import SQLAlchemy
from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, ForeignKey, UniqueConstraint
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    backref,
)
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
    birthday: Mapped[date] = mapped_column(nullable=True)
    phone_number: Mapped[str] = mapped_column(nullable=True)

    def __setattr__(self, key, value):
        if key == 'password' and value is not None:
            value = generate_password_hash(value)
        super().__setattr__(key, value)


class UserFavourite(BaseModel):
    __tablename__ = 'user_favourites'

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey('users.id', ondelete='CASCADE'), nullable=False
    )
    place_id: Mapped[str] = mapped_column(nullable=False)

    # Relationships
    user: Mapped[User] = relationship(
        'User',
        backref=backref('user_favourites', cascade='all, delete-orphan'),
        foreign_keys=[user_id],
    )

    def __init__(self, user_id: uuid.UUID, place_id: str) -> None:
        super().__init__()
        self.user_id = user_id
        self.place_id = place_id


class UserReview(BaseModel):
    __tablename__ = 'user_reviews'

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey('users.id', ondelete='CASCADE'), nullable=False
    )
    place_id: Mapped[str] = mapped_column(nullable=False)
    review: Mapped[str] = mapped_column(nullable=False)
    rating: Mapped[int] = mapped_column(nullable=False, default=1)

    # Relationships
    user: Mapped[User] = relationship(
        'User',
        backref=backref('user_reviews', cascade='all, delete-orphan'),
        foreign_keys=[user_id],
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
        ForeignKey('users.id', ondelete='CASCADE'), nullable=False
    )
    name: Mapped[str] = mapped_column(nullable=False)
    is_optimized: Mapped[bool] = mapped_column(default=False)
    trip_status: Mapped[bool] = mapped_column(
        default=False
    )  # False = "Upcoming", True = "Done"

    # Relationships
    user: Mapped[User] = relationship(
        'User',
        backref=backref('user_trips', cascade='all, delete-orphan'),
        foreign_keys=[user_id],
    )


class Trip(BaseModel):
    __tablename__ = 'trips'

    trip_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey('user_trips.id', ondelete='CASCADE'), nullable=False
    )
    place_id: Mapped[str] = mapped_column(nullable=False)
    order: Mapped[int] = mapped_column(nullable=False, default=0)

    # Relationships
    user_trip: Mapped[UserTrip] = relationship(
        'UserTrip',
        backref=backref('trips', cascade='all, delete-orphan'),
        foreign_keys=[trip_id],
    )


class VectorItem(BaseModel):
    __tablename__ = 'vector_items'

    place_id: Mapped[str] = mapped_column(primary_key=True)
    embedding = mapped_column(Vector)

    def __init__(self, place_id: str, embedding):
        super().__init__()
        self.place_id = place_id
        self.embedding = embedding
