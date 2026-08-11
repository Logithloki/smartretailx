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

  Connections are queried through `userId-index`. This prevents a push
  invocation from reading connection rows owned by other customers and
  keeps lookup cost proportional to the recipient's active sessions.

  A catalogue price refresh is deliberately different: it contains only
  product identifiers and a monotonically increasing promotion revision, then
  broadcasts to all connections. The browser refetches the catalogue through
  the authenticated HTTP API. No order, user, customer, or price data crosses
  the public branch.
"""

from __future__ import annotations

import json
import logging
import os

import boto3
from boto3.dynamodb.conditions import Key
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
    if event.get("source") != "smartretailx.orders" or event.get("detail-type") not in {"order.status-changed", "fulfilment-status-changed"}:
        return None
    detail = event.get("detail") or {}
    if event.get("detail-type") == "fulfilment-status-changed":
        payload = detail.get("payload") or {}
        order_id = payload.get("orderId")
        user_id = payload.get("userId")
        fulfilment_status = payload.get("fulfilmentStatus")
        if detail.get("eventType") != "fulfilment-status-changed" or not all(isinstance(v, str) for v in (order_id, user_id, fulfilment_status)):
            return None
        return {
            "kind": "fulfilment", "orderId": order_id, "userId": user_id,
            "fulfilmentStatus": fulfilment_status, "correlationId": detail.get("correlationId"),
        }
    new_image = ((detail.get("dynamodb") or {}).get("NewImage") or {})
    if not new_image:
        return None

    def s(key: str) -> str | None:
        raw = new_image.get(key) or {}
        return raw.get("S") if isinstance(raw, dict) else None

    order_id = s("orderId")
    user_id = s("userId")
    status = s("status")
    correlation_id = s("correlationId")
    if not (order_id and user_id and status):
        return None
    return {
        "kind": "order",
        "orderId": order_id,
        "userId": user_id,
        "status": status,
        "correlationId": correlation_id,
    }


def _extract_price_refresh(event: dict) -> dict | None:
    """Return a deliberately public, non-sensitive catalogue refresh notice.

    The incoming Pipe event is a trusted internal stream record, but this
    boundary still rejects private identifiers defensively. The public payload
    is constructed from a whitelist rather than forwarding any input object.
    """
    event_kind = (event.get("source"), event.get("detail-type"))
    if event_kind not in {
        ("smartretailx.promotions", "promotion.price-refresh"),
        ("smartretailx.products", "product.price-refresh"),
    }:
        return None
    detail = event.get("detail") or {}
    new_image = ((detail.get("dynamodb") or {}).get("NewImage") or {})
    if not new_image or any(field in new_image for field in ("userId", "orderId", "customerId", "email", "address")):
        return None
    if event_kind[0] == "smartretailx.promotions":
        raw_ids = (new_image.get("productIds") or {}).get("L")
        raw_revision = (new_image.get("lifecycleVersion") or {}).get("N")
        if not isinstance(raw_ids, list) or raw_revision is None:
            return None
        product_ids = [entry.get("S") for entry in raw_ids if isinstance(entry, dict) and isinstance(entry.get("S"), str)]
        # An empty list means a category-scoped promotion changed and the SPA
        # must refetch the whole catalogue. It remains a safe public signal.
        if len(product_ids) != len(raw_ids):
            return None
    else:
        product_id = (new_image.get("productId") or {}).get("S")
        raw_revision = (new_image.get("priceEventVersion") or {}).get("N")
        if not isinstance(product_id, str) or not product_id or raw_revision is None:
            return None
        product_ids = [product_id]
    try:
        revision = int(raw_revision)
    except (TypeError, ValueError):
        return None
    return {"productIds": product_ids, "revision": revision}


def _connections_for(user_id: str) -> list[str]:
    ids: list[str] = []
    kwargs: dict = {
        "IndexName": "userId-index",
        "KeyConditionExpression": Key("userId").eq(user_id),
        "ProjectionExpression": "connectionId",
    }
    while True:
        response = _table().query(**kwargs)
        ids.extend(item["connectionId"] for item in response.get("Items", []))
        token = response.get("LastEvaluatedKey")
        if not token:
            return ids
        kwargs["ExclusiveStartKey"] = token


def _all_connections() -> list[str]:
    """Paginated public-broadcast lookup. Only connection IDs are projected."""
    ids: list[str] = []
    kwargs: dict = {"ProjectionExpression": "connectionId"}
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
    refresh = _extract_price_refresh(event)
    if refresh:
        payload = {
            "type": "catalogue.price-refresh",
            "productIds": refresh["productIds"],
            "revision": refresh["revision"],
        }
        connections = _all_connections()
        counts = {"delivered": 0, "stale": 0, "skipped": 0}
        for connection_id in connections:
            outcome = _post(connection_id, payload)
            counts[outcome] += 1
        logger.info("ws push: public catalogue refresh %s", counts)
        return {"pushed": counts["delivered"], "counts": counts, "public": True}

    change = _extract_status_change(event)
    if not change:
        logger.info("ws push: not a status-change event, ignoring")
        return {"pushed": 0, "reason": "not a status-change event"}

    payload = (
        {
            "type": "order.fulfilment-status-changed",
            "orderId": change["orderId"],
            "fulfilmentStatus": change["fulfilmentStatus"],
            "correlationId": change["correlationId"],
        }
        if change["kind"] == "fulfilment"
        else {
            "type": "order.status-changed",
            "orderId": change["orderId"],
            "status": change["status"],
            "correlationId": change["correlationId"],
        }
    )

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
