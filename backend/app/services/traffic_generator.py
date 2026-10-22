"""Steady synthetic checkout traffic, so an outage is visible as lost orders."""

from __future__ import annotations

import logging
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

logging.basicConfig(level="INFO", format="%(asctime)s traffic %(message)s")
logger = logging.getLogger("traffic")
logging.getLogger("httpx").setLevel(logging.WARNING)

URL = os.environ.get("CHECKOUT_URL", "http://api:8000").rstrip("/") + "/checkout"
RPS = float(os.environ.get("TRAFFIC_RPS", "4"))


def one(i: int) -> None:
    try:
        httpx.post(URL, params={"customer_id": f"cust-{random.randint(1, 5000)}"}, timeout=10)
    except Exception as exc:  # noqa: BLE001
        if i % 50 == 0:
            logger.warning("checkout call failed: %s", exc)


def main() -> None:
    logger.info("sending %.1f checkouts/s to %s", RPS, URL)
    interval = 1.0 / RPS
    i = 0
    with ThreadPoolExecutor(max_workers=32) as pool:
        nxt = time.time()
        while True:
            pool.submit(one, i)
            i += 1
            nxt += interval
            time.sleep(max(0.0, nxt - time.time()))


if __name__ == "__main__":
    main()
