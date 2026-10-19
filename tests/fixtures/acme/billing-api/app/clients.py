import os

import httpx

PRICING_URL = os.environ.get("PRICING_URL", "http://pricing-svc:8080")
INVENTORY_URL = os.environ["INVENTORY_URL"]


def quote(sku: str) -> dict:
    """Fetch a quote. Docs: https://wiki.thirdparty.io/pricing"""
    return httpx.get(f"{PRICING_URL}/quote/{sku}").json()
