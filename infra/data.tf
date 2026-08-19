# ─── DYNAMODB TABLES (ADR-03 polyglot persistence) ────────────

# Orders: PITR + userId GSI + Streams for EventBridge Pipes.
# Deliberately NO TTL — orders are financial records (backlog item 7).
resource "aws_dynamodb_table" "orders" {
  name                        = "${var.project_name}-orders"
  billing_mode                = "PAY_PER_REQUEST"
  hash_key                    = "orderId"
  deletion_protection_enabled = var.environment_name == "production"

  attribute {
    name = "orderId"
    type = "S"
  }

  attribute {
    name = "userId"
    type = "S"
  }

  global_secondary_index {
    name            = "userId-index"
    hash_key        = "userId"
    projection_type = "ALL"
  }

  stream_enabled   = true
  stream_view_type = "NEW_AND_OLD_IMAGES"

  point_in_time_recovery {
    enabled = true
  }

  tags = {
    Name = "${var.project_name}-orders"
  }
}

# Transactional outbox for order-created commands. The API writes this row in
# the same TransactWriteItems call as the order; the stream publisher owns SQS.
resource "aws_dynamodb_table" "order_outbox" {
  name                        = "${var.project_name}-order-outbox"
  billing_mode                = "PAY_PER_REQUEST"
  hash_key                    = "eventId"
  deletion_protection_enabled = var.environment_name == "production"

  attribute {
    name = "eventId"
    type = "S"
  }

  stream_enabled   = true
  stream_view_type = "NEW_IMAGE"

  point_in_time_recovery {
    enabled = true
  }

  tags = {
    Name = "${var.project_name}-order-outbox"
  }
}

# Products: category GSI; Streams NEW_AND_OLD_IMAGES is a hard prerequisite
# for the ap-south-1 Global Table replica (backlog item 20, ADR-07).
resource "aws_dynamodb_table" "products" {
  name                        = "${var.project_name}-products"
  billing_mode                = "PAY_PER_REQUEST"
  hash_key                    = "productId"
  deletion_protection_enabled = var.environment_name == "production"

  attribute {
    name = "productId"
    type = "S"
  }

  attribute {
    name = "category"
    type = "S"
  }

  global_secondary_index {
    name            = "category-index"
    hash_key        = "category"
    projection_type = "ALL"
  }

  stream_enabled   = true
  stream_view_type = "NEW_AND_OLD_IMAGES"

  point_in_time_recovery {
    enabled = true
  }

  # ADR-07 APAC expansion cell (products only, no personal data, GDPR-lawful)
  replica {
    region_name = "ap-south-1"
  }

  tags = {
    Name = "${var.project_name}-products"
  }
}

# Product Service owns promotional writes. The enabled/start key permits the
# Order pricing read model to query candidate promotions without a Scan.
resource "aws_dynamodb_table" "promotions" {
  name                        = "${var.project_name}-promotions"
  billing_mode                = "PAY_PER_REQUEST"
  hash_key                    = "promotionId"
  deletion_protection_enabled = var.environment_name == "production"

  attribute {
    name = "promotionId"
    type = "S"
  }

  attribute {
    name = "enabled"
    type = "S"
  }

  attribute {
    name = "startsAt"
    type = "S"
  }

  global_secondary_index {
    name            = "enabled-startsAt-index"
    hash_key        = "enabled"
    range_key       = "startsAt"
    projection_type = "ALL"
  }

  # Conditional lifecycle transitions are forwarded to EventBridge by a Pipe;
  # pricing still evaluates the time window directly at checkout.
  stream_enabled   = true
  stream_view_type = "NEW_AND_OLD_IMAGES"

  point_in_time_recovery { enabled = true }

  tags = { Name = "${var.project_name}-promotions" }
}

# TTL is correct here: idempotency records expire by design.
resource "aws_dynamodb_table" "idempotency" {
  name         = "${var.project_name}-idempotency"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "id"

  point_in_time_recovery {
    enabled = true
  }

  attribute {
    name = "id"
    type = "S"
  }

  ttl {
    attribute_name = "expiration"
    enabled        = true
  }

  tags = {
    Name = "${var.project_name}-idempotency"
  }
}

# TTL is correct here: stale connections expire by design.
resource "aws_dynamodb_table" "websocket_connections" {
  name         = "${var.project_name}-websocket-connections"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "connectionId"

  point_in_time_recovery {
    enabled = true
  }

  attribute {
    name = "connectionId"
    type = "S"
  }

  attribute {
    name = "userId"
    type = "S"
  }

  global_secondary_index {
    name            = "userId-index"
    hash_key        = "userId"
    projection_type = "KEYS_ONLY"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  tags = {
    Name = "${var.project_name}-websocket-connections"
  }
}

# ─── AURORA SERVERLESS v2 — PostgreSQL 16 (ADR-03) ────────────
# min 0 = auto-pause to £0 compute when idle · max 2 = cost circuit breaker.
# manage_master_user_password replaces the old plaintext variable + manual
# Secrets Manager secret (backlog item 3). Not gated on `live`: parked cost
# is storage-only pennies while paused.

resource "aws_db_subnet_group" "aurora" {
  name       = "${var.project_name}-aurora"
  subnet_ids = aws_subnet.data[*].id

  tags = {
    Name = "${var.project_name}-aurora-subnet-group"
  }
}

resource "aws_rds_cluster" "inventory" {
  cluster_identifier              = "${var.project_name}-inventory"
  engine                          = "aurora-postgresql"
  engine_version                  = "16.14" # newest 16.x in eu-west-1, verified 2026-08-02 (auto-pause needs >= 16.3)
  database_name                   = "inventory"
  master_username                 = "smartretailx_admin"
  manage_master_user_password     = true
  db_subnet_group_name            = aws_db_subnet_group.aurora.name
  vpc_security_group_ids          = [aws_security_group.aurora.id]
  deletion_protection             = var.environment_name == "production"
  skip_final_snapshot             = var.environment_name != "production"
  final_snapshot_identifier       = var.environment_name == "production" ? "${var.project_name}-inventory-final" : null
  backup_retention_period         = var.environment_name == "production" ? 7 : 1
  preferred_backup_window         = "02:00-03:00"
  copy_tags_to_snapshot           = true
  enabled_cloudwatch_logs_exports = ["postgresql"]
  storage_encrypted               = true # diagram claims KMS at rest — this makes it true

  serverlessv2_scaling_configuration {
    min_capacity = 0
    max_capacity = 2
  }

  tags = {
    Name = "${var.project_name}-inventory"
  }
}

resource "aws_rds_cluster_instance" "writer" {
  identifier                 = "${var.project_name}-inventory-writer"
  cluster_identifier         = aws_rds_cluster.inventory.id
  instance_class             = "db.serverless"
  engine                     = aws_rds_cluster.inventory.engine
  engine_version             = aws_rds_cluster.inventory.engine_version
  auto_minor_version_upgrade = true

  tags = {
    Name = "${var.project_name}-inventory-writer"
  }
}

# A second production instance gives Aurora a real failover target. It is not
# created in lower environments; both production instances can still auto-pause
# with the cluster's min-0 capacity setting while the environment is parked.
resource "aws_rds_cluster_instance" "reader" {
  count                      = var.environment_name == "production" ? 1 : 0
  identifier                 = "${var.project_name}-inventory-reader"
  cluster_identifier         = aws_rds_cluster.inventory.id
  instance_class             = "db.serverless"
  engine                     = aws_rds_cluster.inventory.engine
  engine_version             = aws_rds_cluster.inventory.engine_version
  promotion_tier             = 1
  auto_minor_version_upgrade = true

  tags = {
    Name = "${var.project_name}-inventory-reader"
  }
}

# ─── S3 bucket for order summary PDFs ──────────────────────────
# Private bucket — no public access, SSE-S3 at rest, lifecycle to
# expire old summary versions. Access is exclusively via presigned
# URLs generated by the Order Service task role.

resource "aws_s3_bucket" "order_summaries" {
  bucket        = "${var.project_name}-order-summaries-${data.aws_caller_identity.current.account_id}"
  force_destroy = var.environment_name != "production"

  tags = {
    Name = "${var.project_name}-order-summaries"
  }
}

resource "aws_s3_bucket_public_access_block" "order_summaries" {
  bucket = aws_s3_bucket.order_summaries.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "order_summaries" {
  bucket = aws_s3_bucket.order_summaries.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "order_summaries" {
  bucket = aws_s3_bucket.order_summaries.id

  rule {
    id     = "expire-stale-summaries"
    status = "Enabled"
    filter {
      prefix = "orders/"
    }
    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }
}
