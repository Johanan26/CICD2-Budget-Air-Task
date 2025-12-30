from fastapi import FastAPI, Depends, HTTPException, status, Response
from typing import List
from sqlalchemy.orm import Session
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from contextlib import asynccontextmanager
from .db import session_local, async_session, engine
from .models import Base, TaskRequest, Task, RequestStatus, ServiceRoute

import asyncio
import httpx

app = FastAPI(title="Payment Processor Microservice")

Base.metadata.create_all(bind=engine)

WORKER_COUNT = 5
worker_tasks: list[asyncio.Task] = []

def get_db():
    db = session_local()
    try:
        yield db
    finally:
        db.close()

def commit_or_rollback(db: Session, error_msg: str):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=error_msg)

@app.post("/create-task")
async def create_task(task: TaskRequest, db: Session = Depends(get_db)):
    db_task = Task(
        service=task.service,
        route=task.route,
        params=task.params
    )

    db.add(db_task)
    db.commit()
    db.refresh(db_task)

    return db_task.task_id


async def task_worker(worker_id):
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
                    await asyncio.sleep(.2)
                    continue

                task.status = RequestStatus.PROCESSING
                await db.flush()

        try:
            await process_task(task)

            async with async_session() as db:
                async with db.begin():
                    await db.execute(
                        update(Task)
                        .where(Task.id == task.id)
                        .values(status=RequestStatus.SUCCESS)
                    )
        except Exception as e:
            async with async_session() as db:
                async with db.begin():
                    await db.execute(
                        update(Task)
                        .where(Task.id == task.id)
                        .values(status=RequestStatus.FAILED)
                    )
            print("Worker: {worker_id} FAILED {task.id}: {e}")


async def process_task(task: Task):
    async with httpx.AsyncClient(timeout=10) as client:
        url = ServiceRoute[task.service]
        response = await client.post(
            f"{url}/{task.route}",
            json=task.params
        )

        response.raise_for_status()

@asynccontextmanager
async def lifespan(app: FastAPI):
    for i in range(WORKER_COUNT):
        task = asyncio.create_task(task_worker(i))
        worker_tasks.append(task)
    
    yield

    for task in worker_tasks:
        task.cancel()

    await asyncio.gather(*worker_tasks, return_exceptions=True)