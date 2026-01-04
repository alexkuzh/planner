from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.schemas.task_event import TaskEventRead
from app.fsm.task_fsm import TransitionNotAllowed, apply_transition
from app.schemas.transition import TaskTransitionRequest
from app.models.task_event import TaskEvent


from app.core.db import get_db
from app.models.task import Task
from app.schemas.task import TaskCreate, TaskRead, TaskUpdate

router = APIRouter(prefix="/tasks")

@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate, db: Session = Depends(get_db)):
    task = Task(title=payload.title)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task

@router.post("/{task_id}/transition", response_model=TaskRead)
def transition_task(task_id: int, payload: TaskTransitionRequest, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    from_status = task.status.value

    try:
        new_status = apply_transition(task.status, payload.action)
    except TransitionNotAllowed as e:
        raise HTTPException(status_code=409, detail=str(e))

    task.status = new_status
    to_status = task.status.value

    # пока actor = None (позже привяжем к пользователю/супервайзеру)
    event = TaskEvent(
        task_id=task.id,
        action=payload.action,
        from_status=from_status,
        to_status=to_status,
        actor=None,
    )

    db.add_all([task, event])
    db.commit()
    db.refresh(task)
    return task



@router.get("", response_model=list[TaskRead])
def list_tasks(db: Session = Depends(get_db)):
    return db.query(Task).order_by(Task.id.desc()).all()


@router.get("/{task_id}", response_model=TaskRead)
def get_task(task_id: int, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

@router.get("/{task_id}/events", response_model=list[TaskEventRead])
def list_task_events(task_id: int, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return (
        db.query(TaskEvent)
        .filter(TaskEvent.task_id == task_id)
        .order_by(TaskEvent.id.asc())
        .all()
    )


@router.patch("/{task_id}", response_model=TaskRead)
def update_task(task_id: int, payload: TaskUpdate, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if payload.title is not None:
        task.title = payload.title

    # В update_task убери обработку payload.status
    #if payload.status is not None:
    #    task.status = payload.status

    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    db.delete(task)
    db.commit()
    return None
