import importlib

import pytest


def import_required(module_name: str):
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        pytest.fail(f"Expected module {module_name} to exist: {exc}")


def test_drill_schema_parses_model_json():
    schemas = import_required("app.schemas")
    payload = {
        "skill": "reading",
        "title": "Timed Reading Sprint",
        "minutes": 12,
        "instructions": "Answer quickly, then review the vocabulary.",
        "questions": [
            {
                "id": "q1",
                "prompt": "What is the main idea?",
                "choices": ["A", "B", "C", "D"],
                "answer": "A",
            }
        ],
        "rubric": "1 point for the correct main idea.",
    }

    drill = schemas.Drill.model_validate(payload)

    assert drill.skill == "reading"
    assert drill.questions[0].id == "q1"
    assert drill.questions[0].answer == "A"


def test_feedback_schema_requires_next_action_and_mistake_tags():
    schemas = import_required("app.schemas")
    payload = {
        "score": 72,
        "summary": "Good structure, but vocabulary precision is weak.",
        "corrections": [
            {
                "original": "make a progress",
                "corrected": "make progress",
                "explanation": "Progress is uncountable here.",
            }
        ],
        "mistake_tags": ["collocation", "article"],
        "next_action": "Review collocations for 8 minutes.",
    }

    feedback = schemas.Feedback.model_validate(payload)

    assert feedback.score == 72
    assert feedback.mistake_tags == ["collocation", "article"]
    assert feedback.next_action.startswith("Review")
