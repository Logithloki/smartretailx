"""User Service - profile and directory reads backed by Cognito.

All routes live under /v1 (API versioning is an explicitly marked requirement,
backlog item 12). /health is deliberately unauthenticated: it is the ALB target
group health check.
"""

from __future__ import annotations

import logging

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from srx_common import Authenticator, Principal, configure_logging, instrument_fastapi

from .config import Settings, get_settings
from .models import HealthResponse, UserListResponse, UserProfile
from .services import UserNotFound, build_repository

logger = logging.getLogger(__name__)


def canonical_username(username: str) -> str:
    """Cognito email usernames are compared case-insensitively."""
    return username.strip().casefold()


def create_app(settings: Settings | None = None, repository=None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.service_name, settings.log_level)

    repo = repository if repository is not None else build_repository(settings)
    auth = Authenticator(settings)

    app = FastAPI(
        title="SmartRetailX User Service",
        version="1.0.0",
        description="Cognito-backed user profiles and directory.",
    )
    instrument_fastapi(app, settings.service_name)

    @app.get("/health", response_model=HealthResponse, tags=["health"])
    def health() -> HealthResponse:
        return HealthResponse(service=settings.service_name, env=settings.env)

    @app.get("/v1/users/me", response_model=UserProfile, tags=["users"])
    def me(user: Principal = Depends(auth.current_user)) -> UserProfile:
        """Identity as the token asserts it - no directory lookup needed."""
        return UserProfile(
            userId=user.subject,
            username=user.username,
            email=user.email,
            groups=list(user.groups),
        )

    @app.get(
        "/v1/users",
        response_model=UserListResponse,
        tags=["users"],
        dependencies=[Depends(auth.requires("admin"))],
    )
    def list_users(
        limit: int = Query(25, ge=1, le=60),
        nextToken: str | None = Query(None),
    ) -> UserListResponse:
        users, token = repo.list_users(limit=limit, next_token=nextToken)
        return UserListResponse(users=users, nextToken=token)

    @app.get("/v1/users/{username}", response_model=UserProfile, tags=["users"])
    def get_user(username: str, caller: Principal = Depends(auth.current_user)) -> UserProfile:
        """Admins may read anyone; everyone else may read only themselves."""
        username = canonical_username(username)
        is_self = username in {canonical_username(caller.username), canonical_username(caller.subject)}
        if not is_self and not caller.in_group("admin"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="you may only read your own profile",
            )
        try:
            return repo.get_user(username)
        except UserNotFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="user not found"
            ) from None

    @app.delete(
        "/v1/users/{username}", status_code=status.HTTP_204_NO_CONTENT, tags=["admin"],
        dependencies=[Depends(auth.requires("admin"))],
        summary="Delete a Cognito user as an administrator",
    )
    def delete_user(username: str, caller: Principal = Depends(auth.current_user)) -> Response:
        username = canonical_username(username)
        if username in {canonical_username(caller.username), canonical_username(caller.subject)}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="administrators cannot delete themselves")
        try:
            repo.delete_user(username)
        except UserNotFound:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found") from None
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return app


app = create_app()
