import importlib

import pytest
from fastapi.testclient import TestClient


def import_required(module_name: str):
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        pytest.fail(f"Expected module {module_name} to exist: {exc}")


def test_dashboard_and_drill_submission_flow_uses_fake_ai(tmp_path, monkeypatch):
    main = import_required("app.main")
    fake_ai = import_required("app.ai.fake")
    db = import_required("app.db")

    db_path = tmp_path / "cet6.sqlite3"
    monkeypatch.setenv("CET6_DB_PATH", str(db_path))
    app = main.create_app(ai_client=fake_ai.FakeAIClient())
    client = TestClient(app)

    dashboard = client.get("/")
    assert dashboard.status_code == 200
    assert "CET-6 Sprint" in dashboard.text

    generated = client.post(
        "/api/drills/generate",
        json={"skill": "writing", "minutes": 8},
    )
    assert generated.status_code == 200
    drill = generated.json()
    assert drill["skill"] == "writing"
    assert drill["id"] > 0

    graded = client.post(
        "/api/attempts/grade",
        json={
            "drill_id": drill["id"],
            "answers": {"q1": "I think practice is important."},
        },
    )
    assert graded.status_code == 200
    feedback = graded.json()
    assert feedback["score"] >= 0
    assert feedback["mistake_tags"]

    with db.connect(db_path) as conn:
        assert db.dashboard_counts(conn)["reviews"] == 1

    due = client.get("/api/review/due")
    assert due.status_code == 200
    assert due.json() == []
