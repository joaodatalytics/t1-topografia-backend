"""
WeekPlanner API — FastAPI + SQLAlchemy (Com Avisos e Cloud Sync)
"""
from __future__ import annotations
import os
from datetime import datetime
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import (
    CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String, Text, Boolean, create_engine
)
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker

# ─────────────────────────────────────────────
# DATABASE CONFIG
# ─────────────────────────────────────────────
raw_db_url = os.getenv("DATABASE_URL", "sqlite:///./weekplanner.db")
if raw_db_url.startswith("postgres://"):
    raw_db_url = raw_db_url.replace("postgres://", "postgresql://", 1)

DATABASE_URL = raw_db_url

if "sqlite" in DATABASE_URL:
    engine = create_engine(DATABASE_URL, echo=False, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL, echo=False)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase): pass

# ─────────────────────────────────────────────
# MODELS
# ─────────────────────────────────────────────
class UserModel(Base):
    __tablename__ = "users"
    id        = Column(Integer, primary_key=True, index=True)
    nome      = Column(String(100), nullable=False)
    email     = Column(String(150), nullable=False, unique=True)
    cargo     = Column(String(100), default="Membro") # NOVO CAMPO
    avatar    = Column(String(10), default=None)
    cor       = Column(String(7), default="#F37021") 
    criado_em = Column(DateTime, default=datetime.utcnow)

    tasks = relationship("TaskModel", back_populates="user", cascade="all, delete")

class SubTaskModel(Base):
    __tablename__ = "subtasks"
    id        = Column(Integer, primary_key=True, index=True)
    titulo    = Column(String(255), nullable=False)
    concluida = Column(Boolean, default=False)
    task_id   = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    
    task = relationship("TaskModel", back_populates="subtasks")

class TaskModel(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint("dia_da_semana BETWEEN 1 AND 7",   name="chk_dia"),
        CheckConstraint("turno IN ('manha','tarde','noite')", name="chk_turno"),
        CheckConstraint("status IN ('a_fazer','em_andamento','concluido')", name="chk_status"),
        Index("idx_tasks_dia_turno", "dia_da_semana", "turno"),
        Index("idx_tasks_user",      "user_id"),
    )
    id            = Column(Integer, primary_key=True, index=True)
    titulo        = Column(String(255), nullable=False)
    descricao     = Column(Text, default=None)
    dia_da_semana = Column(Integer, nullable=False)
    turno         = Column(String(10), nullable=False, default="manha")
    status        = Column(String(15), nullable=False, default="a_fazer")
    data_exata    = Column(String(10), nullable=True) 
    user_id       = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    criado_em     = Column(DateTime, default=datetime.utcnow)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("UserModel", back_populates="tasks")
    subtasks = relationship("SubTaskModel", back_populates="task", cascade="all, delete-orphan")

class AvisoModel(Base):
    __tablename__ = "avisos"
    id         = Column(Integer, primary_key=True, index=True)
    category   = Column(String(50), nullable=False)
    type       = Column(String(50), nullable=True)
    text       = Column(Text, nullable=False)
    dataLimite = Column(String(50), nullable=True)
    criado_em  = Column(DateTime, default=datetime.utcnow)

# ─────────────────────────────────────────────
# SCHEMAS (Pydantic)
# ─────────────────────────────────────────────
class UserCreate(BaseModel):
    nome:   str
    email:  str
    cargo:  Optional[str] = "Membro"
    avatar: Optional[str] = None
    cor:    Optional[str] = "#F37021"

class UserOut(UserCreate):
    id:        int
    criado_em: datetime
    class Config: from_attributes = True

class SubTaskCreate(BaseModel):
    titulo: str

class SubTaskOut(BaseModel):
    id: int
    titulo: str
    concluida: bool
    class Config: from_attributes = True

class TaskCreate(BaseModel):
    titulo:        str
    descricao:     Optional[str]    = None
    dia_da_semana: int
    turno:         str              = "manha"
    status:        str              = "a_fazer"
    data_exata:    Optional[str]    = None  
    user_id:       int

class TaskUpdate(BaseModel):
    titulo:        Optional[str]  = None
    descricao:     Optional[str]  = None
    dia_da_semana: Optional[int]  = None
    turno:         Optional[str]  = None
    status:        Optional[str]  = None
    data_exata:    Optional[str]  = None  
    user_id:       Optional[int]  = None

class TaskOut(TaskCreate):
    id:            int
    criado_em:     datetime
    atualizado_em: datetime
    user:          UserOut
    subtasks:      List[SubTaskOut] = []
    class Config: from_attributes = True

class AvisoCreate(BaseModel):
    category:   str
    type:       Optional[str] = None
    text:       str
    dataLimite: Optional[str] = None

class AvisoOut(AvisoCreate):
    id: int
    criado_em: datetime
    class Config: from_attributes = True

# ─────────────────────────────────────────────
# APP & ROUTES
# ─────────────────────────────────────────────
app = FastAPI(title="WeekPlanner API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

@app.on_event("startup")
def startup_event(): Base.metadata.create_all(bind=engine)

@app.get("/users", response_model=List[UserOut])
def list_users(db: Session = Depends(get_db)): return db.query(UserModel).order_by(UserModel.nome).all()

@app.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, db: Session = Depends(get_db)):
    user = UserModel(**payload.model_dump())
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

@app.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if user:
        db.delete(user)
        db.commit()

@app.get("/tasks", response_model=List[TaskOut])
def list_tasks(db: Session = Depends(get_db)):
    return db.query(TaskModel).order_by(TaskModel.dia_da_semana, TaskModel.turno, TaskModel.id).all()

@app.post("/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate, db: Session = Depends(get_db)):
    task = TaskModel(**payload.model_dump())
    db.add(task)
    db.commit()
    db.refresh(task)
    return task

@app.put("/tasks/{task_id}", response_model=TaskOut)
def update_task(task_id: int, payload: TaskUpdate, db: Session = Depends(get_db)):
    task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items(): setattr(task, field, value)
    task.atualizado_em = datetime.utcnow()
    db.commit()
    db.refresh(task)
    return task

@app.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
    if task:
        db.delete(task)
        db.commit()

@app.post("/tasks/{task_id}/subtasks", response_model=SubTaskOut)
def add_subtask(task_id: int, payload: SubTaskCreate, db: Session = Depends(get_db)):
    st = SubTaskModel(titulo=payload.titulo, task_id=task_id)
    db.add(st)
    db.commit()
    db.refresh(st)
    return st

@app.put("/subtasks/{subtask_id}")
def toggle_subtask(subtask_id: int, concluida: bool, db: Session = Depends(get_db)):
    st = db.query(SubTaskModel).filter(SubTaskModel.id == subtask_id).first()
    st.concluida = concluida
    db.commit()
    return {"status": "ok"}

@app.get("/avisos", response_model=List[AvisoOut])
def list_avisos(db: Session = Depends(get_db)):
    return db.query(AvisoModel).order_by(AvisoModel.id.desc()).all()

@app.post("/avisos", response_model=AvisoOut, status_code=status.HTTP_201_CREATED)
def create_aviso(payload: AvisoCreate, db: Session = Depends(get_db)):
    aviso = AvisoModel(**payload.model_dump())
    db.add(aviso)
    db.commit()
    db.refresh(aviso)
    return aviso

@app.delete("/avisos/{aviso_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_aviso(aviso_id: int, db: Session = Depends(get_db)):
    aviso = db.query(AvisoModel).filter(AvisoModel.id == aviso_id).first()
    if aviso:
        db.delete(aviso)
        db.commit()