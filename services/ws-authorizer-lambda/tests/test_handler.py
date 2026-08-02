"""Tests for the WebSocket $connect Lambda authorizer.

Token validation is exercised by monkey-patching the JWKS client so the tests
do not require a real Cognito pool. That matches what the srx_common auth
tests do for the HTTP services.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

import handler as h

ISSUER = "https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_TESTPOOL"
CLIENT_ID = "test-client-id"
METHOD_ARN = "arn:aws:execute-api:eu-west-1:000000000000:abc123/prod/$connect"


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("COGNITO_ISSUER", ISSUER)
    monkeypatch.setenv("COGNITO_APP_CLIENT_ID", CLIENT_ID)
    h._reset_cache()
    yield
    h._reset_cache()


@pytest.fixture(scope="module")
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(autouse=True)
def stub_jwks(monkeypatch, signing_key):
    """Replace the JWKS lookup with the local key so validation runs offline."""

    class _StubKey:
        key = signing_key.public_key()

    class _StubClient:
        def get_signing_key_from_jwt(self, token):
            return _StubKey()

    monkeypatch.setattr(h, "_jwks_client", lambda: _StubClient())


def mint(signing_key, **overrides) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "iss": ISSUER,
        "sub": "user-123",
        "aud": CLIENT_ID,
        "token_use": "id",
        "email": "customer@example.com",
        "cognito:groups": ["customer"],
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    claims.update(overrides)
    pem = signing_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return jwt.encode(claims, pem, algorithm="RS256")


# ---------------------------------------------------------------------------
# happy path
# ---------------------------------------------------------------------------


def test_valid_id_token_produces_an_allow_policy(signing_key):
    token = mint(signing_key)
    event = {"queryStringParameters": {"token": token}, "methodArn": METHOD_ARN}

    decision = h.lambda_handler(event, None)

    assert decision["principalId"] == "user-123"
    statement = decision["policyDocument"]["Statement"][0]
    assert statement["Effect"] == "Allow"
    assert statement["Resource"] == METHOD_ARN
    # Context is what $connect uses to derive the userId written into the
    # connections table - the whole point of passing it through.
    assert decision["context"]["userId"] == "user-123"
    assert decision["context"]["email"] == "customer@example.com"
    assert "customer" in decision["context"]["groups"]


def test_access_token_audience_lives_on_client_id_claim(signing_key):
    """Cognito access tokens omit `aud` and put the client id on `client_id`
    instead; the authorizer must accept both."""
    token = mint(
        signing_key,
        token_use="access",
        aud=None,
        client_id=CLIENT_ID,
    )
    event = {"queryStringParameters": {"token": token}, "methodArn": METHOD_ARN}

    decision = h.lambda_handler(event, None)

    assert decision["policyDocument"]["Statement"][0]["Effect"] == "Allow"


# ---------------------------------------------------------------------------
# rejections
# ---------------------------------------------------------------------------


def test_no_token_is_denied():
    event = {"queryStringParameters": {}, "methodArn": METHOD_ARN}
    decision = h.lambda_handler(event, None)
    assert decision["policyDocument"]["Statement"][0]["Effect"] == "Deny"


def test_expired_token_is_denied(signing_key):
    past = datetime.now(timezone.utc) - timedelta(minutes=5)
    token = mint(signing_key, exp=past, iat=past - timedelta(minutes=1))
    event = {"queryStringParameters": {"token": token}, "methodArn": METHOD_ARN}
    decision = h.lambda_handler(event, None)
    assert decision["policyDocument"]["Statement"][0]["Effect"] == "Deny"


def test_wrong_audience_is_denied(signing_key):
    token = mint(signing_key, aud="a-different-client")
    event = {"queryStringParameters": {"token": token}, "methodArn": METHOD_ARN}
    decision = h.lambda_handler(event, None)
    assert decision["policyDocument"]["Statement"][0]["Effect"] == "Deny"


def test_wrong_issuer_is_denied(signing_key):
    token = mint(signing_key, iss="https://example.com/other-pool")
    event = {"queryStringParameters": {"token": token}, "methodArn": METHOD_ARN}
    decision = h.lambda_handler(event, None)
    assert decision["policyDocument"]["Statement"][0]["Effect"] == "Deny"


def test_missing_config_denies_fail_closed(monkeypatch, signing_key):
    """A missing env var is a deployment fault - deny, don't crash silently.
    Fail-closed matches the HTTP services' auth behaviour."""
    monkeypatch.delenv("COGNITO_APP_CLIENT_ID", raising=False)
    token = mint(signing_key)
    event = {"queryStringParameters": {"token": token}, "methodArn": METHOD_ARN}
    decision = h.lambda_handler(event, None)
    assert decision["policyDocument"]["Statement"][0]["Effect"] == "Deny"


# ---------------------------------------------------------------------------
# token transport
# ---------------------------------------------------------------------------


def test_token_can_arrive_via_sec_websocket_protocol_header(signing_key):
    token = mint(signing_key)
    event = {
        "queryStringParameters": None,
        "headers": {"Sec-WebSocket-Protocol": token},
        "methodArn": METHOD_ARN,
    }
    decision = h.lambda_handler(event, None)
    assert decision["policyDocument"]["Statement"][0]["Effect"] == "Allow"
