"""User repositories.

LocalStack Community cannot emulate Cognito (CLAUDE.md, local-first section),
so local development runs against an in-memory stub with the same interface.
The Cognito-backed implementation is exercised by moto in the unit tests and
on real AWS during checkpoint windows.
"""

from __future__ import annotations

import logging

import boto3
from botocore.exceptions import ClientError

from .models import UserProfile

logger = logging.getLogger(__name__)


class UserNotFound(Exception):
    pass


class InMemoryUserRepository:
    """Local-mode stand-in for Cognito."""

    def __init__(self, seed: list[UserProfile] | None = None):
        self._users: dict[str, UserProfile] = {}
        for user in seed if seed is not None else self._default_seed():
            self._users[user.username] = user

    @staticmethod
    def _default_seed() -> list[UserProfile]:
        return [
            UserProfile(
                userId="local-customer-1",
                username="customer@example.com",
                email="customer@example.com",
                groups=["customer"],
            ),
            UserProfile(
                userId="local-admin-1",
                username="admin@example.com",
                email="admin@example.com",
                groups=["customer", "admin"],
            ),
        ]

    def list_users(self, limit: int = 25, next_token: str | None = None):
        return list(self._users.values())[:limit], None

    def get_user(self, username: str) -> UserProfile:
        try:
            return self._users[username]
        except KeyError as exc:
            raise UserNotFound(username) from exc

    def delete_user(self, username: str) -> None:
        if username not in self._users:
            raise UserNotFound(username)
        del self._users[username]


class CognitoUserRepository:
    """Reads the Terraform-managed user pool via cognito-idp admin APIs.

    The task role grants only the Cognito directory read operations needed for
    this pool. Directory listings use one group-membership pass rather than an
    AdminListGroupsForUser request for every listed user; the latter creates an
    avoidable N+1 request pattern and is vulnerable to Cognito throttling.
    """

    def __init__(self, settings):
        self._settings = settings
        self._client = None

    @property
    def client(self):
        # Lazy so importing the module never requires credentials.
        if self._client is None:
            self._client = boto3.client("cognito-idp", **self._settings.boto_kwargs())
        return self._client

    @property
    def _pool_id(self) -> str:
        pool_id = self._settings.cognito_user_pool_id
        if not pool_id:
            raise RuntimeError("COGNITO_USER_POOL_ID is not configured")
        return pool_id

    @staticmethod
    def _attr(attributes: list[dict], name: str) -> str | None:
        for attribute in attributes or []:
            if attribute.get("Name") == name:
                return attribute.get("Value")
        return None

    def _to_profile(self, raw: dict, groups: list[str]) -> UserProfile:
        attributes = raw.get("Attributes") or raw.get("UserAttributes") or []
        return UserProfile(
            userId=self._attr(attributes, "sub") or raw.get("Username", ""),
            username=raw.get("Username", ""),
            email=self._attr(attributes, "email"),
            groups=groups,
            enabled=raw.get("Enabled", True),
        )

    def _groups_for(self, username: str) -> list[str]:
        response = self.client.admin_list_groups_for_user(
            UserPoolId=self._pool_id, Username=username
        )
        return [g["GroupName"] for g in response.get("Groups", [])]

    def _group_memberships(self) -> dict[str, list[str]]:
        """Return user-to-group memberships with bounded Cognito calls.

        Cognito's ListUsers response does not include group membership. Fetch
        the groups once, then list each group's members once per page. This is
        proportional to the number of groups rather than the number of users,
        so a directory page cannot turn into an N+1 burst of admin API calls.
        """
        memberships: dict[str, list[str]] = {}
        groups_token: str | None = None

        while True:
            kwargs: dict[str, object] = {"UserPoolId": self._pool_id, "Limit": 60}
            if groups_token:
                kwargs["NextToken"] = groups_token
            response = self.client.list_groups(**kwargs)
            for group in response.get("Groups", []):
                group_name = group.get("GroupName")
                if not group_name:
                    continue
                users_token: str | None = None
                while True:
                    user_kwargs: dict[str, object] = {
                        "UserPoolId": self._pool_id,
                        "GroupName": group_name,
                        "Limit": 60,
                    }
                    if users_token:
                        user_kwargs["NextToken"] = users_token
                    user_response = self.client.list_users_in_group(**user_kwargs)
                    for user in user_response.get("Users", []):
                        username = user.get("Username")
                        if username:
                            memberships.setdefault(username, []).append(group_name)
                    users_token = user_response.get("NextToken")
                    if not users_token:
                        break
            groups_token = response.get("NextToken")
            if not groups_token:
                break

        return memberships

    def list_users(self, limit: int = 25, next_token: str | None = None):
        kwargs: dict = {"UserPoolId": self._pool_id, "Limit": limit}
        if next_token:
            kwargs["PaginationToken"] = next_token
        response = self.client.list_users(**kwargs)
        memberships = self._group_memberships()
        users = [
            self._to_profile(raw, memberships.get(raw["Username"], []))
            for raw in response.get("Users", [])
        ]
        return users, response.get("PaginationToken")

    def get_user(self, username: str) -> UserProfile:
        try:
            raw = self.client.admin_get_user(UserPoolId=self._pool_id, Username=username)
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "UserNotFoundException":
                raise UserNotFound(username) from exc
            raise
        return self._to_profile(raw, self._groups_for(username))

    def delete_user(self, username: str) -> None:
        try:
            self.client.admin_delete_user(UserPoolId=self._pool_id, Username=username)
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "UserNotFoundException":
                raise UserNotFound(username) from exc
            raise


def build_repository(settings):
    return InMemoryUserRepository() if settings.is_local else CognitoUserRepository(settings)
