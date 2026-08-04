# ─── DYNAMODB TABLES (ADR-03 polyglot persistence) ────────────

# Orders: PITR + userId GSI + Streams for EventBridge Pipes.
# Deliberately NO TTL — orders are financial records (backlog item 7).
resource "aws_dynamodb_table" "orders" {
  name         = "${var.project_name}-orders"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "orderId"

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

# Products: category GSI; Streams NEW_AND_OLD_IMAGES is a hard prerequisite
# for the ap-south-1 Global Table replica (backlog item 20, ADR-07).
resource "aws_dynamodb_table" "products" {
  name         = "${var.project_name}-products"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "productId"

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

  # ADR-07 APAC expansion cell (products only, no personal data, GDPR-lawful)
  replica {
    region_name = "ap-south-1"
  }

  tags = {
    Name = "${var.project_name}-products"
  }
}

# TTL is correct here: idempotency records expire by design.
resource "aws_dynamodb_table" "idempotency" {
  name         = "${var.project_name}-idempotency"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "id"

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

  attribute {
    name = "connectionId"
    type = "S"
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
  cluster_identifier          = "${var.project_name}-inventory"
  engine                      = "aurora-postgresql"
  engine_version              = "16.14" # newest 16.x in eu-west-1, verified 2026-08-02 (auto-pause needs >= 16.3)
  database_name               = "inventory"
  master_username             = "smartretailx_admin"
  manage_master_user_password = true
  db_subnet_group_name        = aws_db_subnet_group.aurora.name
  vpc_security_group_ids      = [aws_security_group.aurora.id]
  skip_final_snapshot         = true
  storage_encrypted           = true # diagram claims KMS at rest — this makes it true

  serverlessv2_scaling_configuration {
    min_capacity = 0
    max_capacity = 2
  }

  tags = {
    Name = "${var.project_name}-inventory"
  }
}

resource "aws_rds_cluster_instance" "writer" {
  identifier         = "${var.project_name}-inventory-writer"
  cluster_identifier = aws_rds_cluster.inventory.id
  instance_class     = "db.serverless"
  engine             = aws_rds_cluster.inventory.engine
  engine_version     = aws_rds_cluster.inventory.engine_version

  tags = {
    Name = "${var.project_name}-inventory-writer"
  }
}
