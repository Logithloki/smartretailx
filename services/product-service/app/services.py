"""DynamoDB access for the product catalogue."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from srx_common import Promotion as PricingPromotion, effective_price

from .models import (
    Product,
    Promotion,
    PromotionCreate,
    PromotionLifecycleState,
)

logger = logging.getLogger(__name__)


class ProductNotFound(Exception):
    pass


class ProductAlreadyExists(Exception):
    pass


class PromotionNotFound(Exception):
    pass


class PromotionAlreadyExists(Exception):
    pass


class ReconcileResult:
    def __init__(self, transition_ids: list[str]):
        self.transition_ids = transition_ids

    @property
    def transitions(self) -> int:
        return len(self.transition_ids)


def _to_item(product: Product) -> dict:
    item = {
        "productId": product.productId,
        "productName": product.productName,
        "price": Decimal(str(product.price)),
        "category": product.category,
        "active": product.active,
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
        active=item.get("active", True),
    )


class ProductRepository:
    def __init__(self, settings):
        self._settings = settings
        self._table = None
        self._promotions_table = None

    @property
    def table(self):
        if self._table is None:
            resource = boto3.resource("dynamodb", **self._settings.boto_kwargs())
            self._table = resource.Table(self._settings.products_table_name)
        return self._table

    @property
    def promotions_table(self):
        if self._promotions_table is None:
            resource = boto3.resource("dynamodb", **self._settings.boto_kwargs())
            self._promotions_table = resource.Table(self._settings.promotions_table_name)
        return self._promotions_table

    def priced(self, product: Product, now: datetime | None = None) -> Product:
        now = now or datetime.now(UTC)
        response = self.promotions_table.query(
            IndexName="enabled-startsAt-index",
            KeyConditionExpression=Key("enabled").eq("true") & Key("startsAt").lte(now.isoformat()),
        )
        items = list(response.get("Items", []))
        while response.get("LastEvaluatedKey"):
            response = self.promotions_table.query(
                IndexName="enabled-startsAt-index",
                KeyConditionExpression=Key("enabled").eq("true") & Key("startsAt").lte(now.isoformat()),
                ExclusiveStartKey=response["LastEvaluatedKey"],
            )
            items.extend(response.get("Items", []))
        promotions = [
            PricingPromotion(
                promotion_id=item["promotionId"], discount_percent=Decimal(str(item["discountPercent"])),
                scope=item["scope"], product_ids=tuple(item.get("productIds", [])),
                category=item.get("category"), enabled=item.get("enabled") == "true",
                starts_at=datetime.fromisoformat(item["startsAt"]), ends_at=datetime.fromisoformat(item["endsAt"]),
            ) for item in items if datetime.fromisoformat(item["endsAt"]) > now
        ]
        quote = effective_price(
            base_price=product.price, product_id=product.productId, category=product.category,
            promotions=promotions, now=now,
        )
        promotion = None if quote.promotion_id is None else {"promotionId": quote.promotion_id}
        return product.model_copy(update={
            "basePrice": quote.base_unit_price, "effectivePrice": quote.effective_unit_price,
            "promotion": promotion,
        })

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

        price_changed = "price" in changes
        if price_changed:
            values.update({":pending": "true", ":zero": Decimal(0), ":one": Decimal(1)})
            sets.extend(
                [
                    "priceEventPending = :pending",
                    "priceEventVersion = if_not_exists(priceEventVersion, :zero) + :one",
                ]
            )

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
        if price_changed:
            self._clear_product_price_event_pending(product_id, int(response["Attributes"]["priceEventVersion"]))
        return _from_item(response["Attributes"])

    def _clear_product_price_event_pending(self, product_id: str, version: int) -> None:
        """Clear only the marker version emitted by this successful price write.

        A later concurrent price update increments the version, so this cleanup
        cannot erase that newer update's pending refresh marker.
        """
        try:
            self.table.update_item(
                Key={"productId": product_id},
                UpdateExpression="SET priceEventPending = :cleared",
                ConditionExpression="priceEventVersion = :version",
                ExpressionAttributeValues={
                    ":cleared": "false",
                    ":version": Decimal(version),
                },
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise

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

    # ---- promotions ------------------------------------------------------

    @staticmethod
    def _promotion_state(item: dict, now: datetime) -> PromotionLifecycleState:
        if item.get("enabled") != "true":
            return PromotionLifecycleState.DISABLED
        if datetime.fromisoformat(item["endsAt"]) <= now:
            return PromotionLifecycleState.EXPIRED
        if datetime.fromisoformat(item["startsAt"]) <= now:
            return PromotionLifecycleState.ACTIVE
        return PromotionLifecycleState.SCHEDULED

    @staticmethod
    def _promotion_from_item(item: dict) -> Promotion:
        return Promotion(
            promotionId=item["promotionId"],
            name=item["name"],
            discountPercent=Decimal(str(item["discountPercent"])),
            scope=item["scope"],
            productIds=item.get("productIds", []),
            category=item.get("category"),
            startsAt=datetime.fromisoformat(item["startsAt"]),
            endsAt=datetime.fromisoformat(item["endsAt"]),
            enabled=item.get("enabled") == "true",
            lifecycleState=item.get("lifecycleState", "SCHEDULED"),
            lifecycleVersion=int(item.get("lifecycleVersion", 0)),
        )

    def create_promotion(self, promotion: PromotionCreate, now: datetime | None = None) -> Promotion:
        now = now or datetime.now(UTC)
        raw = promotion.model_dump()
        state = self._promotion_state({
            **raw,
            "enabled": "true" if raw["enabled"] else "false",
            "startsAt": raw["startsAt"].isoformat(),
            "endsAt": raw["endsAt"].isoformat(),
        }, now)
        item = {
            "promotionId": promotion.promotionId,
            "name": promotion.name,
            "discountPercent": promotion.discountPercent,
            "scope": promotion.scope.value,
            "productIds": promotion.productIds,
            "startsAt": promotion.startsAt.isoformat(),
            "endsAt": promotion.endsAt.isoformat(),
            "enabled": "true" if promotion.enabled else "false",
            "lifecycleState": state.value,
            "lifecycleVersion": 0,
            # Stream records with true are the only public-price refresh source.
            # It is cleared immediately after the write; at-least-once delivery is
            # harmless because clients refetch by product id.
            "priceEventPending": "true",
        }
        if promotion.category:
            item["category"] = promotion.category
        try:
            self.promotions_table.put_item(
                Item=item,
                ConditionExpression="attribute_not_exists(promotionId)",
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise PromotionAlreadyExists(promotion.promotionId) from exc
            raise
        self._clear_price_event_pending(promotion.promotionId, state, 0)
        return self._promotion_from_item(item)

    def create_promotion_from_payload(self, payload: dict, now: datetime | None = None) -> Promotion:
        """Narrow test seam for deterministic lifecycle transition tests."""
        return self.create_promotion(PromotionCreate(**payload), now=now)

    def get_promotion(self, promotion_id: str) -> dict | None:
        return self.promotions_table.get_item(Key={"promotionId": promotion_id}).get("Item")

    def list_promotions(self, limit: int = 100) -> list[Promotion]:
        # The admin view is bounded. The public checkout path never scans this table.
        response = self.promotions_table.scan(Limit=limit)
        return [self._promotion_from_item(item) for item in response.get("Items", [])]

    def update_promotion(self, promotion_id: str, changes: dict, now: datetime | None = None) -> Promotion:
        existing = self.get_promotion(promotion_id)
        if existing is None:
            raise PromotionNotFound(promotion_id)
        now = now or datetime.now(UTC)
        merged = {**existing, **changes}
        if "scope" in merged and hasattr(merged["scope"], "value"):
            merged["scope"] = merged["scope"].value
        if "discountPercent" in merged:
            merged["discountPercent"] = Decimal(str(merged["discountPercent"]))
        if "enabled" in merged:
            merged["enabled"] = "true" if merged["enabled"] is True else ("false" if merged["enabled"] is False else merged["enabled"])
        for field in ("startsAt", "endsAt"):
            if field in merged and isinstance(merged[field], datetime):
                merged[field] = merged[field].isoformat()
        # Re-validate the merged shape so an otherwise-valid PATCH cannot make
        # a CATEGORY promotion without category or invert its time window.
        PromotionCreate(**{key: merged.get(key) for key in PromotionCreate.model_fields})
        state = self._promotion_state(merged, now)
        version = int(existing.get("lifecycleVersion", 0)) + 1
        writable = ("name", "discountPercent", "scope", "productIds", "category", "startsAt", "endsAt", "enabled")
        names = {f"#f{i}": field for i, field in enumerate(writable) if field in merged}
        values = {f":v{i}": merged[field] for i, field in enumerate(writable) if field in merged}
        sets = [f"#f{i} = :v{i}" for i, field in enumerate(writable) if field in merged]
        names.update({"#state": "lifecycleState", "#version": "lifecycleVersion", "#pending": "priceEventPending"})
        values.update({":state": state.value, ":version": version, ":pending": "true"})
        sets.extend(["#state = :state", "#version = :version", "#pending = :pending"])
        try:
            response = self.promotions_table.update_item(
                Key={"promotionId": promotion_id},
                UpdateExpression="SET " + ", ".join(sets),
                ExpressionAttributeNames=names,
                ExpressionAttributeValues=values,
                ConditionExpression="attribute_exists(promotionId)",
                ReturnValues="ALL_NEW",
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise PromotionNotFound(promotion_id) from exc
            raise
        self._clear_price_event_pending(promotion_id, state, version)
        return self._promotion_from_item(response["Attributes"])

    def reconcile_promotions(self, now: datetime | None = None) -> ReconcileResult:
        """Advance only with conditional state changes, safe on every ECS task.

        Pricing does not consult this projection. It exists solely to generate
        a single stream record for catalogue refresh notifications.
        """
        now = now or datetime.now(UTC)
        response = self.promotions_table.query(
            IndexName="enabled-startsAt-index",
            KeyConditionExpression=Key("enabled").eq("true") & Key("startsAt").lte(now.isoformat()),
        )
        candidates = list(response.get("Items", []))
        while response.get("LastEvaluatedKey"):
            response = self.promotions_table.query(
                IndexName="enabled-startsAt-index",
                KeyConditionExpression=Key("enabled").eq("true") & Key("startsAt").lte(now.isoformat()),
                ExclusiveStartKey=response["LastEvaluatedKey"],
            )
            candidates.extend(response.get("Items", []))
        transitioned: list[str] = []
        for item in candidates:
            state = item.get("lifecycleState", PromotionLifecycleState.SCHEDULED.value)
            target: PromotionLifecycleState | None = None
            if state == PromotionLifecycleState.SCHEDULED and datetime.fromisoformat(item["startsAt"]) <= now:
                target = PromotionLifecycleState.ACTIVE
            elif state == PromotionLifecycleState.ACTIVE and datetime.fromisoformat(item["endsAt"]) <= now:
                target = PromotionLifecycleState.EXPIRED
            if target is None:
                continue
            next_version = int(item.get("lifecycleVersion", 0)) + 1
            try:
                self.promotions_table.update_item(
                    Key={"promotionId": item["promotionId"]},
                    UpdateExpression="SET lifecycleState = :target, lifecycleVersion = :version, priceEventPending = :pending",
                    ConditionExpression=(
                        "lifecycleState = :current AND enabled = :enabled "
                        "AND lifecycleVersion = :current_version"
                    ),
                    ExpressionAttributeValues={
                        ":target": target.value, ":version": next_version, ":pending": "true",
                        ":current": state, ":enabled": "true", ":current_version": int(item.get("lifecycleVersion", 0)),
                    },
                )
            except ClientError as exc:
                if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                    continue  # a different ECS task won this exact transition
                raise
            self._clear_price_event_pending(item["promotionId"], target, next_version)
            transitioned.append(item["promotionId"])
        return ReconcileResult(transitioned)

    def _clear_price_event_pending(
        self, promotion_id: str, state: PromotionLifecycleState, version: int
    ) -> None:
        self.promotions_table.update_item(
            Key={"promotionId": promotion_id},
            UpdateExpression="SET priceEventPending = :cleared",
            ConditionExpression="lifecycleState = :state AND lifecycleVersion = :version",
            ExpressionAttributeValues={":cleared": "false", ":state": state.value, ":version": version},
        )
