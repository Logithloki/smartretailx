"""Cognito JWT authentication and group-based authorisation.

Two things worth knowing for the viva:

1.  The API Gateway JWT authoriser validates the signature, issuer and
    audience. It does NOT read `cognito:groups`, because HTTP API v2
    authorisers can only gate on OAuth scopes. Role enforcement therefore
    has to happen here, in the service.
2.  Cognito ACCESS tokens carry the app client id in `client_id`; ID tokens
    carry it in `aud`. Verifying only `aud` would reject every access token,
    so audience is checked manually against either claim.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import BaseServiceSettings

logger = logging.getLogger(__name__)

GROUPS_CLAIM = "cognito:groups"
_ALGORITHMS = ["RS256"]

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    """The authenticated caller, normalised across token types."""

    subject: str
    username: str
    email: str | None = None
    groups: tuple[str, ...] = ()

    def in_group(self, name: str) -> bool:
        return name in self.groups


@lru_cache(maxsize=4)
def _jwk_client(issuer: str) -> jwt.PyJWKClient:
    """One cached JWKS client per issuer - refetching keys per request would
    add a network round trip to every single API call."""
    return jwt.PyJWKClient(f"{issuer.rstrip('/')}/.well-known/jwks.json")


def _normalise_groups(raw: object) -> tuple[str, ...]:
    if isinstance(raw, str):
        return tuple(g for g in raw.replace(",", " ").split() if g)
    if isinstance(raw, (list, tuple)):
        return tuple(str(g) for g in raw)
    return ()


def principal_from_claims(claims: dict) -> Principal:
    subject = str(claims.get("sub", ""))
    username = (
        claims.get("cognito:username")
        or claims.get("username")
        or claims.get("email")
        or subject
    )
    return Principal(
        subject=subject,
        username=str(username),
        email=claims.get("email"),
        groups=_normalise_groups(claims.get(GROUPS_CLAIM)),
    )


def _unauthorised(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


class Authenticator:
    """Builds the FastAPI dependencies each service mounts on its routes."""

    def __init__(self, settings: BaseServiceSettings):
        self.settings = settings

    # ---- token handling -------------------------------------------------

    def _decode_local(self, token: str | None) -> Principal:
        """Local mode: trust whatever is presented, or fall back to a stub.

        Never reachable in production - `current_user` checks `is_local` first.
        """
        if token:
            claims = jwt.decode(token, options={"verify_signature": False})
            return principal_from_claims(claims)
        return Principal(
            subject="local-dev-user",
            username="local@smartretailx.test",
            email="local@smartretailx.test",
            groups=self.settings.local_dev_group_list,
        )

    def _decode_production(self, token: str) -> Principal:
        settings = self.settings
        if not settings.cognito_issuer or not settings.cognito_app_client_id:
            # A missing issuer is a deployment fault, not an anonymous caller.
            # Returning 401 would be a lie and 200 would be a breach, so fail loudly.
            logger.error("auth misconfigured: cognito_issuer/app_client_id unset")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="authentication is not configured",
            )

        try:
            signing_key = _jwk_client(settings.cognito_issuer).get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=_ALGORITHMS,
                issuer=settings.cognito_issuer,
                options={"verify_aud": False, "require": ["exp", "iss", "sub"]},
            )
        except HTTPException:
            raise
        except jwt.ExpiredSignatureError as exc:
            raise _unauthorised("token has expired") from exc
        except jwt.PyJWTError as exc:
            logger.warning("jwt rejected: %s", exc.__class__.__name__)
            raise _unauthorised("invalid token") from exc

        if claims.get("token_use") not in {"access", "id"}:
            raise _unauthorised("unsupported token_use")

        audience = claims.get("aud") or claims.get("client_id")
        if audience != settings.cognito_app_client_id:
            raise _unauthorised("token was not issued for this application")

        return principal_from_claims(claims)

    # ---- FastAPI dependencies ------------------------------------------

    def current_user(
        self,
        credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    ) -> Principal:
        token = credentials.credentials if credentials else None

        if self.settings.is_local:
            return self._decode_local(token)

        if not token:
            raise _unauthorised("missing bearer token")
        return self._decode_production(token)

    def requires(self, *groups: str) -> Callable:
        """Dependency that 403s unless the caller is in one of `groups`.

        The SPA also hides admin controls, but that is cosmetic - this is the
        control that actually holds.
        """
        required = set(groups)

        def _guard(user: Principal = Depends(self.current_user)) -> Principal:
            if not required.intersection(user.groups):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"requires membership of: {', '.join(sorted(required))}",
                )
            return user

        return _guard
