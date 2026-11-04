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

    # SMS (Twilio). Optional: without these, SMS messages are skipped, not failed.
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    twilio_api_base: str = "https://api.twilio.com"
    default_country_code: str = "1"  # used to turn 10-digit numbers into E.164

    # Email (any SMTP server). Optional.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_security: str = "starttls"  # starttls | ssl | none

    # Follow-up engine
    outbox_enabled: bool = True
    outbox_poll_seconds: int = 20
    sms_quiet_start_hour: int = 8   # no texts before 08:00 local
    sms_quiet_end_hour: int = 21    # ...or from 21:00 local

    @property
    def effective_llm_key(self) -> str:
        return self.llm_api_key or self.xai_api_key

    @property
    def voice_ws_url(self) -> str:
        if self.voice_model:
            sep = "&" if "?" in self.xai_realtime_url else "?"
            return f"{self.xai_realtime_url}{sep}model={self.voice_model}"
        return self.xai_realtime_url

    @property
    def sms_configured(self) -> bool:
        return bool(self.twilio_account_sid and self.twilio_auth_token and self.twilio_from_number)

    @property
    def email_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_from)


@lru_cache
def get_settings() -> Settings:
    return Settings()
