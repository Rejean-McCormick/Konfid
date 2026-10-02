import pytest
from pydantic import ValidationError
from konfid.config import Settings

def test_production_configuration_is_fail_closed():
    with pytest.raises(ValidationError):
        Settings(_env_file=None,dev_mode=False,
        database_url="postgresql+psycopg://konfid:test@db/konfid",require_actor_assertion=False,policy_mode="local")

def test_production_accepts_explicit_trust_dependencies():
    s=Settings(
        _env_file=None,
        env="production",
        dev_mode=False,
        database_url="postgresql+psycopg://konfid:test@db/konfid?sslmode=verify-full",
        require_actor_assertion=True,
        require_actor_authorized_party=True,
        workload_jwks_url="https://identity.example/workloads/jwks.json",
        actor_jwks_url="https://identity.example/actors/jwks.json",
        policy_mode="koa",
        koa_policy_url="https://policy.internal",
        koa_audit_url="https://audit.internal",
        interaction_kernel_url="https://ik.internal",
        metrics_enabled=False,
        koa_policy_bearer_token="x",
        koa_audit_bearer_token="x",
        interaction_kernel_bearer_token="x",
    )
    assert s.dev_mode is False and s.policy_mode=="koa"


def test_production_rejects_postgres_without_hostname_verification():
    with pytest.raises(ValidationError, match="sslmode=verify-full"):
        Settings(
            _env_file=None,
            env="production",
            dev_mode=False,
            database_url="postgresql+psycopg://konfid:test@db/konfid?sslmode=require",
            require_actor_assertion=True,
            require_actor_authorized_party=True,
            workload_jwks_url="https://identity.example/workloads/jwks.json",
            actor_jwks_url="https://identity.example/actors/jwks.json",
            policy_mode="koa",
            koa_policy_url="https://policy.internal",
            koa_audit_url="https://audit.internal",
            interaction_kernel_url="https://ik.internal",
            metrics_enabled=False,
            koa_policy_bearer_token="x",
            koa_audit_bearer_token="x",
            interaction_kernel_bearer_token="x",
        )


def test_production_rejects_trust_url_userinfo():
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            env="production",
            dev_mode=False,
            database_url="postgresql+psycopg://konfid:test@db/konfid?sslmode=verify-full",
            require_actor_assertion=True,
            require_actor_authorized_party=True,
            workload_jwks_url="https://user:pass@identity.example/workloads/jwks.json",
            actor_jwks_url="https://identity.example/actors/jwks.json",
            policy_mode="koa",
            koa_policy_url="https://policy.internal",
            koa_audit_url="https://audit.internal",
            interaction_kernel_url="https://ik.internal",
            metrics_enabled=False,
            koa_policy_bearer_token="x",
            koa_audit_bearer_token="x",
            interaction_kernel_bearer_token="x",
        )
