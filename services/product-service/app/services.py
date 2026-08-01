"""DynamoDB access for the product catalogue."""

from __future__ import annotations

import logging
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from .models import Product

logger = logging.getLogger(__name__)


class ProductNotFound(Exception):
    pass


class ProductAlreadyExists(Exception):
    pass


def _to_item(product: Product) -> dict:
    item = {
        "productId": product.productId,
        "productName": product.productName,
        "price": Decimal(str(product.price)),
        "category": product.category,
    }
    if product.description:
        item["description"] = product.description
    return item


def _from_item(item: dict) -> Product:
    return Product(
        productId=item["productId"],
        productName=item.get("productName", ""),
        price=Decimal(str(item["price"])),
        category=item.get("category", "uncategorised"),
        description=item.get("description"),
    )


class ProductRepository:
    def __init__(self, settings):
        self._settings = settings
        self._table = None

    @property
    def table(self):
        if self._table is None:
            resource = boto3.resource("dynamodb", **self._settings.boto_kwargs())
            self._table = resource.Table(self._settings.products_table_name)
        return self._table

    def get(self, product_id: str) -> Product | None:
        item = self.table.get_item(Key={"productId": product_id}).get("Item")
        return _from_item(item) if item else None

    def list(self, category: str | None = None, limit: int = 50) -> list[Product]:
        if category:
            # category-index GSI, not a filtered Scan: a Scan reads the whole
            # table and then throws most of it away.
            response = self.table.query(
                IndexName="category-index",
                KeyConditionExpression=Key("category").eq(category),
                Limit=limit,
            )
        else:
            # The full catalogue is small and has no partition key to query on,
            # so a bounded Scan is honest here. It would not scale, and the
            # report says so.
            response = self.table.scan(Limit=limit)
        return [_from_item(item) for item in response.get("Items", [])]

    def create(self, product: Product) -> Product:
        try:
            self.table.put_item(
                Item=_to_item(product),
                ConditionExpression="attribute_not_exists(productId)",
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise ProductAlreadyExists(product.productId) from exc
            raise
        return product

    def update(self, product_id: str, changes: dict) -> Product:
        if not changes:
            existing = self.get(product_id)
            if existing is None:
                raise ProductNotFound(product_id)
            return existing

        names, values, sets = {}, {}, []
        for index, (field, value) in enumerate(changes.items()):
            names[f"#f{index}"] = field
            values[f":v{index}"] = Decimal(str(value)) if field == "price" else value
            sets.append(f"#f{index} = :v{index}")

        try:
            response = self.table.update_item(
                Key={"productId": product_id},
                UpdateExpression="SET " + ", ".join(sets),
                ExpressionAttributeNames=names,
                ExpressionAttributeValues=values,
                ConditionExpression="attribute_exists(productId)",
                ReturnValues="ALL_NEW",
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise ProductNotFound(product_id) from exc
            raise
        return _from_item(response["Attributes"])

    def delete(self, product_id: str) -> None:
        try:
            self.table.delete_item(
                Key={"productId": product_id},
                ConditionExpression="attribute_exists(productId)",
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise ProductNotFound(product_id) from exc
            raise
