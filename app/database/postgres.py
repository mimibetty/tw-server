import uuid

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import UUID, Boolean, Column, DateTime, String, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase
from werkzeug.security import check_password_hash, generate_password_hash


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)


class BaseModel(db.Model):
    """Base model for all models."""

    __abstract__ = True
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
        try:
            db.session.add(self)
            db.session.commit()
        except IntegrityError as e:
            db.session.rollback()
            raise e

    def update(self):
        try:
            db.session.commit()
        except IntegrityError as e:
            db.session.rollback()
            raise e

    def delete(self):
        try:
            db.session.delete(self)
            db.session.commit()
        except IntegrityError as e:
            db.session.rollback()
            raise e

    def __repr__(self):
        return f'<{self.__class__.__name__} {self.id}>'


class UserModel(BaseModel):
    __tablename__ = 'users'

    email = Column(String(255), unique=True, nullable=False)
    password = Column(String(255), nullable=False)
    name = Column(String(255), nullable=False)
    is_admin = Column(Boolean, nullable=False, default=False)
    is_verified = Column(Boolean, nullable=False, default=False)

    def __init__(
        self, email: str, password: str, name: str, is_admin: bool = False
    ):
        super().__init__()
        self.email = email
        self.password = generate_password_hash(password)
        self.name = name
        self.is_admin = is_admin

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password, password)
