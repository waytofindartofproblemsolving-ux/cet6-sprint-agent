import importlib

import pytest


def import_required(module_name: str):
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        pytest.fail(f"Expected module {module_name} to exist: {exc}")


def test_missing_openai_api_key_raises_setup_error(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    config = import_required("app.config")

    with pytest.raises(config.ConfigurationError, match="OPENAI_API_KEY"):
        config.get_settings()


def test_settings_reads_api_key_without_printing_secret(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    config = import_required("app.config")

    settings = config.get_settings()

    assert settings.openai_api_key == "sk-test-secret"
    assert settings.openai_model == "test-model"
    assert "sk-test-secret" not in repr(settings)


def test_settings_supports_deepseek_provider_with_deepseek_key(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-test-secret")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)
    config = import_required("app.config")

    settings = config.get_settings()

    assert settings.ai_provider == "deepseek"
    assert settings.deepseek_api_key == "ds-test-secret"
    assert settings.deepseek_model == "deepseek-v4-flash"
    assert settings.deepseek_base_url == "https://api.deepseek.com"
    assert "ds-test-secret" not in repr(settings)


def test_deepseek_provider_can_reuse_openai_api_key_env(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "deepseek")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "ds-in-openai-slot")
    config = import_required("app.config")

    settings = config.get_settings()

    assert settings.deepseek_api_key == "ds-in-openai-slot"
