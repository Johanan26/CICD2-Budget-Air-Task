from datetime import datetime
from decimal import Decimal
import uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Enum as SqlEnum, DateTime
from enum import Enum

class Base(DeclarativeBase):
 pass

class ServiceType(str, Enum):
   USER = "user"
   PAYMENT = "payment"
   FLIGHT = "flight"

class RequestStatus(str, Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"

class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str] = mapped_column(String, nullable=False, default=lambda: str(uuid.uuid4()))
    service: Mapped[ServiceType] = mapped_column(SqlEnum(ServiceType), nullable=False) 
    route: Mapped[str] = mapped_column(String, nullable=False)
    params: Mapped[dict] = mapped_column(JSONB, nullable=False)

    create_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    update_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)