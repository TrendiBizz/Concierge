from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://postgres:postgres@localhost:5432/concierge"
    admin_token: str = ""
    public_base_url: str = "http://localhost:8000"

    # Text chat: any OpenAI-compatible endpoint. Defaults to xAI (Grok).
    xai_api_key: str = ""
    llm_base_url: str = "https://api.x.ai/v1"
    llm_api_key: str = ""
    chat_model: str = "grok-4"

    # Grok Voice Agent API
    xai_client_secrets_url: str = "https://api.x.ai/v1/realtime/client_secrets"
    xai_realtime_url: str = "wss://api.x.ai/v1/realtime"
    voice_model: str = ""  # blank = API default; e.g. "grok-voice-3.0"
    voice_default: str = "eve"
    voice_token_ttl_seconds: int = 300

    # Local embeddings (fastembed, free, runs on CPU)
    embed_model: str = "BAAI/bge-small-en-v1.5"
    embed_dim: int = 384

    # Abuse limits
    chat_rate_per_minute_ip: int = 20
    chat_rate_per_day_session: int = 200

    @property
    def effective_llm_key(self) -> str:
        return self.llm_api_key or self.xai_api_key

    @property
    def voice_ws_url(self) -> str:
        if self.voice_model:
            sep = "&" if "?" in self.xai_realtime_url else "?"
            return f"{self.xai_realtime_url}{sep}model={self.voice_model}"
        return self.xai_realtime_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
