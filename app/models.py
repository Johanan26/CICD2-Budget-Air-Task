from datetime import datetime
from decimal import Decimal
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Enum as SqlEnum, DateTime
from pydantic import BaseModel
from typing import Any
from enum import Enum
from dotenv import load_dotenv
import uuid
import os

load_dotenv()

class Base(DeclarativeBase):
 pass

class ServiceType(str, Enum):
   USER = "user"
   PAYMENT = "payment"
   FLIGHT = "flight"

class ServiceRoute(str, Enum):
   USER = os.getenv("USER_URL")
   PAYMENT = os.getenv("PAYMENT_URL")
   FLIGHT = os.getenv("FLIGHT_URL")

class RequestStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"

class TaskRequest(BaseModel):
   service: ServiceType
   route: str
   params: dict[str, Any]

class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str] = mapped_column(String, nullable=False, default=lambda: str(uuid.uuid4()))
    service: Mapped[ServiceType] = mapped_column(SqlEnum(ServiceType), nullable=False) 
    status: Mapped[RequestStatus] = mapped_column(SqlEnum(RequestStatus), nullable=False)
    route: Mapped[str] = mapped_column(String, nullable=False)
    params: Mapped[dict] = mapped_column(JSONB, nullable=False)

    create_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    update_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)