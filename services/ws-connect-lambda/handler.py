"""WebSocket `$connect` handler.

Writes the (connectionId, userId) pair into the websocket-connections
DynamoDB table. userId is read from the authorizer context - the request
authorizer already validated the Cognito JWT and passed `sub` through, so
this handler doesn't decode the token a second time.

The connection row carries an unauthenticated TTL so a client that dies
without cleanly closing (browser tab killed, laptop shut, network flap)
does not leave an orphan row. If the disconnect route fires, we delete
proactively; TTL is the backstop, not the primary cleanup.

Powertools is intentionally not used here: this Lambda's zip must stay
small because API Gateway rejects the WebSocket upgrade if the $connect
handler takes too long (~30 s hard limit, but tail latency matters far
below that). Basic boto3 keeps cold-start under 400 ms in practice.
"""

from __future__ import annotations

import logging
import os
import time

import boto3

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# TTL horizon: 24 hours. Well past any realistic browser session; the
# happy-path disconnect deletes long before this fires.
_TTL_SECONDS = 24 * 60 * 60

_ddb = None


def _table():
    global _ddb
    if _ddb is None:
        _ddb = boto3.resource("dynamodb", region_name=os.environ.get("APP_REGION", "eu-west-1"))
    return _ddb.Table(os.environ["WS_CONNECTIONS_TABLE"])


def _reset() -> None:
    """Test hook - drop the cached client so a fresh table can be bound."""
    global _ddb
    _ddb = None


def _extract_user(event: dict) -> tuple[str, str | None]:
    ctx = event.get("requestContext", {}) or {}
    connection_id = ctx.get("connectionId", "")
    authorizer = ctx.get("authorizer") or {}
    user_id = authorizer.get("userId") or None
    return connection_id, user_id


def lambda_handler(event: dict, context) -> dict:
    connection_id, user_id = _extract_user(event)

    if not connection_id:
        # Should never happen - API Gateway always supplies a connectionId
        # on $connect. Log loudly and reject so the client sees the failure
        # rather than a silent black-hole.
        logger.error("ws connect: missing connectionId in requestContext")
        return {"statusCode": 500, "body": "missing connectionId"}

    if not user_id:
        # Authorizer approved without a sub - this is a misconfiguration,
        # not a hostile client. Refuse to record an unattributed connection
        # because the push Lambda relies on userId to fan out.
        logger.error("ws connect: authorizer context missing userId")
        return {"statusCode": 401, "body": "unauthenticated"}

    now = int(time.time())
    _table().put_item(
        Item={
            "connectionId": connection_id,
            "userId": user_id,
            "connectedAt": now,
            "ttl": now + _TTL_SECONDS,
        }
    )
    logger.info("ws connected: %s (user=%s)", connection_id, user_id)
    return {"statusCode": 200, "body": "connected"}
