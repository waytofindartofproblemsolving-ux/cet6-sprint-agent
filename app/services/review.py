from datetime import date, timedelta

from app.schemas import Feedback, ReviewItem


def build_review_items(feedback: Feedback, today: date | None = None) -> list[ReviewItem]:
    base_date = today or date.today()
    due_date = base_date + timedelta(days=1)
    tags = feedback.mistake_tags or ["general"]
    correction = feedback.corrections[0] if feedback.corrections else None

    if correction is None:
        return [
            ReviewItem(
                mistake_type=tags[0],
                prompt=f"Review this feedback: {feedback.summary}",
                user_answer="",
                corrected_answer=feedback.next_action,
                due_date=due_date,
            )
        ]

    return [
        ReviewItem(
            mistake_type=tags[0],
            prompt=f"Fix this CET-6 mistake: {correction.original}",
            user_answer=correction.original,
            corrected_answer=correction.corrected,
            due_date=due_date,
        )
    ]
