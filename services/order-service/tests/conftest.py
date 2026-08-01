from __future__ import annotations

import boto3
import jwt
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from app.config import Settings
from app.events import OrderCommandPublisher
from app.main import create_app
from app.services import OrderRepository

ORDERS_TABLE = "test-orders"
IDEMPOTENCY_TABLE = "test-idempotency"


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


@pytest.fixture
def aws():
    with mock_aws():
        yield


@pytest.fixture
def orders_table(aws):
    ddb = boto3.resource("dynamodb", region_name="eu-west-1")
    table = ddb.create_table(
        TableName=ORDERS_TABLE,
        KeySchema=[{"AttributeName": "orderId", "KeyType": "HASH"}],
        AttributeDefinitions=[
            {"AttributeName": "orderId", "AttributeType": "S"},
            {"AttributeName": "userId", "AttributeType": "S"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "userId-index",
                "KeySchema": [{"AttributeName": "userId", "KeyType": "HASH"}],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    return table


@pytest.fixture
def idempotency_table(aws):
    ddb = boto3.resource("dynamodb", region_name="eu-west-1")
    return ddb.create_table(
        TableName=IDEMPOTENCY_TABLE,
        KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )


@pytest.fixture
def orders_queue(aws):
    sqs = boto3.client("sqs", region_name="eu-west-1")
    return sqs.create_queue(QueueName="test-orders-queue")["QueueUrl"]


@pytest.fixture
def order_events_queue(aws):
    sqs = boto3.client("sqs", region_name="eu-west-1")
    return sqs.create_queue(QueueName="test-order-events")["QueueUrl"]


@pytest.fixture
def settings(orders_table, idempotency_table, orders_queue, order_events_queue) -> Settings:
    return Settings(
        env="local",
        app_region="eu-west-1",
        orders_table_name=ORDERS_TABLE,
        idempotency_table_name=IDEMPOTENCY_TABLE,
        orders_queue_url=orders_queue,
        order_events_queue_url=order_events_queue,
        _env_file=None,
    )


@pytest.fixture
def repository(settings) -> OrderRepository:
    return OrderRepository(settings)


@pytest.fixture
def publisher(settings) -> OrderCommandPublisher:
    return OrderCommandPublisher(settings)


@pytest.fixture
def client(settings, repository, publisher) -> TestClient:
    return TestClient(create_app(settings=settings, repository=repository, publisher=publisher))


def auth_header(sub: str = "user-1", *groups: str) -> dict:
    token = jwt.encode(
        {"sub": sub, "cognito:username": sub, "cognito:groups": list(groups) or ["customer"]},
        "unused",
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}
