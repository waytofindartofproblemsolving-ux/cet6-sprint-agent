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


def test_split_exam_paper_ignores_body_lines_that_start_with_skill_words():
    from app.services.paper_import import split_exam_paper

    sections = split_exam_paper(
        """
## Reading
The passage starts here.
writing it was one of America's most fascinating discoveries.
reading initiatives can reduce inequality in the earliest years.
"""
    )

    assert len(sections) == 1
    assert sections[0].skill == "reading"
    assert "writing it was" in sections[0].content


def test_split_exam_paper_accepts_unicode_roman_numeral_exam_headings():
    from app.services.paper_import import split_exam_paper

    sections = split_exam_paper(
        """
2021 College English Test Band 6
Part I\u2161I (30 minutes)Listening Comprehension
Questions 1 to 4 are based on the conversation.
Part \u2162 Reading Comprehension (40 minutes)
Read the following passage and answer questions.
Part \u2163 Translation (30 minutes)
Translate the following paragraph into English.
"""
    )

    assert [section.skill for section in sections] == [
        "listening",
        "reading",
        "translation",
    ]
    assert "Questions 1 to 4" in sections[0].content


def test_split_exam_paper_accepts_timestamped_listening_transcript_heading():
    from app.services.paper_import import split_exam_paper

    sections = split_exam_paper(
        """
[00:00.69]College English Test Band 6<ch>大学英语六级考试
[00:04.25]Part \u2161 Listening Comprehension<ch>第二部分 听力理解
[00:07.80]Section A Directions: In this section, you will hear two long conversations.
[00:41.60]Conversation One<ch>对话一
"""
    )

    assert len(sections) == 1
    assert sections[0].skill == "listening"
    assert "Conversation One" in sections[0].content
