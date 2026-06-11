from fastapi.testclient import TestClient


def test_import_real_exam_text_splits_sections_by_skill(tmp_path):
    from app.main import create_app
    from app.ai.fake import FakeAIClient

    client = TestClient(create_app(ai_client=FakeAIClient(), db_path=tmp_path / "cet6.sqlite3"))

    response = client.post(
        "/api/papers/import",
        json={
            "title": "2024-12 CET-6 Set 1",
            "exam_year": 2024,
            "source_text": """
## Reading
Practice improves accuracy when feedback is immediate.

## Writing
Write an essay about deliberate practice.

【翻译】
把这段中文翻译成英文。
""",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["imported_count"] == 3
    assert [item["skill"] for item in body["materials"]] == [
        "reading",
        "writing",
        "translation",
    ]

    materials = client.get("/api/materials").json()
    assert {item["skill"] for item in materials} == {"reading", "writing", "translation"}
    assert all(item["exam_year"] == 2024 for item in materials)


def test_import_real_exam_text_rejects_unmarked_source(tmp_path):
    from app import db
    from app.main import create_app
    from app.ai.fake import FakeAIClient

    db_path = tmp_path / "cet6.sqlite3"
    client = TestClient(create_app(ai_client=FakeAIClient(), db_path=db_path))

    response = client.post(
        "/api/papers/import",
        json={
            "title": "2024-12 CET-6 Set 1",
            "exam_year": 2024,
            "source_text": "A whole paper pasted without section headings.",
        },
    )

    assert response.status_code == 400
    assert "No supported question-type sections" in response.json()["detail"]
    with db.connect(db_path) as conn:
        assert db.list_materials(conn) == []


def test_drill_generation_rejects_mismatched_material_skill(tmp_path):
    from app.main import create_app
    from app.ai.fake import FakeAIClient

    client = TestClient(create_app(ai_client=FakeAIClient(), db_path=tmp_path / "cet6.sqlite3"))
    saved = client.post(
        "/api/materials",
        json={
            "title": "2024 Writing",
            "skill": "writing",
            "exam_year": 2024,
            "content": "Write an essay about practice.",
        },
    )
    assert saved.status_code == 200

    response = client.post(
        "/api/drills/generate",
        json={"skill": "reading", "minutes": 8, "material_id": saved.json()["id"]},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Selected material does not match the requested skill."
