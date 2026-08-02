"""WebSocket `$disconnect` handler.

Fires on clean close (client called ws.close()) OR on server-detected
disconnect (heartbeat failure, browser tab killed). API Gateway does not
distinguish the two - we always remove the row.

Deletes with no condition: if the row is already gone (TTL fired first,
or a duplicate disconnect event) that is the correct end state anyway.
DeleteItem is idempotent on a missing key.
"""

from __future__ import annotations

import logging
import os

import boto3

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

_ddb = None


def _table():
    global _ddb
    if _ddb is None:
        _ddb = boto3.resource("dynamodb", region_name=os.environ.get("APP_REGION", "eu-west-1"))
    return _ddb.Table(os.environ["WS_CONNECTIONS_TABLE"])


def _reset() -> None:
    """Test hook."""
    global _ddb
    _ddb = None


def lambda_handler(event: dict, context) -> dict:
    connection_id = (event.get("requestContext") or {}).get("connectionId", "")
    if not connection_id:
        logger.error("ws disconnect: missing connectionId")
        # 200 anyway - $disconnect ignores the response body; anything other
        # than 500 leaves API Gateway happy. Logs carry the diagnostic.
        return {"statusCode": 200}

    _table().delete_item(Key={"connectionId": connection_id})
    logger.info("ws disconnected: %s", connection_id)
    return {"statusCode": 200}
