from dataclasses import dataclass
import os


class ConfigurationError(RuntimeError):
    """Raised when required local configuration is missing."""


@dataclass(frozen=True)
class Settings:
    ai_provider: str = "openai"
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.5"
    deepseek_api_key: str | None = None
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_base_url: str = "https://api.deepseek.com"

    def __repr__(self) -> str:
        return (
            "Settings("
            f"ai_provider={self.ai_provider!r}, "
            "openai_api_key='***', "
            f"openai_model={self.openai_model!r}, "
            "deepseek_api_key='***', "
            f"deepseek_model={self.deepseek_model!r}, "
            f"deepseek_base_url={self.deepseek_base_url!r}"
            ")"
        )


def get_settings() -> Settings:
    provider = os.getenv("AI_PROVIDER", "openai").strip().lower() or "openai"
    openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
    openai_model = os.getenv("OPENAI_MODEL", "gpt-5.5").strip() or "gpt-5.5"

    if provider == "openai":
        if not openai_api_key:
            raise ConfigurationError(
                "OPENAI_API_KEY is required. Set it in your shell before using live AI."
            )
        return Settings(
            ai_provider=provider,
            openai_api_key=openai_api_key,
            openai_model=openai_model,
        )

    if provider == "deepseek":
        deepseek_api_key = os.getenv("DEEPSEEK_API_KEY", "").strip() or openai_api_key
        if not deepseek_api_key:
            raise ConfigurationError(
                "DEEPSEEK_API_KEY or OPENAI_API_KEY is required when AI_PROVIDER=deepseek."
            )
        return Settings(
            ai_provider=provider,
            openai_api_key=openai_api_key or None,
            openai_model=openai_model,
            deepseek_api_key=deepseek_api_key,
            deepseek_model=(
                os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash").strip()
                or "deepseek-v4-flash"
            ),
            deepseek_base_url=(
                os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip()
                or "https://api.deepseek.com"
            ),
        )

    raise ConfigurationError(
        "AI_PROVIDER must be 'openai' or 'deepseek'."
    )
