import os
from datetime import datetime
from typing import Optional, List

import sqlalchemy as sa
from flask import url_for
from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import DateTime, ForeignKey, Integer, MetaData, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from werkzeug.security import check_password_hash, generate_password_hash


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention={
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    })


db = SQLAlchemy(model_class=Base)


book_genres = sa.Table(
    "book_genres",
    Base.metadata,
    sa.Column("book_id", sa.ForeignKey("books.id", ondelete="CASCADE"), primary_key=True),
    sa.Column("genre_id", sa.ForeignKey("genres.id", ondelete="CASCADE"), primary_key=True),
)


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    users: Mapped[List["User"]] = relationship(back_populates="role")

    def __repr__(self):
        return f"<Role {self.name}>"


class User(Base, UserMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    login: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    middle_name: Mapped[Optional[str]] = mapped_column(String(100))
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    role: Mapped["Role"] = relationship(back_populates="users", lazy=False)
    reviews: Mapped[List["Review"]] = relationship(back_populates="user", cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def full_name(self):
        parts = [self.last_name, self.first_name, self.middle_name or ""]
        return " ".join(part for part in parts if part).strip()

    def has_role(self, *roles):
        return self.role and self.role.name in roles

    def __repr__(self):
        return f"<User {self.login}>"


class Genre(Base):
    __tablename__ = "genres"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    books: Mapped[List["Book"]] = relationship(
        secondary=book_genres,
        back_populates="genres",
    )

    def __repr__(self):
        return f"<Genre {self.name}>"


class Book(Base):
    __tablename__ = "books"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    short_desc: Mapped[str] = mapped_column(Text, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    publisher: Mapped[str] = mapped_column(String(200), nullable=False)
    author: Mapped[str] = mapped_column(String(200), nullable=False)
    pages: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    genres: Mapped[List["Genre"]] = relationship(
        secondary=book_genres,
        back_populates="books",
        lazy=False,
    )

    cover: Mapped[Optional["Cover"]] = relationship(
        back_populates="book",
        cascade="all, delete-orphan",
        uselist=False,
    )

    reviews: Mapped[List["Review"]] = relationship(
        back_populates="book",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self):
        return f"<Book {self.title}>"


class Cover(Base):
    __tablename__ = "covers"

    id: Mapped[int] = mapped_column(primary_key=True)
    file_name: Mapped[str] = mapped_column(String(200), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    md5_hash: Mapped[str] = mapped_column(String(100), nullable=False)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), nullable=False)

    book: Mapped["Book"] = relationship(back_populates="cover")

    @property
    def storage_filename(self):
        _, ext = os.path.splitext(self.file_name)
        return self.md5_hash + ext

    @property
    def url(self):
        return url_for("cover", cover_id=self.id)

    def __repr__(self):
        return f"<Cover {self.file_name}>"


class ReviewStatus(Base):
    __tablename__ = "review_statuses"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    reviews: Mapped[List["Review"]] = relationship(back_populates="status")

    def __repr__(self):
        return f"<ReviewStatus {self.name}>"


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    status_id: Mapped[int] = mapped_column(ForeignKey("review_statuses.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    book: Mapped["Book"] = relationship(back_populates="reviews")
    user: Mapped["User"] = relationship(back_populates="reviews", lazy=False)
    status: Mapped["ReviewStatus"] = relationship(back_populates="reviews", lazy=False)

    __table_args__ = (
        sa.UniqueConstraint("book_id", "user_id", name="uq_reviews_book_user"),
    )

    def __repr__(self):
        return f"<Review {self.id} rating={self.rating}>"
