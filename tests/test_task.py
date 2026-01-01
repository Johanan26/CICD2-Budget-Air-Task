import os
import asyncio
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from unittest.mock import MagicMock, AsyncMock, patch
from contextlib import asynccontextmanager

os.environ["TESTING"] = "1"
DB_HOST = os.getenv("DB_HOST", "localhost")
DATABASE_URL = f"postgresql+asyncpg://postgres:postgres@{DB_HOST}:5432/task_test"
os.environ["ASYNC_DATABASE_URL"] = DATABASE_URL

from app.main import app, task_worker, lifespan, WORKER_COUNT
from app.models import Base, RequestStatus

setup_engine = create_async_engine(DATABASE_URL, poolclass=NullPool, echo=False)

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(scope="session", autouse=True)
async def initialize_test_database():
    async with setup_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    
    yield
    
    async with setup_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await setup_engine.dispose()


@pytest_asyncio.fixture
async def clean_tables():
    async with setup_engine.begin() as conn:
        await conn.execute(text("TRUNCATE TABLE tasks RESTART IDENTITY CASCADE"))
    
    yield
    

@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        timeout=10.0
    ) as ac:
        yield ac


async def test_create_task(client: AsyncClient, clean_tables):
    payload = {
        "service": "user",
        "route": "create-user",
        "params": {"name": "Sean", "email": "sean@example.com"},
    }
    
    response = await client.post("/create-task", json=payload)
    assert response.status_code == 200
    
    task_id = response.json()
    assert isinstance(task_id, str)
    
    await asyncio.sleep(0.1)
    async with setup_engine.connect() as conn:
        result = await conn.execute(
            text("SELECT COUNT(*) FROM tasks WHERE task_id = :task_id"),
            {"task_id": task_id},
        )
        count = result.scalar()
        assert count == 1


async def test_get_task_404(client: AsyncClient, clean_tables):
    response = await client.get("/tasks/does-not-exist")
    assert response.status_code == 404
    assert response.json()["detail"] == "Task not found"


async def test_poll_task_returns_success_when_ready(client: AsyncClient, clean_tables):
    response = await client.post(
        "/create-task",
        json={
            "service": "payment",
            "route": "charge",
            "params": {"amount": "12.50", "currency": "EUR"},
        },
    )
    assert response.status_code == 200
    task_id = response.json()
    
    await asyncio.sleep(0.2)
    
    async with setup_engine.begin() as conn:
        await conn.execute(
            text("""
                UPDATE tasks 
                SET status = 'SUCCESS', 
                    result = '{"ok": true, "payment_id": "p1"}'::jsonb
                WHERE task_id = :task_id
            """),
            {"task_id": task_id}
        )
    
    await asyncio.sleep(0.1)
    
    response = await client.get(f"/tasks/{task_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["result"]["payment_id"] == "p1"


async def test_poll_task_returns_failed_when_ready(client: AsyncClient, clean_tables):
    response = await client.post(
        "/create-task",
        json={
            "service": "flight",
            "route": "book",
            "params": {"flight_id": "f1"},
        },
    )
    assert response.status_code == 200
    task_id = response.json()
    
    await asyncio.sleep(0.2)
    
    async with setup_engine.begin() as conn:
        await conn.execute(
            text("UPDATE tasks SET status = 'FAILED' WHERE task_id = :task_id"),
            {"task_id": task_id}
        )
    
    await asyncio.sleep(0.1)
    
    response = await client.get(f"/tasks/{task_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "failed"

async def test_task_worker_processes_pending_task(client: AsyncClient, clean_tables, mocker):
    """Test that task_worker can process a pending task"""
    response = await client.post(
        "/create-task",
        json={
            "service": "payment",
            "route": "charge",
            "params": {"amount": "10.00", "currency": "USD"},
        },
    )
    task_id = response.json()
    
    mock_process = mocker.patch("app.main.process_task", return_value={"success": True})
    mocker.patch("app.main.process_task", new_callable=mocker.AsyncMock, return_value={"success": True})
    
    worker_task = asyncio.create_task(task_worker(0))
    
    await asyncio.sleep(0.5)
    
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass
    
    await asyncio.sleep(0.1)
    async with setup_engine.connect() as conn:
        result = await conn.execute(
            text("SELECT status FROM tasks WHERE task_id = :task_id"),
            {"task_id": task_id}
        )
        status = result.scalar()
        assert status in ["PROCESSING", "SUCCESS"]

async def test_lifespan_testing_mode_integration():
    from app.main import TESTING, worker_tasks
    
    assert TESTING is True
    
    initial_worker_count = len(worker_tasks)
    
    assert initial_worker_count == 0, "Workers should not start in testing mode"


async def test_lifespan_production_simulation():
    import app.main as main_module
    
    original_testing = main_module.TESTING
    original_workers = main_module.worker_tasks.copy()
    
    try:
        main_module.TESTING = False
        main_module.worker_tasks.clear()
        
        with patch("app.main.async_engine") as mock_engine:
            mock_conn = AsyncMock()
            mock_context = AsyncMock()
            mock_context.__aenter__.return_value = mock_conn
            mock_context.__aexit__.return_value = AsyncMock()
            mock_engine.begin.return_value = mock_context
            mock_engine.dispose = AsyncMock()
            
            with patch("app.main.task_worker") as mock_worker:
                fake_app = MagicMock()
                
                async with lifespan(fake_app):
                    assert len(main_module.worker_tasks) == WORKER_COUNT
                    mock_conn.run_sync.assert_called()
                
                mock_engine.dispose.assert_called_once()
    
    finally:
        main_module.TESTING = original_testing
        main_module.worker_tasks.clear()
        main_module.worker_tasks.extend(original_workers)