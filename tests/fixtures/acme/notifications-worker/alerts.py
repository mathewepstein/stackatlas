import os

import boto3

sns = boto3.client("sns")
TOPIC = os.environ.get("ALERTS_TOPIC_ARN")


def send(message):
    sns.publish(TopicArn=TOPIC, Message=message)
