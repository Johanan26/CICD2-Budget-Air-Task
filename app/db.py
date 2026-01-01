import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/task_db"
)

TESTING = os.getenv("TESTING") == "1"

async_engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    poolclass=NullPool if TESTING else None,
)

async_session = async_sessionmaker(
    async_engine,
    expire_on_commit=False,
)