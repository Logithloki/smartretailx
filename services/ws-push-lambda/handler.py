"""WebSocket push Lambda - EventBridge -> apigatewaymanagementapi.

Invoked by the EventBridge rule that receives `order.status-changed`
events forwarded from the DynamoDB Streams -> Pipes -> bus path
(pipes.tf). The event `detail` carries the raw stream record; we pull the
order's userId out of NewImage, look up that user's active WebSocket
connections in DynamoDB, and postToConnection for each.

Stale connection handling (viva talking point):

  postToConnection raises GoneException (HTTP 410) when the target
  connection has already been closed by the client but the disconnect
  handler has not yet observed the fact (or the row never got cleaned).
  We catch 410 and delete the row inline - the push is best-effort, so a
  missing target is not an error condition, just cleanup opportunity.

  Any other client-side error (400, 403) is logged and skipped; a 5xx is
  re-raised so EventBridge retries the whole invocation. The event is not
  DLQ-worthy on a partial failure - one bad connection should not stop
  the fan-out.

Table access:

  The websocket-connections table has no userId GSI (adding one would
  modify existing infra, which is out of scope for this chunk), so we
  Scan with a userId filter. Scan is acceptable at demo scale: the table
  holds one row per active browser tab, expected under 100 rows total.
  The report notes `userId-index` as the production upgrade.
"""

from __future__ import annotations

import json
import logging
import os

import boto3
from boto3.dynamodb.conditions import Attr
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

_ddb = None
_apigw = None


def _table():
    global _ddb
    if _ddb is None:
        _ddb = boto3.resource("dynamodb", region_name=os.environ.get("APP_REGION", "eu-west-1"))
    return _ddb.Table(os.environ["WS_CONNECTIONS_TABLE"])


def _api_client():
    """Client for `apigatewaymanagementapi` is unusual: the endpoint URL is
    the specific stage's HTTPS callback URL, not the default AWS endpoint.
    Built once per cold start."""
    global _apigw
    if _apigw is None:
        endpoint = os.environ["WS_CALLBACK_ENDPOINT"]
        _apigw = boto3.client(
            "apigatewaymanagementapi",
            endpoint_url=endpoint,
            region_name=os.environ.get("APP_REGION", "eu-west-1"),
        )
    return _apigw


def _reset() -> None:
    """Test hook."""
    global _ddb, _apigw
    _ddb = None
    _apigw = None


def _extract_status_change(event: dict) -> dict | None:
    """Pull orderId/userId/status out of the EventBridge detail.

    Pipes forwards the DynamoDB stream record as-is inside `detail`, so the
    field values are in the marshalled `{"S": "..."}` form.
    """
    detail = event.get("detail") or {}
    new_image = ((detail.get("dynamodb") or {}).get("NewImage") or {})
    if not new_image:
        return None

    def s(key: str) -> str | None:
        raw = new_image.get(key) or {}
        return raw.get("S") if isinstance(raw, dict) else None

    order_id = s("orderId")
    user_id = s("userId")
    status = s("status")
    if not (order_id and user_id and status):
        return None
    return {"orderId": order_id, "userId": user_id, "status": status}


def _connections_for(user_id: str) -> list[str]:
    ids: list[str] = []
    kwargs: dict = {"FilterExpression": Attr("userId").eq(user_id)}
    while True:
        response = _table().scan(**kwargs)
        ids.extend(item["connectionId"] for item in response.get("Items", []))
        token = response.get("LastEvaluatedKey")
        if not token:
            return ids
        kwargs["ExclusiveStartKey"] = token


def _post(connection_id: str, payload: dict) -> str:
    """Returns 'delivered' | 'stale' | 'skipped'."""
    try:
        _api_client().post_to_connection(
            ConnectionId=connection_id,
            Data=json.dumps(payload).encode("utf-8"),
        )
        return "delivered"
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        status_code = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if code == "GoneException" or status_code == 410:
            _table().delete_item(Key={"connectionId": connection_id})
            logger.info("ws push: stale %s pruned", connection_id)
            return "stale"
        if status_code and 400 <= status_code < 500:
            logger.warning("ws push: client error %s on %s", code, connection_id)
            return "skipped"
        # 5xx: re-raise so EventBridge retries.
        raise


def lambda_handler(event: dict, context) -> dict:
    change = _extract_status_change(event)
    if not change:
        logger.info("ws push: not a status-change event, ignoring")
        return {"pushed": 0, "reason": "not a status-change event"}

    payload = {
        "type": "order.status-changed",
        "orderId": change["orderId"],
        "status": change["status"],
    }

    connections = _connections_for(change["userId"])
    if not connections:
        logger.info("ws push: no active connections for user %s", change["userId"])
        return {"pushed": 0, "userId": change["userId"], "orderId": change["orderId"]}

    counts = {"delivered": 0, "stale": 0, "skipped": 0}
    for connection_id in connections:
        outcome = _post(connection_id, payload)
        counts[outcome] += 1

    logger.info(
        "ws push: order=%s user=%s %s",
        change["orderId"],
        change["userId"],
        counts,
    )
    return {"pushed": counts["delivered"], "counts": counts, "orderId": change["orderId"]}
