from __future__ import annotations

import boto3
import jwt
import pytest
from moto import mock_aws

from app.config import Settings
from app.database import build_engine, build_session_factory, create_schema
from app.services import StockRepository


@pytest.fixture(autouse=True)
def aws_credentials(monkeypatch):
    for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        monkeypatch.setenv(key, "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-west-1")


@pytest.fixture
def settings(tmp_path) -> Settings:
    """SQLite on disk for unit tests: fast and dependency-free. The same code
    runs against Postgres 16 in docker compose and Aurora PG16 in production;
    the Day 5 saga demo exercises the Postgres path for real."""
    return Settings(
        env="local",
        app_region="eu-west-1",
        database_url=f"sqlite:///{tmp_path/'stock.db'}",
        _env_file=None,
    )


@pytest.fixture
def session_factory(settings):
    engine = build_engine(settings)
    create_schema(engine)
    return build_session_factory(engine)


@pytest.fixture
def repository(session_factory) -> StockRepository:
    repo = StockRepository(session_factory)
    repo.upsert("prod-laptop-001", 50)
    repo.upsert("prod-mouse-002", 5)
    repo.upsert("prod-sold-out", 0)
    return repo


@pytest.fixture
def aws():
    with mock_aws():
        yield


@pytest.fixture
def orders_queue(aws):
    sqs = boto3.client("sqs", region_name="eu-west-1")
    return sqs.create_queue(QueueName="test-orders-queue")["QueueUrl"]


@pytest.fixture
def sns_topic(aws):
    sns = boto3.client("sns", region_name="eu-west-1")
    return sns.create_topic(Name="test-order-confirmed")["TopicArn"]


@pytest.fixture
def messaging_settings(settings, orders_queue, sns_topic) -> Settings:
    return settings.model_copy(
        update={"orders_queue_url": orders_queue, "sns_topic_arn": sns_topic}
    )


def auth_header(sub: str = "user-1", *groups: str) -> dict:
    token = jwt.encode(
        {"sub": sub, "cognito:username": sub, "cognito:groups": list(groups) or ["customer"]},
        "unused",
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}
