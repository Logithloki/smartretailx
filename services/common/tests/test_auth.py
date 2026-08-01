"""Tests for the shared auth module.

The fail-closed cases matter most: a missing ENV, a missing issuer, or a
malformed token must never result in an authenticated request.
"""

from __future__ import annotations

import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from srx_common import auth as auth_module
from srx_common.auth import Authenticator, Principal
from srx_common.config import BaseServiceSettings

ISSUER = "https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_TESTPOOL"
CLIENT_ID = "test-client-id"


# --------------------------------------------------------------------------
# key material + token helpers
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def keypair():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return pem, private.public_key()


@pytest.fixture(autouse=True)
def _clear_jwks_cache():
    auth_module._jwk_client.cache_clear()
    yield
    auth_module._jwk_client.cache_clear()


@pytest.fixture
def stub_jwks(monkeypatch, keypair):
    """Serve the test public key instead of fetching Cognito's JWKS."""
    _, public_key = keypair

    class _Key:
        key = public_key

    class _Client:
        def get_signing_key_from_jwt(self, token):
            return _Key()

    monkeypatch.setattr(auth_module, "_jwk_client", lambda issuer: _Client())


def make_token(keypair, **overrides) -> str:
    pem, _ = keypair
    now = int(time.time())
    claims = {
        "sub": "user-123",
        "iss": ISSUER,
        "client_id": CLIENT_ID,
        "token_use": "access",
        "cognito:username": "alice",
        "email": "alice@example.com",
        "cognito:groups": ["customer"],
        "iat": now,
        "exp": now + 3600,
    }
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, pem, algorithm="RS256")


def settings_for(**kwargs) -> BaseServiceSettings:
    base = {
        "cognito_issuer": ISSUER,
        "cognito_app_client_id": CLIENT_ID,
        # _env_file=None stops a stray .env.local on disk leaking into tests.
        "_env_file": None,
    }
    base.update(kwargs)
    return BaseServiceSettings(**base)


def build_app(authenticator: Authenticator) -> TestClient:
    app = FastAPI()

    @app.get("/whoami")
    def whoami(user: Principal = Depends(authenticator.current_user)):
        return {"subject": user.subject, "groups": list(user.groups)}

    @app.get("/admin-only")
    def admin_only(user: Principal = Depends(authenticator.requires("admin"))):
        return {"ok": True}

    return TestClient(app)


# --------------------------------------------------------------------------
# fail-closed behaviour
# --------------------------------------------------------------------------

@pytest.mark.parametrize("env_value", [None, "", "   ", "PRODUCTION", "prod", "Local-ish"])
def test_unset_or_unknown_env_is_treated_as_production(env_value):
    """Only the exact string 'local' relaxes auth. Everything else is locked."""
    kwargs = {} if env_value is None else {"env": env_value}
    settings = settings_for(**kwargs)
    assert settings.is_local is False


def test_env_local_is_the_only_relaxed_mode():
    assert settings_for(env="local").is_local is True
    assert settings_for(env="  LOCAL  ").is_local is True


def test_production_without_token_is_401():
    client = build_app(Authenticator(settings_for()))
    assert client.get("/whoami").status_code == 401


def test_missing_cognito_config_fails_with_500_not_200(keypair, stub_jwks):
    """A deployment fault must not read as an anonymous request, and must
    certainly not read as a successful one."""
    settings = settings_for(cognito_issuer=None, cognito_app_client_id=None)
    client = build_app(Authenticator(settings))
    response = client.get("/whoami", headers={"Authorization": f"Bearer {make_token(keypair)}"})
    assert response.status_code == 500


def test_garbage_token_is_401():
    client = build_app(Authenticator(settings_for()))
    response = client.get("/whoami", headers={"Authorization": "Bearer not.a.jwt"})
    assert response.status_code == 401


# --------------------------------------------------------------------------
# production token validation
# --------------------------------------------------------------------------

def test_valid_access_token_is_accepted(keypair, stub_jwks):
    client = build_app(Authenticator(settings_for()))
    response = client.get("/whoami", headers={"Authorization": f"Bearer {make_token(keypair)}"})
    assert response.status_code == 200
    assert response.json() == {"subject": "user-123", "groups": ["customer"]}


def test_id_token_audience_claim_is_accepted(keypair, stub_jwks):
    """ID tokens carry `aud`; access tokens carry `client_id`. Both are ours."""
    token = make_token(keypair, client_id=None, aud=CLIENT_ID, token_use="id")
    client = build_app(Authenticator(settings_for()))
    assert client.get("/whoami", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_token_for_another_client_is_rejected(keypair, stub_jwks):
    token = make_token(keypair, client_id="some-other-app")
    client = build_app(Authenticator(settings_for()))
    assert client.get("/whoami", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_token_from_another_issuer_is_rejected(keypair, stub_jwks):
    token = make_token(keypair, iss="https://evil.example.com")
    client = build_app(Authenticator(settings_for()))
    assert client.get("/whoami", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_expired_token_is_rejected(keypair, stub_jwks):
    now = int(time.time())
    token = make_token(keypair, iat=now - 7200, exp=now - 3600)
    client = build_app(Authenticator(settings_for()))
    assert client.get("/whoami", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_unexpected_token_use_is_rejected(keypair, stub_jwks):
    token = make_token(keypair, token_use="refresh")
    client = build_app(Authenticator(settings_for()))
    assert client.get("/whoami", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_tampered_signature_is_rejected(keypair, stub_jwks):
    token = make_token(keypair)
    head, payload, _ = token.split(".")
    forged = f"{head}.{payload}.AAAAinvalidsignatureAAAA"
    client = build_app(Authenticator(settings_for()))
    assert client.get("/whoami", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


# --------------------------------------------------------------------------
# RBAC
# --------------------------------------------------------------------------

def test_customer_cannot_reach_admin_route(keypair, stub_jwks):
    client = build_app(Authenticator(settings_for()))
    token = make_token(keypair, **{"cognito:groups": ["customer"]})
    assert client.get("/admin-only", headers={"Authorization": f"Bearer {token}"}).status_code == 403


def test_admin_can_reach_admin_route(keypair, stub_jwks):
    client = build_app(Authenticator(settings_for()))
    token = make_token(keypair, **{"cognito:groups": ["customer", "admin"]})
    assert client.get("/admin-only", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_admin_route_without_token_is_401_not_403(keypair, stub_jwks):
    """Unauthenticated must not be reported as merely unauthorised."""
    client = build_app(Authenticator(settings_for()))
    assert client.get("/admin-only").status_code == 401


@pytest.mark.parametrize(
    "raw,expected",
    [
        (["admin", "customer"], ("admin", "customer")),
        ("admin customer", ("admin", "customer")),
        ("admin,customer", ("admin", "customer")),
        (None, ()),
        ([], ()),
    ],
)
def test_groups_claim_normalisation(raw, expected):
    claims = {"sub": "s", "cognito:username": "u"}
    if raw is not None:
        claims["cognito:groups"] = raw
    assert auth_module.principal_from_claims(claims).groups == expected


# --------------------------------------------------------------------------
# local mode
# --------------------------------------------------------------------------

def test_local_mode_without_token_uses_stub_principal():
    client = build_app(Authenticator(settings_for(env="local")))
    body = client.get("/whoami").json()
    assert body["subject"] == "local-dev-user"
    assert body["groups"] == ["customer"]


def test_local_stub_groups_are_configurable():
    settings = settings_for(env="local", local_dev_groups="customer,admin")
    client = build_app(Authenticator(settings))
    assert client.get("/admin-only").status_code == 200


def test_local_mode_honours_unsigned_token_claims():
    """Lets tests and local dev exercise RBAC without minting real tokens."""
    token = jwt.encode({"sub": "s1", "cognito:groups": ["admin"]}, "secret", algorithm="HS256")
    client = build_app(Authenticator(settings_for(env="local")))
    assert client.get("/admin-only", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_local_mode_is_never_used_when_env_is_production(keypair, stub_jwks):
    """The same unsigned token that works locally must fail in production."""
    token = jwt.encode({"sub": "s1", "cognito:groups": ["admin"]}, "secret", algorithm="HS256")
    client = build_app(Authenticator(settings_for(env="production")))
    assert client.get("/admin-only", headers={"Authorization": f"Bearer {token}"}).status_code == 401
