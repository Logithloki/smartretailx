"""Idempotent order creation.

Why this exists: the client retries (a flaky mobile connection, a double-tapped
button, an SQS-driven retry upstream) must not create two orders. The
Idempotency-Key header makes POST /v1/orders safely repeatable.

Three properties worth defending in the viva:

1.  Keys are scoped per user. The stored id is "<subject>#<key>", so one
    customer's key can never collide with - or replay - another's.
2.  The request body is fingerprinted. Reusing a key with different items is a
    client bug, and returning the *old* order would silently discard the new
    request, so it is rejected instead.
3.  The claim is a conditional write, not read-then-write. Two concurrent
    duplicates race on `attribute_not_exists(id)`; exactly one wins and the
    loser gets 409 rather than both creating an order.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from enum import Enum

import boto3

logger = logging.getLogger(__name__)


class IdempotencyState(str, Enum):
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


class IdempotencyConflict(Exception):
    """Same key, different payload."""


class IdempotencyInProgress(Exception):
    """A concurrent request holds this key."""


@dataclass(frozen=True)
class Replay:
    orderId: str


def fingerprint(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


class IdempotencyStore:
    def __init__(self, settings):
        self._settings = settings
        self._table = None

    @property
    def table(self):
        if self._table is None:
            resource = boto3.resource("dynamodb", **self._settings.boto_kwargs())
            self._table = resource.Table(self._settings.idempotency_table_name)
        return self._table

    @staticmethod
    def _record_id(user_id: str, key: str) -> str:
        return f"{user_id}#{key}"

    def claim(self, user_id: str, key: str, payload_hash: str) -> Replay | None:
        """Reserve the key. Returns None if this caller may proceed, or a
        Replay pointing at the order created by the original request."""
        record_id = self._record_id(user_id, key)
        expiration = int(time.time()) + self._settings.idempotency_ttl_seconds

        try:
            self.table.put_item(
                Item={
                    "id": record_id,
                    "state": IdempotencyState.IN_PROGRESS.value,
                    "payloadHash": payload_hash,
                    "expiration": expiration,
                },
                ConditionExpression="attribute_not_exists(id)",
            )
            return None
        except self.table.meta.client.exceptions.ConditionalCheckFailedException:
            pass  # someone got here first - fall through and inspect it

        existing = self.table.get_item(Key={"id": record_id}).get("Item")
        if existing is None:
            # The record expired between the failed put and this read. Treating
            # it as a fresh request is the safe reading: at worst the caller
            # retries a long-expired key.
            return None

        if existing.get("payloadHash") != payload_hash:
            raise IdempotencyConflict(key)

        if existing.get("state") == IdempotencyState.COMPLETED.value:
            logger.info("idempotent replay", extra={"orderId": existing.get("orderId")})
            return Replay(orderId=existing["orderId"])

        raise IdempotencyInProgress(key)

    def complete(self, user_id: str, key: str, order_id: str) -> None:
        self.table.update_item(
            Key={"id": self._record_id(user_id, key)},
            UpdateExpression="SET #s = :s, orderId = :o",
            ExpressionAttributeNames={"#s": "state"},
            ExpressionAttributeValues={
                ":s": IdempotencyState.COMPLETED.value,
                ":o": order_id,
            },
        )

    def release(self, user_id: str, key: str) -> None:
        """Drop the claim when order creation failed, so a genuine retry with
        the same key is not permanently wedged at 409."""
        self.table.delete_item(Key={"id": self._record_id(user_id, key)})
