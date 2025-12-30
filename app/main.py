from fastapi import FastAPI, Depends, HTTPException, status, Response
from typing import List
from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from .db import SessionLocal, engine
from .models import Base, TaskRequest, Task

app = FastAPI(title="Payment Processor Microservice")

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
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