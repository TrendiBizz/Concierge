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

    # PSTN telephone receptionist: opt-in and off until a real provider is validated.
    phone_receptionist_enabled: bool = False

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

    # SMS. Optional: without a configured provider, SMS messages are skipped, not failed.
    # SMS_PROVIDER = twilio | smsgate | none
    sms_provider: str = "twilio"
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    twilio_messaging_service_sid: str = ""  # use for a short code or a sender pool
    twilio_api_base: str = "https://api.twilio.com"
    # Self-hosted Android gateway (capcom6/android-sms-gateway). The phone's SIM is the sender.
    smsgate_base_url: str = ""          # e.g. https://sms.example.com (your private server)
    smsgate_send_path: str = "/3rdparty/v1/messages"  # docs show /message and /messages: check yours
    smsgate_username: str = ""
    smsgate_password: str = ""
    smsgate_signing_key: str = ""       # from the app: Settings > Webhooks > Signing Key
    smsgate_sim_number: int = 0         # 0 = the app's own SIM rotation; 1-3 pins a SIM
    default_country_code: str = "1"  # used to turn 10-digit numbers into E.164

    # Email (any SMTP server). Optional.
    email_drafts_enabled: bool = False  # staging-only until explicitly enabled
    inbound_cloudflare_enabled: bool = False  # no public ingestion until authorized
    inbound_cloudflare_secret: str = ""  # same randomly generated secret in Worker and API
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_security: str = "starttls"  # starttls | ssl | none

    # Reactivation campaigns
    unsubscribe_secret: str = ""      # signs unsubscribe links; falls back to ADMIN_TOKEN
    campaign_max_recipients: int = 200
    campaign_cooldown_days: int = 30    # nobody is messaged by two campaigns inside this window
    campaign_email_per_hour: int = 60
    campaign_sms_per_hour: int = 20     # keep low: a phone-SIM gateway is not built for bulk

    # Response-time alerts
    sla_poll_seconds: int = 60
    digest_poll_seconds: int = 300

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
        name = (self.sms_provider or "none").strip().lower()
        if name == "twilio":
            return bool(self.twilio_account_sid and self.twilio_auth_token
                        and (self.twilio_from_number or self.twilio_messaging_service_sid))
        if name == "smsgate":
            return bool(self.smsgate_base_url and self.smsgate_username and self.smsgate_password)
        return False

    @property
    def email_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_from)


@lru_cache
def get_settings() -> Settings:
    return Settings()
