from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class Activity(Base):
    """Modèle pour les activités de guilde"""

    __tablename__ = "activities"

    id = Column(Integer, primary_key=True)
    message_id = Column(String, unique=True, nullable=False)
    thread_id = Column(String, unique=True, nullable=False)
    channel_id = Column(String, nullable=False)
    guild_id = Column(String, nullable=False)

    title = Column(String, nullable=False)
    leader = Column(String, nullable=True)
    event_date = Column(DateTime, nullable=False)
    ping_role_id = Column(String, nullable=True)

    roles_config = Column(
        JSON, nullable=False
    )  # Structure: {role_name: {weapon: slots}}
    reminders = Column(JSON, nullable=False)  # Liste des minutes avant event
    last_reminder_sent = Column(
        Integer, nullable=True
    )  # Dernier rappel envoyé (en minutes)

    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)

    registrations = relationship(
        "Registration", back_populates="activity", cascade="all, delete-orphan"
    )


class Registration(Base):
    """Modèle pour les inscriptions aux activités"""

    __tablename__ = "registrations"

    id = Column(Integer, primary_key=True)
    activity_id = Column(Integer, ForeignKey("activities.id"), nullable=False)
    user_id = Column(String, nullable=False)
    role_name = Column(String, nullable=False)
    weapon = Column(String, nullable=False)
    slot_number = Column(Integer, nullable=False)

    registered_at = Column(DateTime, default=datetime.utcnow)

    activity = relationship("Activity", back_populates="registrations")
