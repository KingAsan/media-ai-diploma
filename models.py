from sqlalchemy import Boolean, Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from database import Base
import datetime

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True) # Логин
    hashed_password = Column(String)                   # Зашифрованный пароль
    is_admin = Column(Boolean, default=False)          # Ты - админ?

    # Связь: У пользователя много записей истории
    history = relationship("HistoryEntry", back_populates="owner")

class HistoryEntry(Base):
    __tablename__ = "history"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, index=True)
    user_query = Column(Text)
    ai_response = Column(Text)
    ai_response_json = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Привязка к пользователю
    user_id = Column(Integer, ForeignKey("users.id"))
    owner = relationship("User", back_populates="history")