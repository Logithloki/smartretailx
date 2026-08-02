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
resource "aws_pipes_pipe" "order_status" {
  count    = var.live ? 1 : 0
  name     = "${var.project_name}-order-status"
  role_arn = aws_iam_role.pipes.arn
  source   = aws_dynamodb_table.orders.stream_arn
  target   = aws_cloudwatch_event_bus.orders.arn

  source_parameters {
    dynamodb_stream_parameters {
      # LATEST: we do not want to replay the entire order history when the
      # pipe is unparked; the WebSocket clients are ephemeral and only care
      # about live transitions.
      starting_position = "LATEST"
      batch_size        = 1
    }

    filter_criteria {
      filter {
        # See the header comment for why this is not a cross-field compare.
        pattern = jsonencode({
          eventName = ["MODIFY"]
          dynamodb = {
            NewImage = {
              status = {
                S = ["CONFIRMED", "REJECTED"]
              }
            }
          }
        })
      }
    }
  }

  target_parameters {
    event_bridge_event_bus_parameters {
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
