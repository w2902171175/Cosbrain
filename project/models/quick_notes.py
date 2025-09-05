# project/models/quick_notes.py
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
from project.base import Base
from .mixins import TimestampMixin, OwnerMixin, EmbeddingMixin


class DailyRecord(Base, TimestampMixin, OwnerMixin, EmbeddingMixin):
    __tablename__ = "daily_records"

    id = Column(Integer, primary_key=True, index=True)
    
    # 使用混入类继承的字段：
    # - owner_id (from OwnerMixin)
    # - created_at, updated_at (from TimestampMixin)
    # - combined_text, embedding (from EmbeddingMixin)

    # DailyRecord特有字段
    content = Column(Text, nullable=False, comment="日记内容")
    mood = Column(String, nullable=True, comment="心情")
    tags = Column(String, nullable=True, comment="标签")

    owner = relationship("User", back_populates="daily_records")