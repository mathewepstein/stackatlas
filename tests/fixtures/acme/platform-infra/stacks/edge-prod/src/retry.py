import os

import boto3

sqs = boto3.client("sqs")
QUEUE = os.environ["RETRY_QUEUE_URL"]


def handler(event, context):
    sqs.send_message(QueueUrl=QUEUE, MessageBody="retry")
