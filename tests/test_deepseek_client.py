import json
from types import SimpleNamespace


class RecordingChatCompletions:
    def __init__(self, content):
        self.content = content
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))]
        )


def make_client(content):
    from app.ai.deepseek_client import DeepSeekStudyClient

    client = object.__new__(DeepSeekStudyClient)
    client.settings = SimpleNamespace(deepseek_model="deepseek-v4-flash")
    client.client = SimpleNamespace(
        chat=SimpleNamespace(completions=RecordingChatCompletions(content))
    )
    return client


def test_generate_drill_uses_deepseek_chat_json_output():
    payload = {
        "skill": "reading",
        "title": "Reading Sprint",
        "minutes": 8,
        "instructions": "Read quickly.",
        "questions": [
            {
                "id": "q1",
                "prompt": "Main idea?",
                "choices": [],
                "answer": "Practice improves accuracy.",
            }
        ],
        "rubric": "Score evidence.",
    }
    client = make_client(json.dumps(payload))

    drill = client.generate_drill("reading", 8, "sample passage")

    call = client.client.chat.completions.calls[0]
    assert drill.title == "Reading Sprint"
    assert call["model"] == "deepseek-v4-flash"
    assert call["response_format"] == {"type": "json_object"}
    assert call["extra_body"] == {"thinking": {"type": "disabled"}}
    assert "untrusted recent real CET-6 exam text" in call["messages"][1]["content"]
    assert "Example JSON" in call["messages"][1]["content"]


def test_default_ai_client_selects_deepseek_provider(monkeypatch):
    import app.main as main

    class StubDeepSeekClient:
        def __init__(self, settings):
            self.settings = settings

    monkeypatch.setenv("AI_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-test-secret")
    monkeypatch.setenv("CET6_USE_FAKE_AI", "0")
    monkeypatch.setattr(main, "DeepSeekStudyClient", StubDeepSeekClient)

    assert isinstance(main._default_ai_client(), StubDeepSeekClient)


def test_grade_attempt_uses_deepseek_chat_json_output():
    from app.schemas import Drill, Question

    payload = {
        "score": 76,
        "summary": "Clear enough.",
        "corrections": [
            {
                "original": "make a progress",
                "corrected": "make progress",
                "explanation": "Progress is uncountable.",
            }
        ],
        "mistake_tags": ["collocation"],
        "next_action": "Review collocations.",
    }
    client = make_client(json.dumps(payload))
    drill = Drill(
        id=1,
        skill="writing",
        title="Writing",
        minutes=8,
        instructions="Write.",
        questions=[Question(id="q1", prompt="Write.", choices=[], answer="")],
        rubric="Rubric.",
    )

    feedback = client.grade_attempt(drill, {"q1": "I make a progress."})

    call = client.client.chat.completions.calls[0]
    assert feedback.score == 76
    assert call["response_format"] == {"type": "json_object"}
    assert call["extra_body"] == {"thinking": {"type": "disabled"}}
    assert "answers" in call["messages"][1]["content"]
    assert "Example JSON" in call["messages"][1]["content"]
