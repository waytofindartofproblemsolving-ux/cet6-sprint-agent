from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


Skill = Literal["diagnostic", "reading", "listening", "writing", "translation", "vocabulary"]


class Question(BaseModel):
    id: str
    prompt: str
    choices: list[str] = Field(default_factory=list)
    answer: str | None = None


class Drill(BaseModel):
    id: int | None = None
    skill: Skill
    title: str
    minutes: int = Field(ge=1, le=60)
    instructions: str
    questions: list[Question]
    rubric: str


class Correction(BaseModel):
    original: str
    corrected: str
    explanation: str


class Feedback(BaseModel):
    score: int = Field(ge=0, le=100)
    summary: str
    corrections: list[Correction]
    mistake_tags: list[str]
    next_action: str


class ReviewItem(BaseModel):
    id: int | None = None
    mistake_type: str
    prompt: str
    user_answer: str
    corrected_answer: str
    due_date: date


class GenerateDrillRequest(BaseModel):
    skill: Skill
    minutes: int = Field(default=10, ge=1, le=60)
    material_id: int | None = None


class GradeAttemptRequest(BaseModel):
    drill_id: int
    answers: dict[str, str]


class MaterialRequest(BaseModel):
    title: str
    content: str
