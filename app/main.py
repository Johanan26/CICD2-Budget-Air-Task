import os
import asyncio
from fastapi import FastAPI, Depends, HTTPException
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
        url = ServiceRoute[task.service]
        response = await client.post(
            f"{url}/{task.route}",
            json=task.params,
        )
        response.raise_for_status()
        return response.json()


async def task_worker(worker_id: int):
    try:
        while True:
            async with async_session() as db:
                async with db.begin():
                    result = await db.execute(
                        select(Task)
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

            except Exception as e:
                async with async_session() as db:
                    async with db.begin():
                        await db.execute(
                            update(Task)
                            .where(Task.id == task.id)
                            .values(status=RequestStatus.FAILED)
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
        params=task.params,
        status=RequestStatus.PENDING,
    )

    db.add(db_task)
    await db.commit()
    await db.refresh(db_task)

    return db_task.task_id
