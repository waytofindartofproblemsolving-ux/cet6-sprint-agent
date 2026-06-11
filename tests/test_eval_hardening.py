from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest


def walk_objects(schema):
    if schema.get("type") == "object":
        yield schema
        for child in schema.get("properties", {}).values():
            yield from walk_objects(child)
    elif schema.get("type") == "array":
        yield from walk_objects(schema.get("items", {}))


def test_endpoint_ai_errors_are_redacted_and_do_not_save_partial_attempts(tmp_path):
    from app.ai.openai_client import AIServiceError
    from app.main import create_app
    from app import db
    from app.schemas import Drill, Question

    class FailingGradeAI:
        def generate_drill(self, skill, minutes, material_text=None):
            return Drill(
                skill=skill,
                title="Writing Drill",
                minutes=minutes,
                instructions="Answer briefly.",
                questions=[
                    Question(
                        id="q1",
                        prompt="Write one sentence.",
                        choices=[],
                        answer="A precise sentence.",
                    )
                ],
                rubric="Score grammar.",
            )

        def grade_attempt(self, *_args, **_kwargs):
            raise AIServiceError("provider error includes sk-secret-value")

    db_path = tmp_path / "cet6.sqlite3"
    client = TestClient(create_app(ai_client=FailingGradeAI(), db_path=db_path))
    drill = client.post(
        "/api/drills/generate",
        json={"skill": "writing", "minutes": 8},
    ).json()

    response = client.post(
        "/api/attempts/grade",
        json={"drill_id": drill["id"], "answers": {"q1": "My sentence."}},
    )

    assert response.status_code == 502
    assert "sk-secret-value" not in response.text
    assert "sk-***" in response.text
    with db.connect(db_path) as conn:
        counts = db.dashboard_counts(conn)
    assert counts["attempts"] == 0
    assert counts["reviews"] == 0


def test_strict_schema_contract_is_recursive():
    from app.ai.openai_client import drill_response_format, feedback_response_format

    for schema_format in [drill_response_format(), feedback_response_format()]:
        schema = schema_format["format"]["schema"]
        for object_schema in walk_objects(schema):
            assert object_schema["additionalProperties"] is False
            assert set(object_schema["required"]) == set(object_schema["properties"])


def test_grade_attempt_sends_feedback_schema_and_parses_fallback_text():
    from app.ai.openai_client import OpenAIStudyClient
    from app.schemas import Drill, Question

    class RecordingResponses:
        def __init__(self):
            self.calls = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            content = SimpleNamespace(
                text=(
                    '{"score":75,"summary":"Clear enough.",'
                    '"corrections":[{"original":"make a progress","corrected":"make progress","explanation":"Progress is uncountable."}],'
                    '"mistake_tags":["collocation"],"next_action":"Review collocations."}'
                )
            )
            return SimpleNamespace(output=[SimpleNamespace(content=[content])])

    client = object.__new__(OpenAIStudyClient)
    client.settings = SimpleNamespace(openai_model="test-model")
    client.client = SimpleNamespace(responses=RecordingResponses())
    drill = Drill(
        id=1,
        skill="writing",
        title="Writing",
        minutes=8,
        instructions="Write.",
        questions=[Question(id="q1", prompt="Write.", choices=[], answer="")],
        rubric="Rubric.",
    )

    feedback = client.grade_attempt(drill, {"q1": "I make a progress."})

    call = client.client.responses.calls[0]
    assert feedback.score == 75
    assert call["text"]["format"]["name"] == "feedback"
    assert '"answers": {"q1": "I make a progress."}' in call["input"][1]["content"]


def test_unusable_grade_output_is_wrapped_as_ai_service_error():
    from app.ai.openai_client import AIServiceError, OpenAIStudyClient
    from app.schemas import Drill, Question

    class EmptyResponses:
        def create(self, **_kwargs):
            return SimpleNamespace(output=[])

    client = object.__new__(OpenAIStudyClient)
    client.settings = SimpleNamespace(openai_model="test-model")
    client.client = SimpleNamespace(responses=EmptyResponses())
    drill = Drill(
        id=1,
        skill="writing",
        title="Writing",
        minutes=8,
        instructions="Write.",
        questions=[Question(id="q1", prompt="Write.", choices=[], answer="")],
        rubric="Rubric.",
    )

    with pytest.raises(AIServiceError, match="feedback response"):
        client.grade_attempt(drill, {"q1": "Answer."})


def test_invalid_input_returns_clean_errors_without_extra_state(tmp_path):
    from app.main import create_app
    from app.ai.fake import FakeAIClient
    from app import db

    db_path = tmp_path / "cet6.sqlite3"
    client = TestClient(create_app(ai_client=FakeAIClient(), db_path=db_path))

    assert client.post("/api/drills/generate", json={"skill": "grammar", "minutes": 8}).status_code == 422
    assert client.post("/api/drills/generate", json={"skill": "writing", "minutes": 0}).status_code == 422
    assert client.post("/api/drills/generate", json={"skill": "writing", "minutes": 61}).status_code == 422
    assert client.post("/api/materials", json={"title": "", "content": ""}).status_code == 400
    assert client.post(
        "/api/attempts/grade",
        json={"drill_id": 999999, "answers": {"q1": "Answer."}},
    ).status_code == 404

    with db.connect(db_path) as conn:
        assert db.dashboard_counts(conn) == {"drills": 0, "attempts": 0, "reviews": 0}
