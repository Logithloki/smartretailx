from __future__ import annotations

import boto3
import jwt
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from app.cache import ProductCache
from app.config import Settings
from app.main import create_app
from app.services import ProductRepository

PRODUCTS_TABLE = "test-products"
PROMOTIONS_TABLE = "test-promotions"


@pytest.fixture(autouse=True)
def aws_credentials(monkeypatch):
    for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        monkeypatch.setenv(key, "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-west-1")


@pytest.fixture
def aws():
    with mock_aws():
        yield


@pytest.fixture
def products_table(aws):
    ddb = boto3.resource("dynamodb", region_name="eu-west-1")
    table = ddb.create_table(
        TableName=PRODUCTS_TABLE,
        KeySchema=[{"AttributeName": "productId", "KeyType": "HASH"}],
        AttributeDefinitions=[
            {"AttributeName": "productId", "AttributeType": "S"},
            {"AttributeName": "category", "AttributeType": "S"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "category-index",
                "KeySchema": [{"AttributeName": "category", "KeyType": "HASH"}],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    for item in (
        {"productId": "prod-laptop-001", "productName": "MacBook Pro 14",
         "price": "1299.99", "category": "Electronics"},
        {"productId": "prod-mouse-002", "productName": "Magic Mouse",
         "price": "79.99", "category": "Accessories"},
        {"productId": "prod-monitor-003", "productName": "4K Monitor 27inch",
         "price": "599.99", "category": "Electronics"},
    ):
        from decimal import Decimal
        table.put_item(Item={**item, "price": Decimal(item["price"])})
    return table


@pytest.fixture
def promotions_table(aws):
    ddb = boto3.resource("dynamodb", region_name="eu-west-1")
    return ddb.create_table(
        TableName=PROMOTIONS_TABLE,
        KeySchema=[{"AttributeName": "promotionId", "KeyType": "HASH"}],
        AttributeDefinitions=[
            {"AttributeName": "promotionId", "AttributeType": "S"},
            {"AttributeName": "enabled", "AttributeType": "S"},
            {"AttributeName": "startsAt", "AttributeType": "S"},
        ],
        GlobalSecondaryIndexes=[{
            "IndexName": "enabled-startsAt-index",
            "KeySchema": [
                {"AttributeName": "enabled", "KeyType": "HASH"},
                {"AttributeName": "startsAt", "KeyType": "RANGE"},
            ],
            "Projection": {"ProjectionType": "ALL"},
        }],
        BillingMode="PAY_PER_REQUEST",
    )


@pytest.fixture
def settings(products_table, promotions_table) -> Settings:
    return Settings(
        env="local",
        app_region="eu-west-1",
        products_table_name=PRODUCTS_TABLE,
        promotions_table_name=PROMOTIONS_TABLE,
        cache_ttl_seconds=30,
        _env_file=None,
    )


@pytest.fixture
def cache(settings) -> ProductCache:
    return ProductCache(maxsize=settings.cache_max_size, ttl=settings.cache_ttl_seconds)


@pytest.fixture
def repository(settings) -> ProductRepository:
    return ProductRepository(settings)


@pytest.fixture
def client(settings, repository, cache) -> TestClient:
    return TestClient(create_app(settings=settings, repository=repository, cache=cache))


def auth_header(sub: str = "user-1", *groups: str) -> dict:
    token = jwt.encode(
        {"sub": sub, "cognito:username": sub, "cognito:groups": list(groups) or ["customer"]},
        "unused",
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}
