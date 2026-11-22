from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./openintel.db"
    jwt_secret: str = "change-me"
    ip_hash_salt: str = "change-me-too"
    trust_proxy_headers: bool = False  # only true behind a proxy you control

    # LLM: any OpenAI-compatible endpoint. Default = local Ollama.
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = "ollama"
    llm_model: str = "llama3.1:8b"

    searxng_url: str = "http://localhost:8080"
    # optional keyed search providers (most reliable); leave empty to use DuckDuckGo/SearXNG
    brave_api_key: str = ""
    serper_api_key: str = ""

    # quotas per rolling window; 0 = unlimited (default for a private self-hosted instance)
    guest_limit: int = 0     # per IP, anonymous visitors
    user_limit: int = 0      # per account
    quota_window_days: int = 30

    # research budgets
    max_queries: int = 6
    max_urls: int = 30
    max_pages: int = 12
    max_chars_per_source: int = 30000
    chunk_chars: int = 3500      # text per model call
    max_chunks: int = 24         # total model calls for extraction per job
    job_timeout_s: int = 1200

    frontend_url: str = "http://localhost:5173"


settings = Settings()
