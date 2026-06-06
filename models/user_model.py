from sqlalchemy import Column, Integer, String, DateTime, Index
from sqlalchemy.orm import declarative_base
from datetime import datetime

# SQLAlchemy Base configuration
Base = declarative_base()

class UserModel(Base):
    """
    SQLAlchemy ORM Model representing the physical database table.
    """
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, autoincrement=True, comment="Primary Key")
    username = Column(String(50), nullable=False, comment="User login name")
    email = Column(String(100), nullable=False, unique=True, comment="User email")
    age = Column(Integer, nullable=False, default=18)
    status = Column(Integer, nullable=False, default=1, comment="0:Inactive, 1:Active")
    
    gmt_create = Column(DateTime, default=datetime.utcnow, comment="Creation time")
    gmt_modified = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="Last modification time")

    # Indexes
    __table_args__ = (
        Index('idx_status_age', 'status', 'age'), # Example composed index
    )
