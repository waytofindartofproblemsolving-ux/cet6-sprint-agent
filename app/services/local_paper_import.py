from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import shutil
from typing import Any

from app import db
from app.services.paper_import import split_exam_paper


QUARANTINE_DIR = "_quarantine_ads"
SUPPORTED_TEXT_EXTENSIONS = {".pdf", ".docx", ".txt"}


class TextExtractionError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExamMetadata:
    exam_year: int
    exam_month: int | None
    set_no: int | None

    def model_dump(self) -> dict[str, int | None]:
        return {
            "exam_year": self.exam_year,
            "exam_month": self.exam_month,
            "set_no": self.set_no,
        }


@dataclass
class LocalImportReport:
    imported_material_count: int = 0
    answer_explanation_count: int = 0
    quarantined_count: int = 0
    failed_count: int = 0
    missing_listening_count: int = 0
    materials: list[dict[str, Any]] = field(default_factory=list)
    answers: list[dict[str, Any]] = field(default_factory=list)
    quarantined: list[dict[str, str]] = field(default_factory=list)
    failures: list[dict[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "imported_material_count": self.imported_material_count,
            "answer_explanation_count": self.answer_explanation_count,
            "quarantined_count": self.quarantined_count,
            "failed_count": self.failed_count,
            "missing_listening_count": self.missing_listening_count,
            "materials": self.materials,
            "answers": self.answers,
            "quarantined": self.quarantined,
            "failures": self.failures,
        }


def ad_candidate_reason(path: Path) -> str | None:
    name = path.name
    suffix = path.suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".webp"} and any(
        marker in name for marker in ["微信搜索", "扫码", "英语听力助手"]
    ):
        return "audio assistant QR/image ad"
    if (
        suffix == ".docx"
        and "推荐使用PDF版" in name
        and "2024年6月" in name
    ):
        return "2024-06 promotional duplicate docx"
    return None


def parse_exam_metadata(path: Path) -> ExamMetadata:
    text = str(path)
    year_match = re.search(r"(20\d{2})", text)
    if not year_match:
        raise ValueError(f"Cannot parse exam year from {path}")
    year = int(year_match.group(1))

    month_match = (
        re.search(r"20\d{2}[-.年](\d{1,2})", text)
        or re.search(r"20\d{2}年(\d{1,2})月", text)
    )
    month = int(month_match.group(1)) if month_match else None

    set_match = re.search(r"第\s*(\d+)\s*套", text)
    if set_match:
        set_no = int(set_match.group(1))
    else:
        folder_match = re.search(r"20\d{2}-\d{2}-(\d{2})", text)
        set_no = int(folder_match.group(1)) if folder_match else None

    return ExamMetadata(exam_year=year, exam_month=month, set_no=set_no)


def extract_text_from_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        text = _extract_pdf_text(path)
    elif suffix == ".docx":
        text = _extract_docx_text(path)
    elif suffix == ".txt":
        text = path.read_text(encoding="utf-8", errors="ignore")
    elif suffix == ".doc":
        raise TextExtractionError(".doc files require manual conversion to .docx or PDF.")
    else:
        raise TextExtractionError(f"Unsupported file type: {path.suffix}")

    text = text.strip()
    if not text:
        raise TextExtractionError(f"No extractable text found in {path.name}.")
    return text


def import_local_folder(root_path: Path, connection: Any) -> dict[str, Any]:
    root = root_path.resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"Import root does not exist: {root}")

    report = LocalImportReport()
    _quarantine_ads(root, report)

    grouped = _group_import_candidates(root)
    for files in grouped.values():
        _import_group(root, files, connection, report)

    _write_quarantine_manifest(root, report)
    return report.as_dict()


def _extract_pdf_text(path: Path) -> str:
    from pypdf import PdfReader

    try:
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        raise TextExtractionError(f"No extractable text found in {path.name}.") from exc


def _extract_docx_text(path: Path) -> str:
    from docx import Document

    document = Document(str(path))
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def _quarantine_ads(root: Path, report: LocalImportReport) -> None:
    for path in list(root.rglob("*")):
        if not path.is_file() or QUARANTINE_DIR in path.parts:
            continue
        reason = ad_candidate_reason(path)
        if not reason:
            continue
        relative = path.relative_to(root)
        target = root / QUARANTINE_DIR / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(target))
        item = {
            "original_path": str(relative),
            "quarantine_path": str(target.relative_to(root)),
            "reason": reason,
        }
        report.quarantined.append(item)
        report.quarantined_count += 1


def _write_quarantine_manifest(root: Path, report: LocalImportReport) -> None:
    if not report.quarantined:
        return
    manifest = root / QUARANTINE_DIR / "manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps(report.quarantined, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _group_import_candidates(root: Path) -> dict[tuple[int, int | None, int | None], list[Path]]:
    groups: dict[tuple[int, int | None, int | None], list[Path]] = {}
    for path in root.rglob("*"):
        if not path.is_file() or QUARANTINE_DIR in path.parts:
            continue
        if path.suffix.lower() not in SUPPORTED_TEXT_EXTENSIONS | {".doc"}:
            continue
        metadata = parse_exam_metadata(path)
        key = (metadata.exam_year, metadata.exam_month, metadata.set_no)
        groups.setdefault(key, []).append(path)
    return groups


def _import_group(
    root: Path,
    files: list[Path],
    connection: Any,
    report: LocalImportReport,
) -> None:
    answer_files = [path for path in files if _is_answer_file(path)]
    source_files = [path for path in files if not _is_answer_file(path)]

    for answer in sorted(answer_files, key=lambda path: path.name):
        _import_answer(root, answer, connection, report)

    for source in _source_priority(source_files):
        if source.suffix.lower() == ".doc":
            _record_failure(report, root, source, ".doc files require manual conversion to .docx or PDF.")
            continue
        try:
            text = extract_text_from_file(source)
        except TextExtractionError as exc:
            _record_failure(report, root, source, str(exc))
            continue
        sections = split_exam_paper(text)
        if not sections:
            _record_failure(report, root, source, "No supported question-type sections were found.")
            continue
        metadata = parse_exam_metadata(source)
        imported_skills = set()
        for section in sections:
            material_id = db.save_material(
                connection,
                _material_title(source, section.heading),
                section.content,
                metadata.exam_year,
                section.skill,
            )
            report.materials.append(
                {
                    "id": material_id,
                    "title": _material_title(source, section.heading),
                    "skill": section.skill,
                    "exam_year": metadata.exam_year,
                    "source_path": str(source.relative_to(root)),
                }
            )
            report.imported_material_count += 1
            imported_skills.add(section.skill)
        if _has_audio(files) and "listening" not in imported_skills:
            report.missing_listening_count += 1
        return


def _import_answer(
    root: Path,
    path: Path,
    connection: Any,
    report: LocalImportReport,
) -> None:
    try:
        text = extract_text_from_file(path)
    except TextExtractionError as exc:
        _record_failure(report, root, path, str(exc))
        return
    metadata = parse_exam_metadata(path)
    answer_id = db.save_answer_explanation(
        connection,
        path.stem,
        text,
        metadata.exam_year,
        str(path.relative_to(root)),
        exam_month=metadata.exam_month,
        set_no=metadata.set_no,
    )
    report.answers.append(
        {
            "id": answer_id,
            "title": path.stem,
            "exam_year": metadata.exam_year,
            "source_path": str(path.relative_to(root)),
        }
    )
    report.answer_explanation_count += 1


def _is_answer_file(path: Path) -> bool:
    return any(marker in path.name for marker in ["答案", "解析", "详解"])


def _source_priority(paths: list[Path]) -> list[Path]:
    priority = {".pdf": 0, ".docx": 1, ".txt": 2, ".doc": 3}
    return sorted(paths, key=lambda path: (priority.get(path.suffix.lower(), 99), path.name))


def _record_failure(report: LocalImportReport, root: Path, path: Path, error: str) -> None:
    report.failures.append({"source_path": str(path.relative_to(root)), "error": error})
    report.failed_count += 1


def _material_title(path: Path, heading: str) -> str:
    return f"{path.stem} - {heading}"


def _has_audio(files: list[Path]) -> bool:
    return any(path.suffix.lower() == ".mp3" for path in files)
