from sqlalchemy import Column, Integer, String, BigInteger
from .base import Base

class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, index=True, nullable=False)
    first_name = Column(String(50), nullable=True)
    last_name = Column(String(50), nullable=True)
    phone = Column(String(20), nullable=True)
    role = Column(String(20), default="CUSTOMER") # CUSTOMER, ADMIN, STAFF
    status = Column(String(20), default="PENDING_APPROVAL") # PENDING_APPROVAL, APPROVED, BANNED