variable "env" {}

resource "aws_sqs_queue" "retry" {
  name = "${var.env}-notify-retry"
}

data "archive_file" "retry" {
  type        = "zip"
  source_file = "${path.module}/src/retry.py"
  output_path = "/tmp/retry.zip"
}

resource "aws_lambda_function" "retry" {
  function_name = "${local.env}-retry"
  filename      = data.archive_file.retry.output_path
  environment {
    variables = {
      RETRY_QUEUE_URL = aws_sqs_queue.retry.url
    }
  }
}

resource "aws_lambda_event_source_mapping" "notify_orders" {
  event_source_arn = aws_sqs_queue.orders.arn
  function_name    = aws_lambda_function.notify.arn
}

resource "aws_sns_topic_subscription" "alerts_to_orders" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "sqs"
  endpoint  = aws_sqs_queue.orders.arn
}

resource "aws_ssm_parameter" "orders_events_queue" {
  name  = "/config/ordersOrchestration_${local.env}/aws.sqs.orderEventsQueue"
  type  = "String"
  value = "${var.env}-orders-events"
}
