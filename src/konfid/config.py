from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _read_secret(value: str | None, path: str | None) -> str | None:
    if path:
        p = Path(path)
        if p.stat().st_size > 65_536:
            raise ValueError(f"secret file is too large: {path}")
        data = p.read_text(encoding="utf-8").strip()
        if not data:
            raise ValueError(f"secret file is empty: {path}")
        if len(data.encode("utf-8")) > 16_384 or "\x00" in data:
            raise ValueError(f"secret value is invalid: {path}")
        return data
    if value is not None and (len(value.encode("utf-8")) > 16_384 or "\x00" in value):
        raise ValueError("secret value is invalid")
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="KONFID_", env_file=".env", extra="ignore", case_sensitive=False
    )

    env: str = "development"
    dev_mode: bool = True
    version: str = "0.3.0"
    instance_id: str = "local"

    # HTTP/API hardening
    trusted_hosts: list[str] = Field(default_factory=lambda: ["localhost", "127.0.0.1", "testserver"])
    cors_origins: list[str] = Field(default_factory=list)
    max_request_body_bytes: int = 1_048_576
    docs_enabled: bool = True
    hsts_seconds: int = 31_536_000
    metrics_enabled: bool = True
    metrics_token: str | None = None
    metrics_token_file: str | None = None

    # Database
    database_url: str = "sqlite:///./konfid.db"
    database_pool_size: int = 10
    database_max_overflow: int = 20
    database_pool_timeout_seconds: int = 10
    database_pool_recycle_seconds: int = 900
    database_statement_timeout_ms: int = 5_000
    database_lock_timeout_ms: int = 2_000
    database_idle_in_transaction_timeout_ms: int = 10_000
    require_schema_head: bool = False

    # Development-only signing
    dev_signing_secret: str = "dev-only-change-this-secret-1234567890"

    # Workload identity
    workload_issuer: str = "konfid-dev"
    workload_audience: str = "konfid-api"
    workload_jwks_url: str | None = None
    workload_algorithms: list[str] = Field(default_factory=lambda: ["RS256", "ES256", "EdDSA"])
    workload_max_token_ttl_seconds: int = 900

    # Human actor assertion
    actor_issuer: str = "konfid-identity-dev"
    actor_audience: str = "konfid-actor"
    actor_jwks_url: str | None = None
    actor_algorithms: list[str] = Field(default_factory=lambda: ["RS256", "ES256", "EdDSA"])
    actor_max_token_ttl_seconds: int = 600
    jwt_clock_skew_seconds: int = 30
    require_actor_assertion: bool = False
    require_actor_authorized_party: bool = False

    # Policy / integrations
    policy_mode: str = "local"
    koa_policy_url: str | None = None
    koa_policy_bearer_token: str | None = None
    koa_policy_bearer_token_file: str | None = None
    koa_audit_url: str | None = None
    koa_audit_bearer_token: str | None = None
    koa_audit_bearer_token_file: str | None = None
    interaction_kernel_url: str | None = None
    interaction_kernel_bearer_token: str | None = None
    interaction_kernel_bearer_token_file: str | None = None
    orgo_url: str | None = None
    orgo_bearer_token: str | None = None
    orgo_bearer_token_file: str | None = None
    orgo_organization_id: str | None = None
    orgo_case_label: str = "1.11.Konfid"

    # Outbound transport
    http_connect_timeout_seconds: float = 2.0
    http_read_timeout_seconds: float = 5.0
    http_write_timeout_seconds: float = 5.0
    http_pool_timeout_seconds: float = 2.0
    http_max_response_bytes: int = 2_097_152
    http_retry_attempts: int = 3
    http_retry_base_seconds: float = 0.1
    http_circuit_failure_threshold: int = 5
    http_circuit_reset_seconds: int = 30
    outbound_ca_bundle: str | None = None
    outbound_client_cert_file: str | None = None
    outbound_client_key_file: str | None = None

    # Abuse controls
    rate_limit_enabled: bool = True
    rate_limit_default_per_minute: int = 600
    rate_limit_admin_per_minute: int = 120
    rate_limit_response_per_minute: int = 60
    rate_limit_access_per_minute: int = 3_000
    rate_limit_telemetry_per_minute: int = 10_000

    # Security workflow
    default_approval_ttl_seconds: int = 900
    risk_signal_ttl_seconds: int = 900
    response_action_ttl_seconds: int = 1_800
    outbox_max_attempts: int = 12
    outbox_lease_seconds: int = 60
    audit_export_lease_seconds: int = 60
    audit_export_batch_size: int = 100
    worker_batch_size: int = 50
    worker_interval_seconds: float = 1.0
    inline_enforcement_dev_only: bool = False

    @property
    def metrics_secret(self) -> str | None:
        return _read_secret(self.metrics_token, self.metrics_token_file)

    def integration_secret(self, name: str) -> str | None:
        return _read_secret(
            getattr(self, f"{name}_bearer_token", None),
            getattr(self, f"{name}_bearer_token_file", None),
        )

    @model_validator(mode="after")
    def secure_config(self):
        if self.max_request_body_bytes < 16_384:
            raise ValueError("max_request_body_bytes is unreasonably small")
        if self.database_statement_timeout_ms < 500:
            raise ValueError("database_statement_timeout_ms must be >= 500")
        if self.database_lock_timeout_ms < 100 or self.database_lock_timeout_ms > self.database_statement_timeout_ms:
            raise ValueError("database_lock_timeout_ms must be between 100 and statement timeout")
        if self.database_idle_in_transaction_timeout_ms < 1_000:
            raise ValueError("database_idle_in_transaction_timeout_ms must be >= 1000")
        if self.outbound_client_cert_file and not self.outbound_client_key_file:
            raise ValueError("outbound_client_key_file is required with outbound_client_cert_file")

        if not self.dev_mode:
            self.docs_enabled = False
            self.require_schema_head = True
            if not self.database_url.startswith(("postgresql://", "postgresql+psycopg://")):
                raise ValueError("production requires PostgreSQL")
            db_url = urlparse(self.database_url)
            db_query = parse_qs(db_url.query)
            if db_query.get("sslmode", [None])[-1] != "verify-full":
                raise ValueError("production PostgreSQL requires sslmode=verify-full")
            if not self.workload_jwks_url:
                raise ValueError("production requires workload_jwks_url")
            if not self.actor_jwks_url:
                raise ValueError("production requires actor_jwks_url")
            if not self.require_actor_assertion:
                raise ValueError("production requires actor assertions")
            if not self.require_actor_authorized_party:
                raise ValueError("production requires actor authorized-party binding")
            if self.policy_mode != "koa":
                raise ValueError("production requires policy_mode=koa")
            if not self.koa_policy_url:
                raise ValueError("production requires koa_policy_url")
            if not self.koa_audit_url:
                raise ValueError("production requires koa_audit_url")
            if not self.interaction_kernel_url:
                raise ValueError("production requires interaction_kernel_url")
            if not self.rate_limit_enabled:
                raise ValueError("production requires rate limiting")
            if self.metrics_enabled and not (self.metrics_token or self.metrics_token_file):
                raise ValueError("production metrics require an authentication token or must be disabled")
            if "*" in self.trusted_hosts:
                raise ValueError("production trusted_hosts may not contain wildcard *")
            if self.env.lower() in {"development", "dev", "test", "testing"}:
                raise ValueError("production requires a non-development KONFID_ENV")
            if self.jwt_clock_skew_seconds < 0 or self.jwt_clock_skew_seconds > 120:
                raise ValueError("jwt_clock_skew_seconds must be between 0 and 120 in production")
            if not (60 <= self.workload_max_token_ttl_seconds <= 3600):
                raise ValueError("workload_max_token_ttl_seconds must be between 60 and 3600 in production")
            if not (60 <= self.actor_max_token_ttl_seconds <= 1800):
                raise ValueError("actor_max_token_ttl_seconds must be between 60 and 1800 in production")
            for origin in self.cors_origins:
                if urlparse(origin).scheme.lower() != "https":
                    raise ValueError(f"production CORS origins must use HTTPS: {origin}")
            for integration in ["koa_policy", "koa_audit", "interaction_kernel"]:
                if not self.integration_secret(integration) and not self.outbound_client_cert_file:
                    raise ValueError(f"production integration requires bearer token or mTLS: {integration}")
            if self.orgo_url and not self.integration_secret("orgo") and not self.outbound_client_cert_file:
                raise ValueError("production Orgo integration requires bearer token or mTLS")
            for u in [
                self.workload_jwks_url,
                self.actor_jwks_url,
                self.koa_policy_url,
                self.koa_audit_url,
                self.interaction_kernel_url,
                self.orgo_url,
            ]:
                if u:
                    parsed = urlparse(u)
                    if parsed.scheme.lower() != "https" or not parsed.hostname:
                        raise ValueError(f"production integration URL must use HTTPS with a hostname: {u}")
                    if parsed.username or parsed.password or parsed.fragment:
                        raise ValueError("production integration URLs may not contain userinfo or fragments")
            for path in [self.outbound_ca_bundle, self.outbound_client_cert_file, self.outbound_client_key_file]:
                if path and not Path(path).is_file():
                    raise ValueError(f"configured TLS file does not exist: {path}")
            forbidden = {"HS256", "HS384", "HS512", "none"}
            if forbidden.intersection(self.workload_algorithms + self.actor_algorithms):
                raise ValueError("production JWT algorithms must be asymmetric")

        if self.require_actor_assertion and not (self.actor_jwks_url or self.dev_mode):
            raise ValueError("actor assertions require actor_jwks_url")
        if self.policy_mode == "koa" and not self.koa_policy_url:
            raise ValueError("policy_mode=koa requires koa_policy_url")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
