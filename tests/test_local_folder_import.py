from pathlib import Path
import zipfile

from fastapi.testclient import TestClient


SAMPLE_PDF = b"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj
4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj
5 0 obj << /Length 120 >> stream
BT /F1 12 Tf 72 720 Td (## Reading) Tj 0 -18 Td (PDF source text) Tj 0 -18 Td (## Writing) Tj 0 -18 Td (Write source text) Tj ET
endstream endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000241 00000 n 
0000000311 00000 n 
trailer << /Root 1 0 R /Size 6 >>
startxref
451
%%EOF
"""


def write_docx(path: Path, lines: list[str]) -> None:
    body = "".join(
        f"<w:p><w:r><w:t>{line}</w:t></w:r></w:p>"
        for line in lines
    )
    with zipfile.ZipFile(path, "w") as package:
        package.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>""",
        )
        package.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>""",
        )
        package.writestr(
            "word/document.xml",
            f"""<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>{body}</w:body></w:document>""",
        )


def test_ad_candidate_detection_and_metadata_parsing():
    from app.services.local_paper_import import (
        ad_candidate_reason,
        parse_exam_metadata,
    )

    assert ad_candidate_reason(Path("2025-06-01/微信搜索【英语听力助手】或微信扫码.png"))
    assert ad_candidate_reason(Path("2024-06-01/2024年6月第1套英语六级真题【推荐使用PDF版】.docx"))
    assert ad_candidate_reason(Path("2025-06-01/2025年6月第1套英语六级真题【可复制可搜索，打印首选】——【公众号：英语六级真题PDF】.pdf")) is None

    assert parse_exam_metadata(Path("2024-06-01/2024年6月第1套英语六级真题.pdf")).model_dump() == {
        "exam_year": 2024,
        "exam_month": 6,
        "set_no": 1,
    }
    assert parse_exam_metadata(Path("2019年12月CET6/2019.12第3套/2019.12六级真题第3套.pdf")).set_no == 3


def test_extract_text_from_pdf_docx_and_empty_pdf(tmp_path):
    from app.services.local_paper_import import TextExtractionError, extract_text_from_file

    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(SAMPLE_PDF)
    assert "PDF source text" in extract_text_from_file(pdf_path)

    docx_path = tmp_path / "sample.docx"
    write_docx(docx_path, ["## Listening", "Transcript source text"])
    assert "Transcript source text" in extract_text_from_file(docx_path)

    empty_pdf = tmp_path / "empty.pdf"
    empty_pdf.write_bytes(
        b"%PDF-1.4\n1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [] /Count 0 >> endobj\n"
        b"trailer << /Root 1 0 R >>\n%%EOF\n"
    )
    try:
        extract_text_from_file(empty_pdf)
    except TextExtractionError as exc:
        assert "No extractable text" in str(exc)
    else:
        raise AssertionError("Expected empty PDF extraction to fail.")


def test_import_local_folder_quarantines_ads_and_splits_materials(tmp_path):
    from app import db
    from app.main import create_app
    from app.ai.fake import FakeAIClient

    root = tmp_path / "papers"
    set_dir = root / "2024-06-01"
    set_dir.mkdir(parents=True)
    (set_dir / "2024年6月第1套英语六级真题【可复制可搜索，打印首选】——【公众号：英语六级真题PDF】.pdf").write_bytes(SAMPLE_PDF)
    (set_dir / "2024年6月第1套英语六级真题解析.pdf").write_bytes(SAMPLE_PDF)
    (set_dir / "微信搜索【英语听力助手】或微信扫码，即可播放听力音频.png").write_bytes(b"ad")
    write_docx(set_dir / "2024年6月第1套英语六级真题【推荐使用PDF版】.docx", ["ad docx"])

    db_path = tmp_path / "cet6.sqlite3"
    client = TestClient(create_app(ai_client=FakeAIClient(), db_path=db_path))
    response = client.post(
        "/api/papers/import-local-folder",
        json={"root_path": str(root)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["quarantined_count"] == 2
    assert body["imported_material_count"] == 2
    assert body["answer_explanation_count"] == 1
    assert (root / "_quarantine_ads" / "manifest.json").exists()
    assert not any(path.name.endswith(".png") for path in set_dir.iterdir())

    with db.connect(db_path) as conn:
        materials = db.list_materials(conn)
        answers = db.list_answer_explanations(conn)
    assert {item["skill"] for item in materials} == {"reading", "writing"}
    assert len(answers) == 1
    assert "解析" in answers[0]["title"]


def test_local_folder_import_defaults_to_project_root(tmp_path, monkeypatch):
    from app.ai.fake import FakeAIClient
    import app.main as main_module

    root = tmp_path / "project"
    set_dir = root / "2024-06-01"
    set_dir.mkdir(parents=True)
    (set_dir / "paper.pdf").write_bytes(SAMPLE_PDF)

    monkeypatch.setattr(main_module, "PROJECT_ROOT", root)
    client = TestClient(
        main_module.create_app(
            ai_client=FakeAIClient(),
            db_path=tmp_path / "cet6.sqlite3",
        )
    )

    response = client.post("/api/papers/import-local-folder", json={})

    assert response.status_code == 200
    assert response.json()["imported_material_count"] == 2


def test_import_local_folder_ignores_non_exam_text_files(tmp_path):
    from app.ai.fake import FakeAIClient
    from app.main import create_app

    root = tmp_path / "project"
    root.mkdir()
    (root / "requirements.txt").write_text("pytest>=8.2", encoding="utf-8")
    set_dir = root / "2024-06-01"
    set_dir.mkdir()
    (set_dir / "paper.pdf").write_bytes(SAMPLE_PDF)

    client = TestClient(create_app(ai_client=FakeAIClient(), db_path=tmp_path / "cet6.sqlite3"))
    response = client.post(
        "/api/papers/import-local-folder",
        json={"root_path": str(root)},
    )

    assert response.status_code == 200
    assert response.json()["imported_material_count"] == 2
    assert response.json()["failed_count"] == 0


def test_import_local_folder_is_idempotent(tmp_path):
    from app import db
    from app.ai.fake import FakeAIClient
    from app.main import create_app

    root = tmp_path / "project"
    set_dir = root / "2024-06-01"
    set_dir.mkdir(parents=True)
    (set_dir / "paper.pdf").write_bytes(SAMPLE_PDF)
    (set_dir / ("answer-" + "\u89e3\u6790" + ".pdf")).write_bytes(SAMPLE_PDF)

    db_path = tmp_path / "cet6.sqlite3"
    client = TestClient(create_app(ai_client=FakeAIClient(), db_path=db_path))

    first = client.post("/api/papers/import-local-folder", json={"root_path": str(root)})
    second = client.post("/api/papers/import-local-folder", json={"root_path": str(root)})

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["imported_material_count"] == 0
    assert second.json()["answer_explanation_count"] == 0
    with db.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM materials").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM answer_explanations").fetchone()[0] == 1


def test_large_answer_pdf_is_registered_without_text_extraction(tmp_path, monkeypatch):
    from app import db
    from app.ai.fake import FakeAIClient
    import app.services.local_paper_import as importer
    from app.main import create_app

    monkeypatch.setattr(importer, "MAX_ANSWER_EXTRACTION_BYTES", 10)
    root = tmp_path / "project"
    set_dir = root / "2024-06-01"
    set_dir.mkdir(parents=True)
    (set_dir / "paper.pdf").write_bytes(SAMPLE_PDF)
    (set_dir / ("answer-" + "\u89e3\u6790" + ".pdf")).write_bytes(b"not a pdf, intentionally too large")

    db_path = tmp_path / "cet6.sqlite3"
    client = TestClient(create_app(ai_client=FakeAIClient(), db_path=db_path))
    response = client.post("/api/papers/import-local-folder", json={"root_path": str(root)})

    assert response.status_code == 200
    assert response.json()["answer_explanation_count"] == 1
    assert response.json()["failed_count"] == 0
    with db.connect(db_path) as conn:
        content = conn.execute("SELECT content FROM answer_explanations").fetchone()["content"]
    assert "Text extraction skipped" in content


def test_import_local_folder_skips_doc_files_with_report(tmp_path):
    from app.main import create_app
    from app.ai.fake import FakeAIClient

    root = tmp_path / "papers"
    set_dir = root / "2018年12月CET6" / "2018.12第1套"
    set_dir.mkdir(parents=True)
    (set_dir / "2018.12六级真题第1套.doc").write_bytes(b"legacy word binary")

    client = TestClient(create_app(ai_client=FakeAIClient(), db_path=tmp_path / "cet6.sqlite3"))
    response = client.post(
        "/api/papers/import-local-folder",
        json={"root_path": str(root)},
    )

    assert response.status_code == 200
    assert response.json()["failed_count"] == 1
    assert ".doc files require manual conversion" in response.json()["failures"][0]["error"]
