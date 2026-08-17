# ─── EVENTBRIDGE PIPES — the differentiator (ADR + CLAUDE.md) ─
#
# DynamoDB Streams → EventBridge bus with **zero glue Lambda**. Everything
# from stream read, filter, to bus put is native AWS wiring; the report and
# viva both lean on this as the "innovative service choice" story.
#
# Component status: **needs CW-3a validation on real AWS** — LocalStack
# Community cannot emulate EventBridge Pipes (CLAUDE.md cost-guardrails).
#
# Filter design note (viva answer):
#   The spec asks for "MODIFY where NEW_IMAGE.status != OLD_IMAGE.status".
#   EventBridge filter patterns do NOT support cross-field comparison
#   (you cannot match on "field A not equal to field B"). The closest
#   zero-glue approximation is to match on the specific NEW_IMAGE.status
#   values we care about, PENDING → CONFIRMED and PENDING → REJECTED.
#   Since the Order Service only ever UpdateItem's the status column, every
#   MODIFY IS a status change — so this pattern captures exactly the
#   transitions worth pushing over the WebSocket, with no false positives
#   under normal operation. If we ever need true "field changed" semantics,
#   the escape hatch is a Pipes enrichment step, not glue in the pipeline.

resource "aws_cloudwatch_event_bus" "orders" {
  name = "${var.project_name}-events"

  tags = {
    Name = "${var.project_name}-events"
  }
}

# Pipes assumes this role to read the stream and put events on the bus.
data "aws_iam_policy_document" "pipes_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["pipes.amazonaws.com"]
    }
    condition {
      # Confused-deputy protection: only Pipes acting for THIS account may
      # assume the role. Belt-and-braces since Pipes is the only caller.
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_iam_role" "pipes" {
  name               = "${var.project_name}-pipes"
  assume_role_policy = data.aws_iam_policy_document.pipes_assume.json
}

resource "aws_iam_role_policy" "pipes" {
  name = "pipes-source-and-target"
  role = aws_iam_role.pipes.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # Stream read on the orders table stream only — no access to the base
        # table, no access to any other stream.
        Sid    = "ReadOrdersStream"
        Effect = "Allow"
        Action = [
          "dynamodb:DescribeStream",
          "dynamodb:GetRecords",
          "dynamodb:GetShardIterator",
          "dynamodb:ListStreams",
        ]
        Resource = [aws_dynamodb_table.orders.stream_arn]
      },
      {
        Sid    = "ReadPromotionsStream"
        Effect = "Allow"
        Action = [
          "dynamodb:DescribeStream",
          "dynamodb:GetRecords",
          "dynamodb:GetShardIterator",
          "dynamodb:ListStreams",
        ]
        Resource = [aws_dynamodb_table.promotions.stream_arn]
      },
      {
        Sid    = "ReadProductsStream"
        Effect = "Allow"
        Action = [
          "dynamodb:DescribeStream",
          "dynamodb:GetRecords",
          "dynamodb:GetShardIterator",
          "dynamodb:ListStreams",
        ]
        Resource = [aws_dynamodb_table.products.stream_arn]
      },
      {
        Sid      = "PutOnOrdersBus"
        Effect   = "Allow"
        Action   = ["events:PutEvents"]
        Resource = [aws_cloudwatch_event_bus.orders.arn]
      },
    ]
  })
}

# The pipe itself is gated on `live` — Pipes bills per record processed, and
# a parked stack should not be draining the stream. Follows the same toggle
# pattern as NAT / ALB listener / ECS desired_count.
# ─── EventBridge rule -> push Lambda ─────────────────────────
# Closes the Pipes -> bus -> Lambda -> postToConnection loop:
#
#   DDB Streams (MODIFY, terminal status)
#     -> Pipes filter
#     -> orders bus (detail-type: order.status-changed, source: smartretailx.orders)
#     -> THIS rule
#     -> push Lambda
#     -> apigatewaymanagementapi.postToConnection(connectionId, data)
#
# Rule + target + invoke permission are all gated on `live` - the push
# Lambda is idle in a parked stack, and Pipes is not draining the stream
# either, so there is nothing for a rule to catch.
#
# Needs CW-3a validation on real AWS.

resource "aws_cloudwatch_event_rule" "order_status_changed" {
  count          = var.live ? 1 : 0
  name           = "${var.project_name}-order-status-changed"
  description    = "Route Pipes-forwarded order status changes to the WebSocket push Lambda"
  event_bus_name = aws_cloudwatch_event_bus.orders.name

  event_pattern = jsonencode({
    source        = ["smartretailx.orders"]
    "detail-type" = ["order.status-changed", "fulfilment-status-changed"]
  })

  tags = {
    Name = "${var.project_name}-order-status-changed"
  }
}

resource "aws_cloudwatch_event_target" "push" {
  count          = var.live ? 1 : 0
  rule           = aws_cloudwatch_event_rule.order_status_changed[0].name
  event_bus_name = aws_cloudwatch_event_bus.orders.name
  target_id      = "push-lambda"
  arn            = aws_lambda_alias.ws_push.arn
}

resource "aws_lambda_permission" "push_from_events" {
  count         = var.live ? 1 : 0
  statement_id  = "AllowInvokeFromEventBridgeOrderStatusRule"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ws_push.function_name
  qualifier     = aws_lambda_alias.ws_push.name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.order_status_changed[0].arn
}

# These stream-driven notifications are deliberately not a pricing authority.
# The client receives identifiers only and refetches; the Order Service always
# evaluates enabled/startsAt/endsAt when creating its immutable price snapshot.
resource "aws_cloudwatch_event_rule" "promotion_price_refresh" {
  count          = var.live ? 1 : 0
  name           = "${var.project_name}-promotion-price-refresh"
  description    = "Route catalogue price refresh records to the WebSocket push Lambda"
  event_bus_name = aws_cloudwatch_event_bus.orders.name

  event_pattern = jsonencode({
    source        = ["smartretailx.promotions", "smartretailx.products"]
    "detail-type" = ["promotion.price-refresh", "product.price-refresh"]
  })
}

resource "aws_cloudwatch_event_target" "promotion_push" {
  count          = var.live ? 1 : 0
  rule           = aws_cloudwatch_event_rule.promotion_price_refresh[0].name
  event_bus_name = aws_cloudwatch_event_bus.orders.name
  target_id      = "push-lambda-catalogue"
  arn            = aws_lambda_alias.ws_push.arn
}

resource "aws_lambda_permission" "push_from_promotion_events" {
  count         = var.live ? 1 : 0
  statement_id  = "AllowInvokeFromEventBridgePromotionPriceRule"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ws_push.function_name
  qualifier     = aws_lambda_alias.ws_push.name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.promotion_price_refresh[0].arn
}

resource "aws_pipes_pipe" "order_status" {
  count    = var.live ? 1 : 0
  name     = "${var.project_name}-order-status"
  role_arn = aws_iam_role.pipes.arn
  source   = aws_dynamodb_table.orders.stream_arn
  target   = aws_cloudwatch_event_bus.orders.arn

  depends_on = [aws_iam_role_policy.pipes]

  source_parameters {
    dynamodb_stream_parameters {
      # LATEST: we do not want to replay the entire order history when the
      # pipe is unparked; the WebSocket clients are ephemeral and only care
      # about live transitions.
      starting_position      = "LATEST"
      batch_size             = 1
      maximum_retry_attempts = 3
      # Explicit values keep the AWS Pipes UpdatePipe validation happy across
      # every environment; without them the provider sends implicit defaults
      # that older pipes reject with MaximumBatchingWindow/RecordAge ranges.
      maximum_batching_window_in_seconds = 1
      maximum_record_age_in_seconds      = 300
    }

    filter_criteria {
      filter {
        # See the header comment for why this is not a cross-field compare.
        pattern = jsonencode({
          eventName = ["MODIFY"]
          dynamodb = {
            NewImage = {
              status = {
                S = ["CONFIRMED", "REJECTED", "CANCEL_PENDING", "CANCELLED"]
              }
            }
          }
        })
      }
    }
  }

  target_parameters {
    eventbridge_event_bus_parameters {
      # Stable identity so the downstream EventBridge rule (Week 5 chunk 1
      # commit 5) can pattern-match without depending on the raw DDB record
      # shape.
      detail_type = "order.status-changed"
      source      = "smartretailx.orders"
    }
  }

  tags = {
    Name = "${var.project_name}-order-status"
  }
}

resource "aws_pipes_pipe" "promotion_price_refresh" {
  count    = var.live ? 1 : 0
  name     = "${var.project_name}-promotion-price-refresh"
  role_arn = aws_iam_role.pipes.arn
  source   = aws_dynamodb_table.promotions.stream_arn
  target   = aws_cloudwatch_event_bus.orders.arn

  depends_on = [aws_iam_role_policy.pipes]

  source_parameters {
    dynamodb_stream_parameters {
      starting_position                  = "LATEST"
      batch_size                         = 1
      maximum_retry_attempts             = 3
      maximum_batching_window_in_seconds = 1
      maximum_record_age_in_seconds      = 300
    }

    filter_criteria {
      filter {
        # The reconciler writes this marker only with a successful conditional
        # transition, then clears it in a follow-up record. Pipe's at-least-
        # once delivery remains safe because the browser merely refetches.
        pattern = jsonencode({
          eventName = ["INSERT", "MODIFY"]
          dynamodb = {
            NewImage = {
              priceEventPending = { S = ["true"] }
            }
          }
        })
      }
    }
  }

  target_parameters {
    eventbridge_event_bus_parameters {
      detail_type = "promotion.price-refresh"
      source      = "smartretailx.promotions"
    }
  }

  tags = { Name = "${var.project_name}-promotion-price-refresh" }
}

resource "aws_pipes_pipe" "product_price_refresh" {
  count    = var.live ? 1 : 0
  name     = "${var.project_name}-product-price-refresh"
  role_arn = aws_iam_role.pipes.arn
  source   = aws_dynamodb_table.products.stream_arn
  target   = aws_cloudwatch_event_bus.orders.arn

  depends_on = [aws_iam_role_policy.pipes]

  source_parameters {
    dynamodb_stream_parameters {
      starting_position                  = "LATEST"
      batch_size                         = 1
      maximum_retry_attempts             = 3
      maximum_batching_window_in_seconds = 1
      maximum_record_age_in_seconds      = 300
    }

    filter_criteria {
      filter {
        # The write record containing the marker triggers a safe identifier-
        # only browser refetch. The follow-up clear record is filtered out.
        pattern = jsonencode({
          eventName = ["MODIFY"]
          dynamodb = {
            NewImage = {
              priceEventPending = { S = ["true"] }
            }
          }
        })
      }
    }
  }

  target_parameters {
    eventbridge_event_bus_parameters {
      detail_type = "product.price-refresh"
      source      = "smartretailx.products"
    }
  }

  tags = { Name = "${var.project_name}-product-price-refresh" }
}
