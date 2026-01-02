from datetime import datetime
from decimal import Decimal
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Enum as SqlEnum, DateTime
from pydantic import BaseModel
from typing import Any, Optional
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
   USER = os.getenv("USERS_URL")
   PAYMENT = os.getenv("PAYMENTS_URL")
   FLIGHT = os.getenv("FLIGHTS_URL")

class RequestStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"

class HttpMethod(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"

class TaskRequest(BaseModel):
   service: ServiceType
   route: str
   params: dict[str, Any]
   method: HttpMethod = HttpMethod.POST  # Default to POST for backward compatibility

class TaskStatusResponse(BaseModel):
    task_id: str
    status: RequestStatus
    result: Optional[dict | list | Any] = None  # Allow dict, list, or any JSON-serializable type

class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str] = mapped_column(String, nullable=False, default=lambda: str(uuid.uuid4()))
    service: Mapped[ServiceType] = mapped_column(SqlEnum(ServiceType), nullable=False) 
    status: Mapped[RequestStatus] = mapped_column(SqlEnum(RequestStatus), nullable=False)
    route: Mapped[str] = mapped_column(String, nullable=False)
    method: Mapped[HttpMethod] = mapped_column(SqlEnum(HttpMethod), nullable=False, default=HttpMethod.POST)
    params: Mapped[dict] = mapped_column(JSONB, nullable=False)

    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    create_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    update_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)