from __future__ import annotations

from datetime import date
import json
import os
from pathlib import Path
import sqlite3
from typing import Any

from app.schemas import Drill, Feedback, ReviewItem


def default_db_path() -> Path:
    return Path(os.getenv("CET6_DB_PATH", "cet6.sqlite3"))


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path is not None else default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    init_db(connection)
    return connection


def init_db(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            skill TEXT,
            exam_year INTEGER,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS drills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            skill TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            drill_id INTEGER NOT NULL,
            answers TEXT NOT NULL,
            feedback TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS review_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mistake_type TEXT NOT NULL,
            prompt TEXT NOT NULL,
            user_answer TEXT NOT NULL,
            corrected_answer TEXT NOT NULL,
            due_date TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS answer_explanations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            exam_year INTEGER NOT NULL,
            exam_month INTEGER,
            set_no INTEGER,
            content TEXT NOT NULL,
            source_path TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(materials)").fetchall()
    }
    if "exam_year" not in columns:
        connection.execute("ALTER TABLE materials ADD COLUMN exam_year INTEGER")
    if "skill" not in columns:
        connection.execute("ALTER TABLE materials ADD COLUMN skill TEXT")
    connection.commit()


def save_drill(connection: sqlite3.Connection, drill: Drill) -> Drill:
    payload = drill.model_dump(mode="json", exclude={"id"})
    cursor = connection.execute(
        "INSERT INTO drills (skill, payload) VALUES (?, ?)",
        (drill.skill, json.dumps(payload, ensure_ascii=False)),
    )
    connection.commit()
    return drill.model_copy(update={"id": int(cursor.lastrowid)})


def get_drill(connection: sqlite3.Connection, drill_id: int) -> Drill | None:
    row = connection.execute("SELECT id, payload FROM drills WHERE id = ?", (drill_id,)).fetchone()
    if row is None:
        return None
    payload: dict[str, Any] = json.loads(row["payload"])
    payload["id"] = row["id"]
    return Drill.model_validate(payload)


def save_attempt(
    connection: sqlite3.Connection,
    drill_id: int,
    answers: dict[str, str],
    feedback: Feedback,
) -> int:
    cursor = connection.execute(
        "INSERT INTO attempts (drill_id, answers, feedback) VALUES (?, ?, ?)",
        (
            drill_id,
            json.dumps(answers, ensure_ascii=False),
            feedback.model_dump_json(),
        ),
    )
    connection.commit()
    return int(cursor.lastrowid)


def save_review_items(
    connection: sqlite3.Connection,
    review_items: list[ReviewItem],
) -> list[ReviewItem]:
    saved: list[ReviewItem] = []
    for item in review_items:
        cursor = connection.execute(
            """
            INSERT INTO review_items
                (mistake_type, prompt, user_answer, corrected_answer, due_date)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                item.mistake_type,
                item.prompt,
                item.user_answer,
                item.corrected_answer,
                item.due_date.isoformat(),
            ),
        )
        saved.append(item.model_copy(update={"id": int(cursor.lastrowid)}))
    connection.commit()
    return saved


def list_due_review_items(
    connection: sqlite3.Connection,
    today: date | None = None,
) -> list[ReviewItem]:
    due_by = (today or date.today()).isoformat()
    rows = connection.execute(
        """
        SELECT id, mistake_type, prompt, user_answer, corrected_answer, due_date
        FROM review_items
        WHERE due_date <= ?
        ORDER BY due_date ASC, id ASC
        """,
        (due_by,),
    ).fetchall()
    return [
        ReviewItem(
            id=row["id"],
            mistake_type=row["mistake_type"],
            prompt=row["prompt"],
            user_answer=row["user_answer"],
            corrected_answer=row["corrected_answer"],
            due_date=date.fromisoformat(row["due_date"]),
        )
        for row in rows
    ]


def save_material(
    connection: sqlite3.Connection,
    title: str,
    content: str,
    exam_year: int,
    skill: str,
) -> int:
    cursor = connection.execute(
        "INSERT INTO materials (title, content, exam_year, skill) VALUES (?, ?, ?, ?)",
        (title.strip(), content.strip(), exam_year, skill),
    )
    connection.commit()
    return int(cursor.lastrowid)


def list_materials(connection: sqlite3.Connection, skill: str | None = None) -> list[dict[str, Any]]:
    params: tuple[Any, ...] = ()
    skill_filter = ""
    if skill:
        skill_filter = "AND skill = ?"
        params = (skill,)
    rows = connection.execute(
        f"""
        SELECT id, title, skill, exam_year
        FROM materials
        WHERE exam_year IS NOT NULL AND skill IS NOT NULL
        {skill_filter}
        ORDER BY id DESC
        """,
        params,
    ).fetchall()
    return [
        {
            "id": int(row["id"]),
            "title": str(row["title"]),
            "skill": str(row["skill"]),
            "exam_year": row["exam_year"],
        }
        for row in rows
    ]


def get_material(connection: sqlite3.Connection, material_id: int | None) -> dict[str, Any] | None:
    if material_id is None:
        return None
    row = connection.execute(
        "SELECT content, exam_year, skill FROM materials WHERE id = ?",
        (material_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "content": str(row["content"]),
        "exam_year": row["exam_year"],
        "skill": row["skill"],
    }


def save_answer_explanation(
    connection: sqlite3.Connection,
    title: str,
    content: str,
    exam_year: int,
    source_path: str,
    exam_month: int | None = None,
    set_no: int | None = None,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO answer_explanations
            (title, exam_year, exam_month, set_no, content, source_path)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            title.strip(),
            exam_year,
            exam_month,
            set_no,
            content.strip(),
            source_path,
        ),
    )
    connection.commit()
    return int(cursor.lastrowid)


def list_answer_explanations(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT id, title, exam_year, exam_month, set_no, source_path
        FROM answer_explanations
        ORDER BY id ASC
        """
    ).fetchall()
    return [
        {
            "id": int(row["id"]),
            "title": str(row["title"]),
            "exam_year": int(row["exam_year"]),
            "exam_month": row["exam_month"],
            "set_no": row["set_no"],
            "source_path": str(row["source_path"]),
        }
        for row in rows
    ]


def dashboard_counts(connection: sqlite3.Connection) -> dict[str, int]:
    return {
        "drills": int(connection.execute("SELECT COUNT(*) FROM drills").fetchone()[0]),
        "attempts": int(connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]),
        "reviews": int(connection.execute("SELECT COUNT(*) FROM review_items").fetchone()[0]),
    }
