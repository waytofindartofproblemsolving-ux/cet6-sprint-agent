from __future__ import annotations

from dataclasses import dataclass
import re


SUPPORTED_SKILLS = ("reading", "listening", "writing", "translation", "vocabulary")

HEADING_ALIASES = {
    "reading": "reading",
    "reading comprehension": "reading",
    "阅读": "reading",
    "阅读理解": "reading",
    "listening": "listening",
    "listening transcript": "listening",
    "听力": "listening",
    "writing": "writing",
    "写作": "writing",
    "translation": "translation",
    "翻译": "translation",
    "vocabulary": "vocabulary",
    "词汇": "vocabulary",
}

EXAM_HEADING_PATTERNS = (
    (re.compile(r"^(part\s+i\s+)?writing(?:\s*(?:\(|:|-)|$)"), "writing"),
    (re.compile(r"^(part\s+ii\s+)?listening\s+comprehension(?:\s*(?:\(|:|-)|$)"), "listening"),
    (re.compile(r"^(part\s+iii\s+)?reading\s+comprehension(?:\s*(?:\(|:|-)|$)"), "reading"),
    (re.compile(r"^(part\s+iv\s+)?translation(?:\s*(?:\(|:|-)|$)"), "translation"),
    (re.compile(r"^vocabulary(?:\s*(?:\(|:|-)|$)"), "vocabulary"),
)


@dataclass(frozen=True)
class PaperSection:
    skill: str
    heading: str
    content: str


def split_exam_paper(source_text: str) -> list[PaperSection]:
    sections: list[PaperSection] = []
    active_skill: str | None = None
    active_heading = ""
    buffer: list[str] = []

    for raw_line in source_text.splitlines():
        skill = _heading_skill(raw_line)
        if skill is not None:
            _append_section(sections, active_skill, active_heading, buffer)
            active_skill = skill
            active_heading = _clean_heading(raw_line)
            buffer = []
            continue
        if active_skill is not None:
            buffer.append(raw_line)

    _append_section(sections, active_skill, active_heading, buffer)
    return sections


def _append_section(
    sections: list[PaperSection],
    skill: str | None,
    heading: str,
    buffer: list[str],
) -> None:
    content = "\n".join(buffer).strip()
    if skill is not None and content:
        sections.append(PaperSection(skill=skill, heading=heading or skill.title(), content=content))


def _heading_skill(line: str) -> str | None:
    heading = _clean_heading(line).lower()
    if not heading:
        return None
    if heading in HEADING_ALIASES:
        return HEADING_ALIASES[heading]
    for pattern, skill in EXAM_HEADING_PATTERNS:
        if pattern.search(heading):
            return skill
    if not _has_heading_marker(line):
        return None
    for alias, skill in HEADING_ALIASES.items():
        if heading.startswith(f"{alias} "):
            return skill
    return None


def _clean_heading(line: str) -> str:
    heading = line.strip()
    heading = re.sub(r"^#{1,6}\s*", "", heading)
    heading = heading.strip("[]【】:")
    return heading.strip()


def _has_heading_marker(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("#") or stripped.startswith("[") or stripped.startswith("【")
