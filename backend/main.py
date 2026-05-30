from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel
import os

from fastapi.middleware.cors import CORSMiddleware

from . import models
from .database import engine, get_db
from .ml_service import ml_service

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Crop Disease Identification API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Schemas ---

class QuestionCreate(BaseModel):
    title: str
    content: str
    author_id: int

class QuestionResponse(BaseModel):
    id: int
    title: str
    content: str
    author_id: int

    class Config:
        from_attributes = True

class AnswerCreate(BaseModel):
    content: str
    question_id: int
    author_id: int

class AnswerResponse(BaseModel):
    id: int
    content: str
    question_id: int
    author_id: int

    class Config:
        from_attributes = True

class ScanHistoryResponse(BaseModel):
    id: int
    prediction: str
    confidence: str

    class Config:
        from_attributes = True

# --- Endpoints ---

@app.post("/predict", response_model=ScanHistoryResponse)
async def predict_disease(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File provided is not an image.")

    contents = await file.read()

    # Run ML prediction
    result = ml_service.predict(contents)

    # Save scan history to database
    scan_history = models.ScanHistory(
        prediction=result["prediction"],
        confidence=result["confidence"]
    )
    db.add(scan_history)
    db.commit()
    db.refresh(scan_history)

    return scan_history

@app.post("/questions/", response_model=QuestionResponse)
def create_question(question: QuestionCreate, db: Session = Depends(get_db)):
    db_question = models.Question(**question.dict())
    db.add(db_question)
    db.commit()
    db.refresh(db_question)
    return db_question

@app.get("/questions/", response_model=List[QuestionResponse])
def read_questions(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    questions = db.query(models.Question).offset(skip).limit(limit).all()
    return questions

@app.post("/answers/", response_model=AnswerResponse)
def create_answer(answer: AnswerCreate, db: Session = Depends(get_db)):
    db_answer = models.Answer(**answer.dict())
    db.add(db_answer)
    db.commit()
    db.refresh(db_answer)
    return db_answer

@app.get("/questions/{question_id}/answers/", response_model=List[AnswerResponse])
def read_answers(question_id: int, db: Session = Depends(get_db)):
    answers = db.query(models.Answer).filter(models.Answer.question_id == question_id).all()
    return answers

# Initialize default user
@app.on_event("startup")
def startup_event():
    db = engine.connect()
    # Using raw SQL or a session to ensure the user exists
    with Session(engine) as session:
        user = session.query(models.User).filter_by(id=1).first()
        if not user:
            user = models.User(id=1, username="farmer_joe")
            session.add(user)
            session.commit()
