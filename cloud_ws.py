"""
CloudChatClient — persistent WebSocket client Hub → Cloud.

Fase 3 of V2 architecture (docs/AI_ARCHITECTURE_V2.md §4, §8.2, §9.2).

Replaces the per-turn httpx.stream(POST) SSE call with a single WebSocket
connection that lives for the entire browser session. Benefits:

- One connection per session instead of one per turn.
- Bidirectional: tool_results travel back on the same socket.
- WS ping/pong every 20 s keeps the stream alive through OpenAI's silent
  planning phases — no more gateway idle-timeout HTML error pages.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

import websockets
import websockets.exceptions
from websockets.asyncio.client import ClientConnection, connect

logger = logging.getLogger(__name__)


class CloudChatClient:
    """Persistent WebSocket client to Cloud's assistant chat endpoint.

    Opens once per browser session (on Hub WS connect), stays alive until
    browser WS closes. Handles bidirectional JSON messaging.

    Usage::

        client = CloudChatClient(url="wss://...", hub_jwt="eyJ...")
        await client.connect()
        await client.send({"type": "chat_turn", ...})
        async for msg in client.receive():
            ...  # relay to browser
        await client.close()
    """

    def __init__(self, cloud_ws_url: str, hub_jwt: str) -> None:
        self.url = cloud_ws_url
        self.hub_jwt = hub_jwt
        self._ws: ClientConnection | None = None

    async def connect(self) -> None:
        """Open the WebSocket connection to Cloud."""
        headers = {"Authorization": f"Bearer {self.hub_jwt}"}
        self._ws = await connect(
            self.url,
            additional_headers=headers,
            ping_interval=20,
            ping_timeout=10,
            max_size=10 * 1024 * 1024,  # 10 MB — plenty for chat payloads
        )
        logger.info("[HUB→CLOUD WS] Connected to %s", self.url)

    async def send(self, message: dict[str, Any]) -> None:
        """Send a JSON message to Cloud."""
        if self._ws is None:
            raise RuntimeError("CloudChatClient: WebSocket not connected — call connect() first")
        await self._ws.send(json.dumps(message))

    async def receive(self) -> AsyncGenerator[dict[str, Any]]:
        """Async generator that yields parsed JSON messages from Cloud.

        Exits cleanly when Cloud closes the connection.
        """
        if self._ws is None:
            raise RuntimeError("CloudChatClient: WebSocket not connected — call connect() first")
        try:
            async for raw in self._ws:
                if isinstance(raw, bytes):
                    raw = raw.decode()
                try:
                    yield json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning("[HUB→CLOUD WS] Non-JSON message received: %.200s", raw)
        except websockets.exceptions.ConnectionClosed as exc:
            logger.info(
                "[HUB→CLOUD WS] Cloud closed connection: code=%s reason=%s",
                exc.rcvd.code if exc.rcvd else "?",
                exc.rcvd.reason if exc.rcvd else "?")
        except Exception:
            logger.exception("[HUB→CLOUD WS] Unexpected error in receive()")

    async def close(self) -> None:
        """Close the WebSocket connection gracefully."""
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            finally:
                self._ws = None
            logger.info("[HUB→CLOUD WS] Connection closed")


async def stream_turn_via_ws(
    *,
    cloud_ws_url: str,
    hub_jwt: str,
    payload: dict[str, Any]) -> AsyncGenerator[dict[str, Any]]:
    """One-shot helper: open WS, send one chat_turn payload, yield all responses, close.

    This is the V2 equivalent of the legacy _stream_via_sse() per-turn call.
    Used by _ws_handle_chat to process a single agentic-loop iteration.

    Yields all JSON messages until a ``done`` or ``error`` message is received,
    or Cloud closes the connection.
    """
    client = CloudChatClient(cloud_ws_url=cloud_ws_url, hub_jwt=hub_jwt)
    await client.connect()
    try:
        await client.send(payload)
        async for msg in client.receive():
            yield msg
            msg_type = msg.get("type", "")
            if msg_type in ("done", "error"):
                break
    finally:
        await client.close()
