import importlib
from datetime import date, timedelta

import pytest


def import_required(module_name: str):
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        pytest.fail(f"Expected module {module_name} to exist: {exc}")


def test_review_items_are_due_the_next_day_for_new_mistakes():
    schemas = import_required("app.schemas")
    review_service = import_required("app.services.review")
    today = date(2026, 6, 10)
    feedback = schemas.Feedback(
        score=61,
        summary="Meaning is understandable, grammar needs work.",
        corrections=[
            schemas.Correction(
                original="I very like reading.",
                corrected="I like reading very much.",
                explanation="Adverb placement is incorrect.",
            )
        ],
        mistake_tags=["word_order"],
        next_action="Do one word-order micro-drill.",
    )

    items = review_service.build_review_items(feedback, today=today)

    assert len(items) == 1
    assert items[0].mistake_type == "word_order"
    assert items[0].due_date == today + timedelta(days=1)
    assert "I very like reading" in items[0].prompt
