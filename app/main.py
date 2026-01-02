import os
import asyncio
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from contextlib import asynccontextmanager
import httpx

from .db import async_session, async_engine
from .models import (
    Base,
    TaskRequest,
    Task,
    RequestStatus,
    ServiceRoute,
    TaskStatusResponse,
    HttpMethod,
)

TESTING = os.getenv("TESTING") == "1"

WORKER_COUNT = 5
worker_tasks: list[asyncio.Task] = []


async def get_db() -> AsyncSession:
    async with async_session() as db:
        yield db


async def commit_or_rollback(db: AsyncSession, error_msg: str):
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail=error_msg)

async def process_task(task: Task):
    async with httpx.AsyncClient(timeout=10) as client:
        url = ServiceRoute[task.service.name].value
        full_url = f"{url}/{task.route}"
        

        if task.method in (HttpMethod.GET, HttpMethod.HEAD, HttpMethod.OPTIONS):
            response = await client.request(
                method=task.method.value,
                url=full_url,
                params=task.params,
            )
        else:
            response = await client.request(
                method=task.method.value,
                url=full_url,
                json=task.params,
            )
        
        response.raise_for_status()
        
        # HEAD and OPTIONS might not have JSON response
        if task.method == HttpMethod.HEAD:
            return {"status_code": response.status_code, "headers": dict(response.headers)}
        elif task.method == HttpMethod.OPTIONS:
            return {"status_code": response.status_code, "headers": dict(response.headers), "text": response.text}
        
        # Try to parse JSON, fallback to text if not JSON
        try:
            return response.json()
        except Exception:
            return {"status_code": response.status_code, "text": response.text}


async def task_worker(worker_id: int):
    try:
        while True:
            async with async_session() as db:
                async with db.begin():
                    result = await db.execute(
                        select(Task)
                        .filter(Task.status == RequestStatus.PENDING)
                        .order_by(Task.create_at)
                        .with_for_update(skip_locked=True)
                        .limit(1)
                    )
                    task = result.scalars().first()

                    if task is None:
                        await asyncio.sleep(0.3)
                        continue

                    task.status = RequestStatus.PROCESSING

            try:
                task_result = await process_task(task)

                async with async_session() as db:
                    async with db.begin():
                        await db.execute(
                            update(Task)
                            .where(Task.id == task.id)
                            .values(
                                status=RequestStatus.SUCCESS,
                                result=task_result,
                            )
                        )

            except httpx.HTTPStatusError as e:
                error_detail = None
                try:
                    error_detail = e.response.json()
                except Exception:
                    error_detail = {"detail": str(e)}
                
                async with async_session() as db:
                    async with db.begin():
                        await db.execute(
                            update(Task)
                            .where(Task.id == task.id)
                            .values(
                                status=RequestStatus.FAILED,
                                result=error_detail
                            )
                        )
                print(f"Worker {worker_id} FAILED {task.id}: {e}")
            except Exception as e:
                async with async_session() as db:
                    async with db.begin():
                        await db.execute(
                            update(Task)
                            .where(Task.id == task.id)
                            .values(
                                status=RequestStatus.FAILED,
                                result={"detail": str(e)}
                            )
                        )
                print(f"Worker {worker_id} FAILED {task.id}: {e}")

    except asyncio.CancelledError:
        print(f"Worker {worker_id} shutting down")
        raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not TESTING:
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        for i in range(WORKER_COUNT):
            worker_tasks.append(asyncio.create_task(task_worker(i)))

    yield

    for task in worker_tasks:
        task.cancel()

    await asyncio.gather(*worker_tasks, return_exceptions=True)
    
    if not TESTING:
        await async_engine.dispose()

app = FastAPI(
    title="Payment Processor Microservice",
    lifespan=lifespan,
)

# CORS middleware - must be added before routes
# Order matters: middleware is applied in reverse order
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
    allow_headers=["*"],
    expose_headers=["*"],
)


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "ok"}

@app.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def poll_task(task_id: str):
    async with async_session() as db:
        result = await db.execute(
            select(Task).where(Task.task_id == task_id)
        )
        task = result.scalars().first()

        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")

        return TaskStatusResponse(
            task_id=task.task_id,
            status=task.status,
            result=task.result,
        )
        
@app.post("/create-task")
async def create_task(
    task: TaskRequest,
    db: AsyncSession = Depends(get_db),
):
    db_task = Task(
        service=task.service,
        route=task.route,
        method=task.method,
        params=task.params,
        status=RequestStatus.PENDING,
    )

    db.add(db_task)
    await db.commit()
    await db.refresh(db_task)

    return db_task.task_id
