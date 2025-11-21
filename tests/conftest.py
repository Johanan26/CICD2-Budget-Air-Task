import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app, get_db
from app.Usermodels import Base

# Create engine (in-memory)
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={"check_same_thread": False}
)

# Create tables once at module level
Base.metadata.create_all(bind=engine)

# Create a session factory
TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

@pytest.fixture(scope="function")
def db_session():
    """Create a fresh database session for each test with transaction rollback."""
    # Create a connection
    connection = engine.connect()
    # Begin a transaction
    transaction = connection.begin()
    # Create a session bound to the connection
    session = TestingSessionLocal(bind=connection)
    
    yield session
    
    # Rollback the transaction (undoes all changes made during the test)
    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture(scope="function")
def client(db_session):
    """Create a test client with a fresh database session."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass  # Session cleanup handled by db_session fixture
    
    app.dependency_overrides[get_db] = override_get_db
    
    yield TestClient(app)
    
    # Clean up dependency override
    app.dependency_overrides.clear()