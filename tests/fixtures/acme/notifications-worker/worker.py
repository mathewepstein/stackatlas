import os

import requests

SLACK_WEBHOOK = "https://hooks.slack.com/services/example"
BILLING_URL = os.getenv("BILLING_URL")
MONGO_URL = "mongodb://prod-events-mongo.acme.internal:27017/events"

# legacy endpoint: "https://old.thirdparty.io/v0"


def notify(text: str) -> None:
    requests.post(SLACK_WEBHOOK, json={"text": text})
