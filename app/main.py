from __future__ import annotations

from datetime import date
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import db
from app.ai.deepseek_client import DeepSeekStudyClient
from app.ai.fake import FakeAIClient
from app.ai.openai_client import AIServiceError, OpenAIStudyClient
from app.config import ConfigurationError, get_settings
from app.schemas import (
    ExamPaperImportRequest,
    GenerateDrillRequest,
    GradeAttemptRequest,
    LocalFolderImportRequest,
    MaterialRequest,
)
from app.services.local_paper_import import import_local_folder
from app.services.paper_import import split_exam_paper
from app.services.review import build_review_items


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
RECENT_EXAM_WINDOW_YEARS = 15


class MissingAIClient:
    def __init__(self, message: str):
        self.message = message

    def generate_drill(self, *_args: Any, **_kwargs: Any) -> Any:
        raise ConfigurationError(self.message)

    def grade_attempt(self, *_args: Any, **_kwargs: Any) -> Any:
        raise ConfigurationError(self.message)


def create_app(ai_client: Any | None = None, db_path: str | Path | None = None) -> FastAPI:
    application = FastAPI(title="CET-6 Sprint Agent")
    application.mount(
        "/static",
        StaticFiles(directory=BASE_DIR / "static"),
        name="static",
    )
    templates = Jinja2Templates(directory=BASE_DIR / "templates")

    if ai_client is None:
        ai_client = _default_ai_client()

    def connection():
        return db.connect(db_path)

    @application.get("/", response_class=HTMLResponse)
    def dashboard(request: Request):
        with connection() as conn:
            counts = db.dashboard_counts(conn)
        return templates.TemplateResponse(
            request,
            "dashboard.html",
            {
                "counts": counts,
                "ai_ready": not isinstance(ai_client, MissingAIClient),
            },
        )

    @application.get("/drill", response_class=HTMLResponse)
    def drill_page(request: Request):
        return templates.TemplateResponse(request, "drill.html")

    @application.get("/review", response_class=HTMLResponse)
    def review_page(request: Request):
        return templates.TemplateResponse(request, "review.html")

    @application.get("/materials", response_class=HTMLResponse)
    def materials_page(request: Request):
        return templates.TemplateResponse(request, "materials.html")

    @application.post("/api/diagnostic/start")
    def start_diagnostic():
        return _generate_drill(
            GenerateDrillRequest(skill="diagnostic", minutes=15),
            connection,
            ai_client,
        )

    @application.post("/api/drills/generate")
    def generate_drill(payload: GenerateDrillRequest):
        return _generate_drill(payload, connection, ai_client)

    @application.post("/api/attempts/grade")
    def grade_attempt(payload: GradeAttemptRequest):
        with connection() as conn:
            drill = db.get_drill(conn, payload.drill_id)
            if drill is None:
                raise HTTPException(status_code=404, detail="Drill not found.")
            try:
                feedback = ai_client.grade_attempt(drill, payload.answers)
            except ConfigurationError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            except AIServiceError as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from exc
            db.save_attempt(conn, payload.drill_id, payload.answers, feedback)
            review_items = build_review_items(feedback, today=date.today())
            db.save_review_items(conn, review_items)
        return feedback

    @application.get("/api/review/due")
    def due_review():
        with connection() as conn:
            return db.list_due_review_items(conn, today=date.today())

    @application.post("/api/materials")
    def save_material(payload: MaterialRequest):
        if not payload.title.strip() or not payload.content.strip():
            raise HTTPException(status_code=400, detail="Title and content are required.")
        if not _is_recent_real_exam_year(payload.exam_year):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Material exam_year must be from the past 15 years "
                    f"({_min_recent_exam_year()}-{date.today().year})."
                ),
            )
        with connection() as conn:
            material_id = db.save_material(
                conn,
                payload.title,
                payload.content,
                payload.exam_year,
                payload.skill,
            )
        return {"id": material_id}

    @application.get("/api/materials")
    def list_materials(skill: str | None = None):
        with connection() as conn:
            return db.list_materials(conn, skill=skill)

    @application.post("/api/papers/import")
    def import_exam_paper(payload: ExamPaperImportRequest):
        if not payload.title.strip() or not payload.source_text.strip():
            raise HTTPException(status_code=400, detail="Title and source_text are required.")
        if not _is_recent_real_exam_year(payload.exam_year):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Paper exam_year must be from the past 15 years "
                    f"({_min_recent_exam_year()}-{date.today().year})."
                ),
            )
        sections = split_exam_paper(payload.source_text)
        if not sections:
            raise HTTPException(
                status_code=400,
                detail="No supported question-type sections were found.",
            )

        saved = []
        with connection() as conn:
            for section in sections:
                material_id = db.save_material(
                    conn,
                    f"{payload.title} - {section.heading}",
                    section.content,
                    payload.exam_year,
                    section.skill,
                )
                saved.append(
                    {
                        "id": material_id,
                        "title": f"{payload.title} - {section.heading}",
                        "skill": section.skill,
                        "exam_year": payload.exam_year,
                    }
                )
        return {"imported_count": len(saved), "materials": saved}

    @application.post("/api/papers/import-local-folder")
    def import_local_exam_folder(payload: LocalFolderImportRequest):
        root_path = Path(payload.root_path).resolve() if payload.root_path else PROJECT_ROOT
        try:
            with connection() as conn:
                return import_local_folder(root_path, conn)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return application


def _default_ai_client() -> Any:
    if os.getenv("CET6_USE_FAKE_AI") == "1":
        return FakeAIClient()
    try:
        settings = get_settings()
        if settings.ai_provider == "deepseek":
            return DeepSeekStudyClient(settings)
        return OpenAIStudyClient(settings)
    except ConfigurationError as exc:
        return MissingAIClient(str(exc))


def _generate_drill(
    payload: GenerateDrillRequest,
    connection_factory: Any,
    ai_client: Any,
) -> Any:
    with connection_factory() as conn:
        if payload.material_id is None:
            raise HTTPException(
                status_code=400,
                detail="Select a recent real CET-6 exam material first.",
            )
        material = db.get_material(conn, payload.material_id)
        if material is None:
            raise HTTPException(status_code=404, detail="Material not found.")
        if not _is_recent_real_exam_year(material["exam_year"]):
            raise HTTPException(
                status_code=400,
                detail="Material must be from a recent real CET-6 exam.",
            )
        if payload.skill != "diagnostic" and material["skill"] != payload.skill:
            raise HTTPException(
                status_code=400,
                detail="Selected material does not match the requested skill.",
            )
        try:
            drill = ai_client.generate_drill(
                payload.skill,
                payload.minutes,
                material["content"],
            )
        except ConfigurationError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except AIServiceError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return db.save_drill(conn, drill)


def _min_recent_exam_year() -> int:
    return date.today().year - RECENT_EXAM_WINDOW_YEARS + 1


def _is_recent_real_exam_year(exam_year: Any) -> bool:
    if not isinstance(exam_year, int):
        return False
    return _min_recent_exam_year() <= exam_year <= date.today().year


app = create_app()
