locals {
  env         = "prod"
  tld         = "acme.com"
  orders_host = "${local.env}-orders-orchestration.${local.tld}"
  alb         = var.internal_alb_listener_arn
  settings = {
    "/config/global_${local.env}/orders.url" = {
      type  = "String"
      value = "https://orders.acme.com"
    }
  }
}

variable "internal_alb_listener_arn" {
  type = string
}

variable "pricing_path" {
  default = "/v1/pricing"
}

resource "aws_apigatewayv2_api" "public" {
  name          = "public-api"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_domain_name" "public" {
  domain_name = "edge.acme.com"
}

resource "aws_apigatewayv2_api_mapping" "public" {
  api_id      = aws_apigatewayv2_api.public.id
  domain_name = aws_apigatewayv2_domain_name.public.id
}

resource "aws_apigatewayv2_integration" "orders" {
  api_id           = aws_apigatewayv2_api.public.id
  integration_type = "HTTP_PROXY"
  connection_type  = "VPC_LINK"
  integration_uri  = local.alb
  request_parameters = {
    "overwrite:header.Host" = local.orders_host
  }
  tls_config {
    server_name_to_verify = local.orders_host
  }
}

resource "aws_apigatewayv2_route" "orders" {
  api_id    = aws_apigatewayv2_api.public.id
  route_key = "POST /v1/orders/{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.orders.id}"
}

data "archive_file" "notify" {
  type        = "zip"
  source_file = "${path.module}/src/notify.py"
  output_path = "/tmp/notify.zip"
}

resource "aws_lambda_function" "notify" {
  function_name = "${local.env}-notify"
  filename      = data.archive_file.notify.output_path
  handler       = "notify.handler"
  runtime       = "python3.12"
  environment {
    variables = {
      BILLING_URL   = "https://billing-api.acme.com"
      PRICING_PATH  = var.pricing_path
      API_TOKEN_SSM = "/secret/notify/token"
    }
  }
}

resource "aws_db_instance" "orders" {
  identifier = "${local.env}-orders-db"
  engine     = "postgres"
}

resource "aws_elasticache_replication_group" "cache" {
  replication_group_id = "${local.env}-orders-cache"
  engine               = "redis"
}

resource "aws_sqs_queue" "orders" {
  name = "orders-events"
}

resource "aws_sns_topic" "alerts" {
  name = "${local.env}-alerts"
}

resource "aws_s3_bucket" "assets" {
  bucket = "acme-assets-${local.env}"
}

resource "aws_ssm_parameter" "pricing_url" {
  name  = "/config/orders-service_${local.env}/pricing.url"
  type  = "String"
  value = "https://pricing.acme.com"
}

resource "aws_codebuild_project" "orders" {
  name = "orders-service-build"
  source {
    type      = "GITHUB"
    location  = "https://github.com/acme/orders-service.git"
    buildspec = "buildspec.yml"
  }
  environment {
    environment_variable {
      name  = "ECR_REPO_NAME"
      value = "acme/orders-service"
    }
  }
}
