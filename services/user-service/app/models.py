"""Pydantic schemas.

HTTP API v2 has no request validators (ADR-02), so Pydantic is the validation
layer for the whole system - not a convenience.
"""

from pydantic import BaseModel, Field


class UserProfile(BaseModel):
    userId: str = Field(..., description="Cognito subject (sub) claim")
    username: str
    # Cognito is authoritative for this read-only value. Existing pools may
    # contain legacy addresses (including reserved test domains) that should
    # still be displayed rather than rejected during response validation.
    email: str | None = None
    groups: list[str] = Field(default_factory=list)
    enabled: bool = True


class UserListResponse(BaseModel):
    users: list[UserProfile]
    nextToken: str | None = None


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str
    env: str
