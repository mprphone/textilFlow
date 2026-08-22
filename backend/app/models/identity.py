from sqlalchemy import Boolean, Column, ForeignKey, Integer, JSON, String

from ..db import Base
from .base import TimestampMixin


class Company(Base, TimestampMixin):
    __tablename__ = "companies"
    id = Column(Integer, primary_key=True)
    code = Column(String(30), unique=True, nullable=False)
    name = Column(String(200), nullable=False)
    tax_id = Column(String(30))
    currency = Column(String(3), default="EUR", nullable=False)
    timezone = Column(String(60), default="Europe/Lisbon", nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    settings = Column(JSON, default=dict, nullable=False)


class User(Base, TimestampMixin):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True, nullable=False)
    full_name = Column(String(200), nullable=False)
    email = Column(String(200))
    password_hash = Column(String(255), nullable=False)
    must_change_password = Column(Boolean, default=False, nullable=False)
    active = Column(Boolean, default=True, nullable=False)


class UserCompany(Base):
    __tablename__ = "user_companies"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    role = Column(String(50), default="operator", nullable=False)
    permissions = Column(JSON, default=list, nullable=False)
