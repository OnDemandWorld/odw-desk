"""
ODW.ai Desk — Configuration Management

Uses pydantic-settings to load and validate environment variables.
All configuration is typed and validated at startup.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = Field(default="ODW.ai Desk", description="Application name")
    app_version: str = Field(default="1.0.0", description="Application version")
    environment: Literal["development", "staging", "production"] = Field(
        default="development", description="Deployment environment"
    )
    debug: bool = Field(default=False, description="Enable debug mode")
    host: str = Field(default="0.0.0.0", description="Application host")
    port: int = Field(default=8000, ge=1, le=65535, description="Application port")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", description="Logging level"
    )

    # CORS (comma-separated string in env, parsed to list)
    cors_origins: str = Field(
        default="http://localhost:3000,http://localhost:8000",
        description="Allowed CORS origins (comma-separated)",
    )

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins from comma-separated string to list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://desk:desk@localhost:5432/desk",
        description="PostgreSQL connection string",
    )
    database_pool_size: int = Field(default=10, ge=1, description="Database connection pool size")
    database_max_overflow: int = Field(
        default=20, ge=0, description="Database max overflow connections"
    )

    # Redis
    redis_url: str = Field(
        default="redis://localhost:6379/0", description="Redis connection string"
    )
    redis_prefix: str = Field(default="desk:", description="Redis key prefix")

    # Security
    secret_key: str = Field(
        default="dev-secret-key-change-me-in-production",
        description="Application secret (JWT signing, encryption)",
        min_length=32,
    )
    deployment_id: str = Field(
        default="dev-local-001", description="Unique deployment identifier"
    )
    desk_api_key: str = Field(
        default="",
        description=(
            "Optional API key guarding /api/v1/admin/* and /api/v1/agents/*. "
            "When empty, those routes stay open (backward compatible / dev)."
        ),
    )
    desk_default_role: Literal["admin", "agent"] = Field(
        default="admin",
        description=(
            "Role assumed by an authenticated principal when none is supplied via "
            "JWT claim or the X-Desk-Role header. Defaults to admin for dev single-user."
        ),
    )

    # Event Bus
    event_bus_backend: Literal["redis_streams", "nats"] = Field(
        default="redis_streams", description="Event bus backend"
    )

    # Vault (Knowledge Base)
    vault_url: str = Field(
        default="http://localhost:8765", description="ODW.ai Vault base URL"
    )
    vault_api_key: str = Field(
        default="vk_dev_local_key", description="Vault API authentication key"
    )
    vault_collection_id: str = Field(
        default="col-dev-001", description="Default knowledge base collection ID"
    )

    # Authentication (OIDC)
    auth_oidc_issuer: str = Field(
        default="http://localhost:8080/realms/odw",
        description="OIDC provider issuer URL",
    )
    auth_oidc_client_id: str = Field(default="desk", description="OIDC client ID")
    auth_oidc_audience: str = Field(default="desk-api", description="OIDC token audience")

    # WhatsApp Business API
    whatsapp_access_token: str = Field(
        default="", description="Meta/BSP WhatsApp access token"
    )
    whatsapp_phone_number_id: str = Field(
        default="", description="WhatsApp phone number ID"
    )
    whatsapp_webhook_verify_token: str = Field(
        default="dev_verify_token", description="WhatsApp webhook verification token"
    )
    whatsapp_app_secret: str = Field(
        default="",
        description=(
            "WhatsApp app secret used to verify inbound webhook HMAC signatures "
            "(X-Hub-Signature-256). When empty, signature verification is skipped (dev only)."
        ),
    )
    whatsapp_graph_api_base_url: str = Field(
        default="https://graph.facebook.com/v19.0",
        description="Meta Graph API base URL for WhatsApp Cloud API (overridable for tests)",
    )
    whatsapp_business_account_id: str = Field(
        default="", description="WhatsApp business account ID"
    )

    # WhatsApp Baileys Bridge
    baileys_bridge_url: str = Field(
        default="http://localhost:3001",
        description="WhatsApp Baileys bridge sidecar URL",
    )
    baileys_enabled: bool = Field(default=True, description="Enable WhatsApp Baileys bridge")

    # Local Model (Ollama/vLLM)
    ollama_endpoint: str = Field(
        default="http://localhost:11434", description="Ollama/vLLM endpoint URL"
    )
    local_model_name: str = Field(
        default="llama-3.1-8b", description="Local model identifier"
    )
    local_model_enabled: bool = Field(default=True, description="Enable local model inference")

    # Frontier Model (OpenAI/Anthropic)
    frontier_provider: Literal["openai", "anthropic", "none"] = Field(
        default="none", description="Frontier model provider"
    )
    frontier_api_key: str = Field(default="", description="Frontier model API key")
    frontier_model_name: str = Field(
        default="gpt-4o-mini", description="Frontier model identifier"
    )
    frontier_enabled: bool = Field(default=False, description="Enable frontier model inference")

    # AI Configuration
    confidence_threshold: float = Field(
        default=0.6, ge=0.0, le=1.0, description="Default AI confidence threshold"
    )
    pii_shield_enabled: bool = Field(default=True, description="Enable PII detection and redaction")
    pii_frontier_allowed_with_redaction: bool = Field(
        default=False,
        description="Allow frontier models when PII is detected (with redaction)",
    )

    # SLA Configuration
    sla_first_response_minutes: int = Field(
        default=10, ge=1, description="SLA for first response (minutes)"
    )
    sla_resolution_hours: int = Field(
        default=48, ge=1, description="SLA for resolution (hours)"
    )
    sla_scan_interval_seconds: int = Field(
        default=60, ge=5, description="SLA scanner interval (seconds)"
    )

    # Data Retention
    data_retention_days: int = Field(
        default=365, ge=1, description="Conversation data retention period (days)"
    )

    # Compliance (V1.4)
    compliance_cross_product_erasure: bool = Field(
        default=True,
        description=(
            "When deleting a customer, also best-effort erase their associated "
            "Vault knowledge files (recorded as vault_file_ids in conversation "
            "metadata). Vault failures never block the local deletion."
        ),
    )

    # Web-chat (V1.4)
    webchat_rate_limit_per_min: int = Field(
        default=30,
        ge=1,
        description="Max inbound web-chat messages per visitor per minute (sliding window).",
    )

    # Observability — distributed tracing spans (V1.6 F-2)
    # Best-effort span model layered on the V1.5 trace_id propagation. Defaults
    # are backward compatible: sample everything, export to the console, no OTLP.
    trace_sample_rate: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Fraction of traces sampled for span export (1.0 = all, 0.0 = none).",
    )
    trace_exporter: Literal["console", "otlp", "none"] = Field(
        default="console",
        description="Span exporter: console (structlog), otlp (best-effort HTTP), or none.",
    )
    otlp_endpoint: str = Field(
        default="",
        description="OTLP HTTP endpoint spans are POSTed to when trace_exporter=otlp.",
    )

    # Email channel (V1.5 F-2)
    # Disabled by default so development never requires a live SMTP server;
    # outbound replies are stubbed until enabled + a host is configured.
    email_enabled: bool = Field(
        default=False,
        description="Enable the Email channel (outbound SMTP). Default False (dev stub).",
    )
    email_smtp_host: str = Field(default="", description="Outbound SMTP server host")
    email_smtp_port: int = Field(default=587, ge=1, le=65535, description="Outbound SMTP port")
    email_smtp_user: str = Field(default="", description="SMTP authentication username")
    email_smtp_password: str = Field(default="", description="SMTP authentication password")
    email_use_tls: bool = Field(
        default=True, description="Use STARTTLS when connecting to the SMTP server"
    )
    email_from: str = Field(
        default="", description="Sender address used on outbound Email replies"
    )

    # License
    license_key: str = Field(default="free", description="Desk license key")
    license_grace_period_days: int = Field(
        default=7, ge=0, description="License grace period (days)"
    )

    # S3-Compatible Object Storage
    s3_endpoint: str = Field(
        default="http://localhost:9000", description="S3-compatible endpoint URL"
    )
    s3_access_key: str = Field(default="minioadmin", description="S3 access key")
    s3_secret_key: str = Field(default="minioadmin", description="S3 secret key")
    s3_bucket: str = Field(default="desk-dev", description="S3 bucket name")
    s3_region: str = Field(default="us-east-1", description="S3 region")
    s3_use_ssl: bool = Field(default=False, description="Use SSL for S3 connections")


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


if __name__ == "__main__":
    # Test configuration loading
    settings = get_settings()
    print(f"App: {settings.app_name} v{settings.app_version}")
    print(f"Environment: {settings.environment}")
    print(f"Database: {settings.database_url}")
    print(f"Redis: {settings.redis_url}")
    print(f"Vault: {settings.vault_url}")
    print(f"Local Model: {settings.local_model_name} @ {settings.ollama_endpoint}")
    print(f"Frontier: {settings.frontier_provider} ({settings.frontier_model_name})")
