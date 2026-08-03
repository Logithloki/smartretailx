"""Minimal WebSocket client for CW-5 evidence.

Connects to the SmartRetailX WebSocket API using a Cognito JWT passed
in the query string (WS APIs cannot use Authorization headers), then
prints every frame received until stdin is closed or a 60s idle timeout
elapses. Also proves the authorizer accepts a valid token.

Usage (PowerShell):
    $env:WS_URL, $env:CUSTOMER_TOKEN must be set.
    python scripts/ws-listen.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import time

import websockets

WS_URL = os.environ["WS_URL"]
TOKEN = os.environ["CUSTOMER_TOKEN"]
TIMEOUT = int(os.environ.get("WS_TIMEOUT", "90"))


async def main() -> None:
    url = f"{WS_URL}?token={TOKEN}"
    print(f"[t=0.0s] connecting to {WS_URL} ...", flush=True)
    started = time.time()

    async with websockets.connect(url) as ws:
        elapsed = time.time() - started
        print(f"[t={elapsed:.2f}s] connected (authorizer accepted token)", flush=True)
        print(f"[t={elapsed:.2f}s] waiting up to {TIMEOUT}s for status push ...", flush=True)

        try:
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=TIMEOUT)
                elapsed = time.time() - started
                print(f"[t={elapsed:.2f}s] << {msg}", flush=True)
        except asyncio.TimeoutError:
            elapsed = time.time() - started
            print(f"[t={elapsed:.2f}s] idle timeout - closing", flush=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except websockets.exceptions.InvalidStatus as e:
        # Authorizer denial arrives as an HTTP 4xx before the WS upgrade completes.
        print(f"INVALID_STATUS: {e}", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
