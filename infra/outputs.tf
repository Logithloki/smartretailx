output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.main.id
}

output "public_subnet_ids" {
  description = "Public subnet IDs"
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "Private subnet IDs for microservices"
  value       = aws_subnet.private[*].id
}

output "data_subnet_ids" {
  description = "Data subnet IDs for Aurora"
  value       = aws_subnet.data[*].id
}

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = aws_ecs_cluster.main.name
}

output "ecr_repository_urls" {
  description = "ECR repository URLs for all services"
  value = {
    for k, v in aws_ecr_repository.services : k => v.repository_url
  }
}

output "orders_table_name" {
  description = "DynamoDB orders table name"
  value       = aws_dynamodb_table.orders.name
}

output "orders_table_stream_arn" {
  description = "DynamoDB orders table stream ARN for EventBridge Pipes"
  value       = aws_dynamodb_table.orders.stream_arn
}

output "products_table_stream_arn" {
  description = "DynamoDB products table stream ARN (Global Table prerequisite)"
  value       = aws_dynamodb_table.products.stream_arn
}

output "orders_queue_url" {
  description = "SQS orders queue URL"
  value       = aws_sqs_queue.orders.url
}

output "orders_dlq_url" {
  description = "SQS orders DLQ URL"
  value       = aws_sqs_queue.orders_dlq.url
}

output "sns_order_confirmed_arn" {
  description = "SNS order confirmed topic ARN"
  value       = aws_sns_topic.order_confirmed.arn
}

output "orders_event_bus_arn" {
  description = "EventBridge bus ARN receiving order.status-changed events from Pipes"
  value       = aws_cloudwatch_event_bus.orders.arn
}

output "orders_event_bus_name" {
  description = "EventBridge bus name (used when adding rules on this bus)"
  value       = aws_cloudwatch_event_bus.orders.name
}

output "websocket_api_id" {
  description = "WebSocket API v2 ID"
  value       = aws_apigatewayv2_api.ws.id
}

output "websocket_endpoint" {
  description = "WebSocket URL (null when parked). Clients connect wss://.../prod?token=<JWT>"
  value       = one(aws_apigatewayv2_stage.ws[*].invoke_url)
}

output "alerts_topic_arn" {
  description = "SNS alerts topic ARN (subscribe your email manually)"
  value       = aws_sns_topic.alerts.arn
}

output "aurora_cluster_endpoint" {
  description = "Aurora writer endpoint"
  value       = aws_rds_cluster.inventory.endpoint
}

output "aurora_master_secret_arn" {
  description = "ARN of the RDS-managed master credentials secret (inject via ECS secrets.valueFrom)"
  value       = aws_rds_cluster.inventory.master_user_secret[0].secret_arn
  sensitive   = true
}

output "alb_dns_name" {
  description = "Internal ALB DNS name (null when parked)"
  value       = one(aws_lb.main[*].dns_name)
}

output "api_endpoint" {
  description = "HTTP API base URL - all service calls go through here"
  value       = aws_apigatewayv2_stage.default.invoke_url
}

output "vpc_link_id" {
  description = "API Gateway VPC Link ID"
  value       = aws_apigatewayv2_vpc_link.main.id
}

output "cognito_user_pool_id" {
  description = "Cognito user pool ID"
  value       = aws_cognito_user_pool.main.id
}

output "cognito_app_client_id" {
  description = "Cognito SPA app client ID (public client - no secret)"
  value       = aws_cognito_user_pool_client.spa.id
}

output "cognito_issuer" {
  description = "JWT issuer URL used by the API Gateway authorizer and service middleware"
  value       = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.main.id}"
}

output "cognito_hosted_ui_url" {
  description = "Cognito hosted-UI login URL (SPA authorization-code + PKCE entry point)"
  value       = "https://${aws_cognito_user_pool_domain.main.domain}.auth.${var.aws_region}.amazoncognito.com"
}

output "alb_security_group_id" {
  description = "ALB security group ID"
  value       = aws_security_group.alb.id
}

output "vpc_link_security_group_id" {
  description = "VPC Link security group ID (for the Week-1-D4 API Gateway VPC Link)"
  value       = aws_security_group.vpc_link.id
}

output "ecs_tasks_security_group_id" {
  description = "ECS tasks security group ID"
  value       = aws_security_group.ecs_tasks.id
}

output "aurora_security_group_id" {
  description = "Aurora security group ID"
  value       = aws_security_group.aurora.id
}
