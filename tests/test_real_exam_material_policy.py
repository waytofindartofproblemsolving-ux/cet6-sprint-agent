from fastapi.testclient import TestClient


class RecordingAIClient:
    def __init__(self):
        self.generate_calls = 0
        self.last_material_text = None

    def generate_drill(self, *_args, **_kwargs):
        self.generate_calls += 1
        if len(_args) >= 3:
            self.last_material_text = _args[2]
        raise AssertionError("AI should not be called when material policy fails.")


def test_drill_generation_requires_selected_real_exam_material(tmp_path):
    from app import db
    from app.main import create_app

    db_path = tmp_path / "cet6.sqlite3"
    ai_client = RecordingAIClient()
    client = TestClient(create_app(ai_client=ai_client, db_path=db_path))

    response = client.post(
        "/api/drills/generate",
        json={"skill": "reading", "minutes": 8},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Select a recent real CET-6 exam material first."
    assert ai_client.generate_calls == 0
    with db.connect(db_path) as conn:
        assert db.dashboard_counts(conn)["drills"] == 0


def test_material_save_rejects_outdated_exam_year(tmp_path):
    from app.main import create_app

    client = TestClient(create_app(ai_client=RecordingAIClient(), db_path=tmp_path / "cet6.sqlite3"))

    response = client.post(
        "/api/materials",
        json={
            "title": "Old CET-6 paper",
            "skill": "reading",
            "exam_year": 2010,
            "content": "Old real exam text.",
        },
    )

    assert response.status_code == 400
    assert "past 15 years" in response.json()["detail"]


def test_material_without_exam_year_cannot_be_used_for_generation(tmp_path):
    from app import db
    from app.main import create_app

    db_path = tmp_path / "cet6.sqlite3"
    ai_client = RecordingAIClient()
    client = TestClient(create_app(ai_client=ai_client, db_path=db_path))
    with db.connect(db_path) as conn:
        material_id = conn.execute(
            "INSERT INTO materials (title, content) VALUES (?, ?)",
            ("Legacy material", "Legacy content without source year."),
        ).lastrowid
        conn.commit()

    response = client.post(
        "/api/drills/generate",
        json={"skill": "reading", "minutes": 8, "material_id": material_id},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Material must be from a recent real CET-6 exam."
    assert ai_client.generate_calls == 0
    assert client.get("/api/materials").json() == []


def test_recent_real_exam_material_can_drive_generation(tmp_path):
    from app.main import create_app
    from app.schemas import Drill, Question

    class MaterialAwareAIClient:
        def __init__(self):
            self.last_material_text = None

        def generate_drill(self, skill, minutes, material_text=None):
            self.last_material_text = material_text
            return Drill(
                skill=skill,
                title="Recent Real Exam Reading",
                minutes=minutes,
                instructions="Answer from the recent real exam material.",
                questions=[
                    Question(
                        id="q1",
                        prompt="What does the real exam material argue?",
                        choices=[],
                        answer="Practice improves accuracy.",
                    )
                ],
                rubric="Use evidence from the real exam material.",
            )

    ai_client = MaterialAwareAIClient()
    client = TestClient(create_app(ai_client=ai_client, db_path=tmp_path / "cet6.sqlite3"))

    saved = client.post(
        "/api/materials",
        json={
            "title": "2024-12 CET-6 Reading Passage 1",
            "skill": "reading",
            "exam_year": 2024,
            "content": "Practice improves accuracy when feedback is immediate.",
        },
    )
    assert saved.status_code == 200

    generated = client.post(
        "/api/drills/generate",
        json={"skill": "reading", "minutes": 8, "material_id": saved.json()["id"]},
    )

    assert generated.status_code == 200
    assert ai_client.last_material_text == "Practice improves accuracy when feedback is immediate."
