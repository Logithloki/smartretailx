"""WebSocket `$connect` request authorizer.

API Gateway v2 WebSocket APIs do NOT support the built-in JWT authorizer
(that path is HTTP/REST only). The standard workaround is a small Lambda
REQUEST authorizer that reads the token from the query string
(`wss://<endpoint>?token=<JWT>`) - the browser cannot set Authorization
headers on the WebSocket upgrade, so a query-string token is the only
practical option. The token is validated against the Cognito JWKS the same
way `srx_common.auth` validates it for the HTTP services, so authoriser
behaviour matches everywhere in the system.

This module deliberately does NOT depend on the srx_common package: Lambda
zip artefacts are packaged per-function and the common package cannot be
easily included without a build step. The JWT validation logic is
duplicated in miniature form and kept behaviourally aligned via the
comment in `srx_common/auth.py`.

Returning `Deny` from this authoriser rejects the connection with a 401 at
the WebSocket upgrade; a `sub` claim is passed through in the authoriser
context so the `$connect` handler can record `userId` on the connection
without decoding the token twice.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache

import jwt

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

_ALGORITHMS = ["RS256"]


@lru_cache(maxsize=1)
def _jwks_client() -> jwt.PyJWKClient:
    issuer = os.environ["COGNITO_ISSUER"].rstrip("/")
    return jwt.PyJWKClient(f"{issuer}/.well-known/jwks.json")


def _reset_cache() -> None:
    """Test hook - drops the cached JWKS client so a fresh env can be bound.

    Robust against a monkey-patched `_jwks_client` (some tests replace it
    with a plain callable, so `cache_clear` might be missing).
    """
    clear = getattr(_jwks_client, "cache_clear", None)
    if callable(clear):
        clear()


def _extract_token(event: dict) -> str | None:
    """Query string is the only workable transport for the WS upgrade token."""
    qs = event.get("queryStringParameters") or {}
    token = qs.get("token")
    if token:
        return token
    # Some clients place the token in `Sec-WebSocket-Protocol` as a fallback;
    # supporting the header keeps browser and CLI paths symmetric.
    headers = event.get("headers") or {}
    return headers.get("Sec-WebSocket-Protocol") or headers.get("sec-websocket-protocol")


def _validate(token: str) -> dict:
    issuer = os.environ["COGNITO_ISSUER"]
    audience = os.environ["COGNITO_APP_CLIENT_ID"]

    signing_key = _jwks_client().get_signing_key_from_jwt(token)
    claims = jwt.decode(
        token,
        signing_key.key,
        algorithms=_ALGORITHMS,
        issuer=issuer,
        # Cognito access tokens carry the client id in `client_id`, ID tokens
        # in `aud`. Verifying `aud` here would reject access tokens outright,
        # so we check the audience by hand against either claim below.
        options={"verify_aud": False, "require": ["exp", "iss", "sub"]},
    )

    if claims.get("token_use") not in {"access", "id"}:
        raise jwt.InvalidTokenError("unsupported token_use")

    presented_audience = claims.get("aud") or claims.get("client_id")
    if presented_audience != audience:
        raise jwt.InvalidTokenError("token was not issued for this application")

    return claims


def _allow(principal_id: str, method_arn: str, claims: dict) -> dict:
    return {
        "principalId": principal_id,
        "policyDocument": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Action": "execute-api:Invoke",
                    "Effect": "Allow",
                    # A wildcard here would let the same Allow decision cover
                    # any route on any stage of the API; scoping to the exact
                    # `$connect` invocation the client asked for closes that.
                    "Resource": method_arn,
                }
            ],
        },
        # Context is copied by API Gateway onto `event.requestContext.authorizer`
        # for the $connect Lambda - saves decoding the JWT twice.
        "context": {
            "userId": claims.get("sub", ""),
            "email": str(claims.get("email", "") or ""),
            "groups": ",".join(_normalise_groups(claims.get("cognito:groups"))),
        },
    }


def _deny(method_arn: str) -> dict:
    return {
        "principalId": "anonymous",
        "policyDocument": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Action": "execute-api:Invoke",
                    "Effect": "Deny",
                    "Resource": method_arn,
                }
            ],
        },
    }


def _normalise_groups(raw: object) -> tuple[str, ...]:
    if isinstance(raw, str):
        return tuple(g for g in raw.replace(",", " ").split() if g)
    if isinstance(raw, (list, tuple)):
        return tuple(str(g) for g in raw)
    return ()


def lambda_handler(event: dict, context) -> dict:
    method_arn = event.get("methodArn", "*")

    token = _extract_token(event)
    if not token:
        logger.info("ws authorizer: no token presented")
        return _deny(method_arn)

    try:
        claims = _validate(token)
    except jwt.PyJWTError as exc:
        logger.info("ws authorizer: token rejected (%s)", exc.__class__.__name__)
        return _deny(method_arn)
    except KeyError as exc:
        # A missing env var is a deployment fault; deny closed rather than
        # returning a soft error the client cannot interpret.
        logger.error("ws authorizer: misconfigured, missing %s", exc)
        return _deny(method_arn)

    return _allow(principal_id=claims["sub"], method_arn=method_arn, claims=claims)
