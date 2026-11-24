from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from urllib.parse import urlsplit


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://postgres:postgres@localhost:5432/concierge"
    admin_token: str = ""
    # N9: AES-256-GCM key material for encrypting OAuth tokens, webhook secrets & TOTP seeds at rest.
    # Leave unset to derive from ADMIN_TOKEN; set a dedicated 32+ char random secret in production.
    token_encryption_key: str = ""
    public_base_url: str = "http://localhost:8000"
    owner_portal_url: str = "https://concierge.trendibizz.com/owner-ui"
    onboarding_url: str = "https://concierge.trendibizz.com/studio"
    # Public origin that email links are rewritten through so a click can be recorded. Blank keeps
    # every email plain text with its original links — tracking is an operator decision, not a default.
    tracked_links_base: str = ""

    @field_validator("tracked_links_base")
    @classmethod
    def valid_tracking_origin(cls, value: str) -> str:
        value = (value or "").strip().rstrip("/")
        if not value:
            return ""
        url = urlsplit(value)
        if url.scheme != "https" or not url.hostname or url.path not in ("", "/") or url.query:
            raise ValueError("Tracked links base must be a bare HTTPS origin, e.g. https://concierge.trendibizz.com")
        return value

    @field_validator("owner_portal_url")
    @classmethod
    def valid_owner_portal(cls, value: str) -> str:
        url = urlsplit(value)
        local_http = url.scheme == "http" and url.hostname in ("127.0.0.1", "localhost", "::1")
        if ((url.scheme != "https" and not local_http) or not url.hostname or url.username or url.password
                or url.query or url.fragment or url.path != "/owner-ui"):
            raise ValueError("Owner portal must be an HTTPS /owner-ui URL (HTTP is allowed only on loopback) without credentials or parameters")
        return value

    # Unified Concierge social publishing module (built into the API; reads existing SOCIAL_* env names).
    social_service_enabled: bool = False
    social_enabled: bool = False
    social_service_url: str = "http://127.0.0.1:4390"  # deprecated legacy setting; kept for backward compatibility
    social_concierge_key: str = ""                     # deprecated legacy setting; kept for backward compatibility
    social_live_publishing: bool = False
    social_enable_publish: bool = False
    social_enable_facebook_publish: bool = False
    social_enable_instagram_publish: bool = False
    social_enable_linkedin_publish: bool = False
    social_enable_linkedin_organization_publish: bool = False
    social_enable_x_publish: bool = False
    social_enable_tiktok_publish: bool = False
    social_enable_google_business_publish: bool = False
    social_facebook_client_id: str = ""
    social_facebook_client_secret: str = ""
    social_facebook_callback: str = ""
    social_facebook_page_hints: str = ""
    social_instagram_login_mode: str = "facebook"
    social_instagram_client_id: str = ""
    social_instagram_client_secret: str = ""
    social_instagram_callback: str = ""
    social_linkedin_client_id: str = ""
    social_linkedin_client_secret: str = ""
    social_linkedin_callback: str = ""
    social_linkedin_organization_client_id: str = ""
    social_linkedin_organization_client_secret: str = ""
    social_linkedin_organization_callback: str = ""
    social_x_client_id: str = ""
    social_x_client_secret: str = ""
    social_x_callback: str = ""
    social_tiktok_client_key: str = ""
    social_tiktok_client_secret: str = ""
    social_tiktok_callback: str = ""
    social_tiktok_enable_video_scope: bool = False
    social_tiktok_verified_media_origins: str = ""
    social_google_client_id: str = ""
    social_google_client_secret: str = ""
    social_google_callback: str = ""
    social_meta_graph_version: str = "v22.0"
    social_linkedin_api_version: str = "202605"
    social_media_dir: str = ""
    social_poll_seconds: int = 15

    # "claude" asks the Max-plan CLI for one plan per new case. Empty skips the call.
    case_planner: str = ""

    calendar_credentials_dir: str = ""  # mounted private secret directory, not source control

    # Text chat: any OpenAI-compatible endpoint. Defaults to Google Gemini (OpenAI-compatible).
    llm_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    llm_api_key: str = ""
    chat_model: str = "gemini-3.8-flash"
    # N3: resilience. Any OpenAI-compatible provider that supports tool calls can be the secondary
    # (leave the key empty to keep failover off). Never hard-code a vendor or a key here.
    llm_fallback_base_url: str = ""
    llm_fallback_api_key: str = ""
    llm_fallback_model: str = ""
    llm_timeout_seconds: float = 45.0
    llm_retry_attempts: int = 2          # extra tries on the primary before giving up on it
    llm_breaker_threshold: int = 4       # consecutive failed requests that open the breaker
    llm_breaker_cooldown_seconds: float = 60.0
    # N3: directory where the PBX drops voicemail WAVs when the AI voice link is down. Empty = off.
    voicemail_spool_dir: str = ""

    # PSTN telephone receptionist: opt-in and off until a real provider is validated.
    phone_receptionist_enabled: bool = False
    voice_recording_enabled: bool = False  # web audio: business opt-in plus caller choice
    phone_recording_enabled: bool = False  # separate paid-provider + legal approval
    phone_voice_provider: Literal['gemini_live', 'legacy_twilio_tts'] = 'gemini_live'
    # Google Gemini 3.8 Live API (website voice + telephone voice bridge)
    gemini_api_key: str = ""
    gemini_live_model: str = "models/gemini-3.8-live"
    gemini_live_ws_url: str = "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
    gemini_auth_tokens_url: str = "https://generativelanguage.googleapis.com/v1alpha/auth_tokens"
    gemini_constrained_ws_url: str = "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContentConstrained"
    gemini_live_voice: str = "Aoede"
    # Blank by default: models/gemini-3.8-live rejects thinkingConfig.thinkingLevel with WS 1007.
    # Set explicitly (e.g. "low") only for thinking-capable models like models/gemini-3.8-live-extended-thinking.
    gemini_thinking_level: str = ""
    phone_verified_tenants: str = ""  # populated only after a genuine carrier call test
    # Asterisk Manager Interface — the control plane for take-over/listen-in/whisper.
    # Blank host or secret keeps every media-server action disabled.
    ami_host: str = ""          # e.g. "pbx" (private container network, never published)
    ami_port: int = 5038
    ami_user: str = ""
    ami_secret: str = ""
    # Outbound pattern for a supervisor leg / take-over through the carrier trunk.
    # <number> is replaced with the dialled party.
    asterisk_channel_dial: str = "PJSIP/<number>@concierge-reg"

    # Operator records tenant slugs only after live website chat + voice checks.
    website_verified_tenants: str = ""
    voice_default: str = "Aoede"
    voice_token_ttl_seconds: int = 300

    # Local embeddings (fastembed, free, runs on CPU)
    embed_model: str = "BAAI/bge-small-en-v1.5"
    embed_dim: int = 384

    # Abuse limits
    chat_rate_per_minute_ip: int = 20
    chat_rate_per_day_session: int = 200

    # SMS. Optional: without a configured provider, SMS messages are skipped, not failed.
    # SMS_PROVIDER = smsgate | none
    sms_provider: str = "smsgate"
    # Optional Twilio voice relay/recording credentials (not used for SMS).
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
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
    inbound_cloudflare_enabled: bool = False
    email_auth_url: str = ""
    internal_token: str = ""  # loopback-only voice shell API
    media_dir: str = "/data/media"
    media_image_limit: int = 100
    media_video_limit: int = 40
    media_ai_limit: int = 50
    media_storage_limit_bytes: int = 2 * 1024 * 1024 * 1024
    reply_domain: str = "trendibizz.com"
    cloudflare_account_id: str = ""
    cloudflare_api_token: str = ""  # scoped API token (Bearer); the global key is retired
    cloudflare_zone_id: str = ""
    cloudflare_worker_name: str = "concierge-inbound-worker"
    rspamd_url: str = ""
    clamav_host: str = ""
    clamav_port: int = 3310  # no public ingestion until authorized
    inbound_cloudflare_secret: str = ""  # same randomly generated secret in Worker and API
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    vapid_public_key: str = ""    # Web Push for owner alerts (installed portal)
    vapid_private_key: str = ""
    vapid_subject: str = "mailto:admin@trendibizz.com"
    smtp_security: str = "starttls"  # starttls | ssl | none
    # Brevo webhook shared secret. Unset means the bounce webhook is closed (503), so an
    # unauthenticated caller can never suppress a customer's address.
    brevo_webhook_secret: str = ""

    # Reactivation campaigns
    # Stripe signs its webhooks with this; without it no purchase can be trusted as paid.
    stripe_webhook_secret: str = ""
    # Needed only for the self-serve Stripe Customer Portal (Studio > Billing). Unset = portal link hidden.
    stripe_secret_key: str = ""
    stripe_portal_return_url: str = "https://concierge.trendibizz.com/studio/"
    # N8: Tenant online payments via Stripe Connect Standard (disabled until configured).
    stripe_connect_client_id: str = ""
    stripe_connect_webhook_secret: str = ""
    # Days a declined card keeps working before the business is paused.
    billing_grace_days: int = 7
    # N6 integrations. Every provider ships disabled: with no credentials the Connect button is
    # hidden and nothing is called. Register an app with the provider, then set these.
    xero_client_id: str = ""
    xero_client_secret: str = ""
    ms_client_id: str = ""            # Microsoft 365 / Outlook Calendar (Entra app registration)
    ms_client_secret: str = ""
    ms_tenant: str = "common"
    # ServiceM8 uses customer API keys; Xero and Microsoft 365 use OAuth.
    # N10 remainder: Gmail send-as OAuth (disabled until credentials are supplied).
    gmail_oauth_client_id: str = ""
    gmail_oauth_client_secret: str = ""
    # N7: Meta WhatsApp / FB Messenger / IG DM messaging (disabled until Meta app approval).
    meta_messaging_enabled: bool = False
    meta_app_id: str = ""
    meta_app_secret: str = ""
    meta_webhook_verify_token: str = ""
    meta_graph_version: str = "v22.0"
    # Dedicated WhatsApp Meta app ("Trendi Messaging"); falls back to main Meta app when unset.
    meta_wa_app_id: str = ""
    meta_wa_app_secret: str = ""
    meta_wa_embedded_signup_config_id: str = ""
    # Tier 2 (H2/H10): disabled by default until explicitly enabled.
    gbp_reviews_enabled: bool = False
    outbound_ai_calls_enabled: bool = False
    unsubscribe_secret: str = ""      # signs unsubscribe links; falls back to ADMIN_TOKEN
    campaign_max_recipients: int = 200
    campaign_cooldown_days: int = 30    # nobody is messaged by two campaigns inside this window
    campaign_email_per_hour: int = 60
    campaign_sms_per_hour: int = 20     # keep low: a phone-SIM gateway is not built for bulk

    # One owner alert per enquiry: later turns of a conversation join the alert while it waits to go out.
    # A thread quiet for this many hours that writes again is a NEW enquiry and gets its own alert.
    owner_alert_reopen_hours: int = 24
    # Owner is told ("ACTION NEEDED") when a genuine enquiry has had no reply this long. A tenant's own
    # sla_minutes overrides it. 0 = off.
    owner_issue_unanswered_minutes: int = 120
    # A new owner alert waits this long so the rest of a quick conversation joins it (0 = send at once).
    owner_alert_debounce_seconds: int = 45

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
        return self.llm_api_key or self.gemini_api_key

    @property
    def gemini_ws_url(self) -> str:
        if self.gemini_api_key:
            sep = "&" if "?" in self.gemini_live_ws_url else "?"
            return f"{self.gemini_live_ws_url}{sep}key={self.gemini_api_key}"
        return self.gemini_live_ws_url

    @property
    def gemini_auth_tokens_endpoint(self) -> str:
        if self.gemini_api_key:
            sep = "&" if "?" in self.gemini_auth_tokens_url else "?"
            return f"{self.gemini_auth_tokens_url}{sep}key={self.gemini_api_key}"
        return self.gemini_auth_tokens_url

    @property
    def sms_configured(self) -> bool:
        name = (self.sms_provider or "none").strip().lower()
        if name == "smsgate":
            return bool(self.smsgate_base_url and self.smsgate_username and self.smsgate_password)
        return False

    @property
    def email_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_from)


@lru_cache
def get_settings() -> Settings:
    return Settings()
