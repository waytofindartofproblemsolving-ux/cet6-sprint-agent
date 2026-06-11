from fastapi.testclient import TestClient


class RecordingAIClient:
    def __init__(self):
        self.generate_calls = 0
        self.last_material_text = None

    def generate_drill(self, *_args, **_kwargs):
        self.generate_calls += 1
        if len(_args) >= 3:
            self.last_material_text = _args[2]
        raise AssertionError("AI should not be called for an unknown material.")


class FailingAIClient:
    def generate_drill(self, *_args, **_kwargs):
        from app.config import ConfigurationError

        raise ConfigurationError("OPENAI_API_KEY is required for live AI.")

    def grade_attempt(self, *_args, **_kwargs):
        from app.config import ConfigurationError

        raise ConfigurationError("OpenAI request failed.")


def test_unknown_material_id_returns_404_without_calling_ai(tmp_path):
    from app import db
    from app.main import create_app

    db_path = tmp_path / "cet6.sqlite3"
    ai_client = RecordingAIClient()
    client = TestClient(create_app(ai_client=ai_client, db_path=db_path))

    response = client.post(
        "/api/drills/generate",
        json={"skill": "reading", "minutes": 10, "material_id": 999999},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Material not found."
    assert ai_client.generate_calls == 0
    with db.connect(db_path) as conn:
        assert db.dashboard_counts(conn)["drills"] == 0


def test_ai_setup_failure_returns_503_without_traceback(tmp_path):
    from app.main import create_app

    client = TestClient(create_app(ai_client=FailingAIClient(), db_path=tmp_path / "cet6.sqlite3"))

    response = client.post(
        "/api/drills/generate",
        json={"skill": "writing", "minutes": 8},
    )

    assert response.status_code == 503
    assert "OPENAI_API_KEY" in response.json()["detail"]
    assert "Traceback" not in response.text


def test_saved_material_can_be_listed_and_used_for_generation(tmp_path):
    from app.main import create_app
    from app.schemas import Drill, Question

    class MaterialAwareAIClient:
        def __init__(self):
            self.last_material_text = None

        def generate_drill(self, skill, minutes, material_text=None):
            self.last_material_text = material_text
            return Drill(
                skill=skill,
                title="Material Reading",
                minutes=minutes,
                instructions="Answer from the saved material.",
                questions=[
                    Question(
                        id="q1",
                        prompt="What does the material argue?",
                        choices=[],
                        answer="Practice improves accuracy.",
                    )
                ],
                rubric="Use evidence from the material.",
            )

    ai_client = MaterialAwareAIClient()
    client = TestClient(create_app(ai_client=ai_client, db_path=tmp_path / "cet6.sqlite3"))

    saved = client.post(
        "/api/materials",
        json={
            "title": "My CET-6 passage",
            "content": "Practice improves accuracy when feedback is immediate.",
        },
    )
    assert saved.status_code == 200

    listed = client.get("/api/materials")
    assert listed.status_code == 200
    assert listed.json() == [{"id": saved.json()["id"], "title": "My CET-6 passage"}]

    generated = client.post(
        "/api/drills/generate",
        json={"skill": "reading", "minutes": 10, "material_id": saved.json()["id"]},
    )

    assert generated.status_code == 200
    assert ai_client.last_material_text == "Practice improves accuracy when feedback is immediate."
