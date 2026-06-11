def test_drill_response_format_uses_strict_model_output_schema():
    from app.ai.openai_client import drill_response_format

    schema_format = drill_response_format()
    schema = schema_format["format"]["schema"]

    assert schema_format["format"]["strict"] is True
    assert "id" not in schema["properties"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {
        "skill",
        "title",
        "minutes",
        "instructions",
        "questions",
        "rubric",
    }
    assert schema["properties"]["questions"]["items"]["additionalProperties"] is False


def test_feedback_response_format_uses_strict_model_output_schema():
    from app.ai.openai_client import feedback_response_format

    schema_format = feedback_response_format()
    schema = schema_format["format"]["schema"]

    assert schema_format["format"]["strict"] is True
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {
        "score",
        "summary",
        "corrections",
        "mistake_tags",
        "next_action",
    }
    assert schema["properties"]["corrections"]["items"]["additionalProperties"] is False
