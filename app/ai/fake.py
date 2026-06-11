from app.schemas import Correction, Drill, Feedback, Question


class FakeAIClient:
    def generate_drill(
        self,
        skill: str,
        minutes: int,
        material_text: str | None = None,
    ) -> Drill:
        prompt = "Use the selected recent real CET-6 exam material for this drill."
        if skill == "reading":
            prompt = "What is the main idea of the passage?"
        if material_text:
            prompt = f"Use this recent real exam material and answer one focused question: {material_text[:120]}"

        return Drill(
            skill=skill,
            title=f"{skill.title()} Sprint",
            minutes=minutes,
            instructions="Work under time pressure, then review the correction.",
            questions=[
                Question(
                    id="q1",
                    prompt=prompt,
                    choices=[],
                    answer="A focused answer with accurate grammar.",
                )
            ],
            rubric="Score clarity, accuracy, vocabulary, and CET-6 relevance.",
        )

    def grade_attempt(self, drill: Drill, answers: dict[str, str]) -> Feedback:
        first_answer = next(iter(answers.values()), "")
        original = first_answer or "No answer"
        corrected = original.strip() or "Add a complete answer."
        if corrected == original:
            corrected = f"{corrected} This needs a more precise CET-6 expression."

        return Feedback(
            score=68 if first_answer else 20,
            summary="Your answer is understandable, but needs more precise wording.",
            corrections=[
                Correction(
                    original=original,
                    corrected=corrected,
                    explanation="Use more exact collocations and complete sentence structure.",
                )
            ],
            mistake_tags=["collocation"],
            next_action="Spend 8 minutes rewriting the corrected sentence twice.",
        )
