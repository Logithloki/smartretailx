from __future__ import annotations

import boto3
import jwt
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from app.config import Settings
from app.main import create_app
from app.models import UserProfile
from app.services import CognitoUserRepository, InMemoryUserRepository, UserNotFound


@pytest.fixture(autouse=True)
def aws_credentials(monkeypatch):
    """Keep moto sealed off from any real profile on this machine."""
    for key, value in {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SECURITY_TOKEN": "testing",
        "AWS_SESSION_TOKEN": "testing",
        "AWS_DEFAULT_REGION": "eu-west-1",
    }.items():
        monkeypatch.setenv(key, value)


def local_settings(**kwargs) -> Settings:
    base = {"env": "local", "_env_file": None}
    base.update(kwargs)
    return Settings(**base)


def client(**kwargs) -> TestClient:
    settings = kwargs.pop("settings", None) or local_settings(**kwargs)
    return TestClient(create_app(settings=settings))


def token_for(*groups: str, sub: str = "user-1", username: str = "alice") -> dict:
    """Local mode reads unsigned tokens, so RBAC is testable without keys."""
    raw = jwt.encode(
        {"sub": sub, "cognito:username": username, "cognito:groups": list(groups)},
        "unused",
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {raw}"}


# --------------------------------------------------------------------------
# health
# --------------------------------------------------------------------------

def test_health_is_public_and_reports_env():
    """The ALB health check is unauthenticated - if this ever needs a token
    the target group goes permanently unhealthy."""
    response = client().get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == "user-service"


def test_openapi_contract_exposes_canonical_user_routes():
    paths = client().get("/openapi.json").json()["paths"]
    assert "/v1/users" in paths
    assert "/v1/users/me" in paths
    assert all(not path.startswith("/api/") for path in paths)


# --------------------------------------------------------------------------
# /v1/users/me
# --------------------------------------------------------------------------

def test_me_returns_claims_from_the_token():
    response = client().get("/v1/users/me", headers=token_for("customer"))
    assert response.status_code == 200
    body = response.json()
    assert body["userId"] == "user-1"
    assert body["groups"] == ["customer"]


def test_routes_are_versioned_under_v1():
    """Backlog item 12 - unversioned paths must not resolve."""
    assert client().get("/users/me", headers=token_for("customer")).status_code == 404


# --------------------------------------------------------------------------
# RBAC on the directory listing
# --------------------------------------------------------------------------

def test_customer_cannot_list_users():
    assert client().get("/v1/users", headers=token_for("customer")).status_code == 403


def test_admin_can_list_users():
    response = client().get("/v1/users", headers=token_for("admin"))
    assert response.status_code == 200
    assert len(response.json()["users"]) == 2


def test_admin_directory_returns_legacy_test_domain_email():
    repository = InMemoryUserRepository(
        seed=[
            UserProfile(
                userId="legacy-user",
                username="legacy-user",
                email="legacy@smartretailx.test",
                groups=["customer"],
            )
        ]
    )
    response = TestClient(create_app(settings=local_settings(), repository=repository)).get(
        "/v1/users", headers=token_for("admin")
    )

    assert response.status_code == 200
    assert response.json()["users"][0]["email"] == "legacy@smartretailx.test"


def test_admin_directory_handles_missing_email():
    repository = InMemoryUserRepository(
        seed=[
            UserProfile(
                userId="no-email-user",
                username="no-email-user",
                email=None,
                groups=["customer"],
            )
        ]
    )
    response = TestClient(create_app(settings=local_settings(), repository=repository)).get(
        "/v1/users", headers=token_for("admin")
    )

    assert response.status_code == 200
    assert response.json()["users"][0]["email"] is None


def test_list_users_rejects_out_of_range_limit():
    """Pydantic/FastAPI query validation stands in for the request validators
    HTTP API v2 does not have (ADR-02)."""
    assert client().get("/v1/users?limit=500", headers=token_for("admin")).status_code == 422
    assert client().get("/v1/users?limit=0", headers=token_for("admin")).status_code == 422


# --------------------------------------------------------------------------
# self-vs-admin read rules
# --------------------------------------------------------------------------

def test_customer_may_read_own_profile():
    response = client().get(
        "/v1/users/customer@example.com",
        headers=token_for("customer", username="customer@example.com"),
    )
    assert response.status_code == 200


def test_customer_may_not_read_another_profile():
    response = client().get(
        "/v1/users/admin@example.com",
        headers=token_for("customer", username="customer@example.com"),
    )
    assert response.status_code == 403


def test_admin_may_read_any_profile():
    response = client().get(
        "/v1/users/customer@example.com",
        headers=token_for("admin", username="admin@example.com"),
    )
    assert response.status_code == 200


def test_missing_user_is_404_for_admin():
    response = client().get("/v1/users/nobody@example.com", headers=token_for("admin"))
    assert response.status_code == 404


def test_admin_can_delete_another_user_but_not_self():
    admin = token_for("admin", username="admin@example.com")
    assert client().delete("/v1/users/customer@example.com", headers=admin).status_code == 204
    assert client().delete("/v1/users/admin@example.com", headers=admin).status_code == 400


def test_admin_self_delete_is_rejected_for_different_case_and_whitespace():
    admin = token_for("admin", username="Admin@Example.com")
    assert client().delete("/v1/users/admin@example.com", headers=admin).status_code == 400
    assert client().delete("/v1/users/%20admin@example.com%20", headers=admin).status_code == 400


def test_cognito_delete_failure_does_not_remove_the_user(monkeypatch):
    from app.main import create_app

    repository = InMemoryUserRepository()

    def fail_delete(username):
        raise RuntimeError("cognito unavailable")

    monkeypatch.setattr(repository, "delete_user", fail_delete)
    app = create_app(settings=local_settings(), repository=repository)
    response = TestClient(app, raise_server_exceptions=False).delete(
        "/v1/users/customer@example.com", headers=token_for("admin")
    )
    assert response.status_code == 500
    assert repository.get_user("customer@example.com").username == "customer@example.com"


def test_customer_cannot_delete_users():
    response = client().delete("/v1/users/admin@example.com", headers=token_for("customer"))
    assert response.status_code == 403


# --------------------------------------------------------------------------
# in-memory repository
# --------------------------------------------------------------------------

def test_in_memory_repository_raises_for_unknown_user():
    with pytest.raises(UserNotFound):
        InMemoryUserRepository().get_user("ghost")


# --------------------------------------------------------------------------
# Cognito-backed repository (moto)
# --------------------------------------------------------------------------

@mock_aws
def test_cognito_repository_reads_users_and_groups():
    idp = boto3.client("cognito-idp", region_name="eu-west-1")
    pool_id = idp.create_user_pool(PoolName="test-pool")["UserPool"]["Id"]
    idp.create_group(GroupName="admin", UserPoolId=pool_id)
    idp.admin_create_user(
        UserPoolId=pool_id,
        Username="admin@example.com",
        UserAttributes=[{"Name": "email", "Value": "admin@example.com"}],
    )
    idp.admin_add_user_to_group(
        UserPoolId=pool_id, Username="admin@example.com", GroupName="admin"
    )

    settings = Settings(
        env="production", cognito_user_pool_id=pool_id, app_region="eu-west-1", _env_file=None
    )
    repo = CognitoUserRepository(settings)

    users, _ = repo.list_users()
    assert [u.username for u in users] == ["admin@example.com"]
    assert users[0].groups == ["admin"]

    profile = repo.get_user("admin@example.com")
    assert profile.email == "admin@example.com"
    assert profile.groups == ["admin"]


@mock_aws
def test_cognito_repository_maps_missing_user_to_domain_error():
    idp = boto3.client("cognito-idp", region_name="eu-west-1")
    pool_id = idp.create_user_pool(PoolName="test-pool")["UserPool"]["Id"]
    settings = Settings(
        env="production", cognito_user_pool_id=pool_id, app_region="eu-west-1", _env_file=None
    )
    with pytest.raises(UserNotFound):
        CognitoUserRepository(settings).get_user("ghost@example.com")


def test_cognito_repository_requires_pool_id():
    settings = Settings(env="production", cognito_user_pool_id=None, _env_file=None)
    with pytest.raises(RuntimeError):
        CognitoUserRepository(settings).list_users()


def test_cognito_directory_lists_group_memberships_in_bulk():
    """The directory must not issue one Cognito group call per listed user.

    The old N+1 implementation made a directory page fragile under Cognito's
    request quotas and converted one group lookup failure into an HTTP 500.
    """

    class FakeCognito:
        def list_users(self, **kwargs):
            return {
                "Users": [
                    {
                        "Username": "admin@example.com",
                        "Attributes": [{"Name": "email", "Value": "admin@example.com"}],
                    },
                    {
                        "Username": "customer@example.com",
                        "Attributes": [{"Name": "email", "Value": "customer@example.com"}],
                    },
                ]
            }

        def list_groups(self, **kwargs):
            return {"Groups": [{"GroupName": "admin"}, {"GroupName": "customer"}]}

        def list_users_in_group(self, **kwargs):
            if kwargs["GroupName"] == "admin":
                return {"Users": [{"Username": "admin@example.com"}]}
            return {"Users": [{"Username": "customer@example.com"}]}

        def admin_list_groups_for_user(self, **kwargs):
            raise AssertionError("per-user group lookup must not be used for directory listings")

    settings = Settings(
        env="production", cognito_user_pool_id="eu-west-1_example", _env_file=None
    )
    repo = CognitoUserRepository(settings)
    repo._client = FakeCognito()

    users, token = repo.list_users()

    assert token is None
    assert {user.username: user.groups for user in users} == {
        "admin@example.com": ["admin"],
        "customer@example.com": ["customer"],
    }
