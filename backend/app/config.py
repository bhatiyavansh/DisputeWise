from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    postgres_user: str = "disputewise"
    postgres_password: str = "disputewise"
    postgres_db: str = "disputewise"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    api_default_page_size: int = 25
    api_max_page_size: int = 200

    # Gates the OpenRouter provider's diagnostic response logging (see
    # OpenRouterLLMProvider._log_diagnostics). Defaults to "development"
    # since this is a demo app with no separate prod deployment configured
    # yet; set ENVIRONMENT=production to silence it.
    environment: str = "development"

    # Phase 4 -- optional. The app must run fully (evidence gap analysis, RAG
    # retrieval, all non-generation endpoints, and the entire test suite)
    # with all of this unset. Never hardcode a key here or anywhere else.
    #
    # llm_provider selects which LLMProvider get_llm_provider() constructs
    # (see app/evidence_intel/llm_provider.py). "openrouter" is the buildathon
    # demo default -- a genuinely free, verified-tool-calling-capable model
    # (see docs/phase4.md's "OpenRouter setup" section for how it was chosen
    # and verified against OpenRouter's live /api/v1/models endpoint).
    # "anthropic" remains supported so the architecture stays provider-agnostic,
    # but is NOT used for the demo per product decision.
    llm_provider: str = "openrouter"
    llm_model: str = "nvidia/nemotron-3-super-120b-a12b:free"

    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    anthropic_api_key: str | None = None

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
