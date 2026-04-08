"""
Shiny WebSocket response capture utilities.
Shiny communicates via WebSocket using SockJS transport.

SockJS frame format:
  'o'         open
  'h'         heartbeat
  'a["..."]'  array containing JSON-encoded Shiny message
  'c[n,"msg"] close

Shiny message payload (inside the array):
  {"values": {"outputId": <value>}, "errors": {}, "inputMessages": []}
"""
import asyncio
import json
import logging
from typing import Any

log = logging.getLogger(__name__)


def _parse_sockjs_frame(raw: str) -> dict | None:
    """Parse a SockJS frame and return the inner Shiny message dict, or None."""
    if not raw or raw in ("o", "h"):
        return None
    try:
        if raw.startswith("a"):
            # a["<json-string>"]  — array of one JSON-encoded string
            arr = json.loads(raw[1:])
            if not arr:
                return None
            return json.loads(arr[0])
        else:
            return json.loads(raw)
    except Exception:
        return None


class ShinyResponseCapture:
    """
    Attaches to all WebSockets on a Playwright page and waits for
    specific Shiny output IDs to arrive in 'values'.
    """

    def __init__(self, page, debug: bool = False):
        self._page = page
        self._debug = debug
        self._listeners: dict[str, asyncio.Future] = {}
        self._attached = False
        self._all_output_ids: set[str] = set()

    def attach(self):
        """Call once after creating the page to start listening."""
        if self._attached:
            return
        self._attached = True
        self._page.on("websocket", self._on_websocket)

    def _on_websocket(self, ws):
        log.debug(f"[WS] connected: {ws.url}")
        ws.on("framereceived", self._on_frame)

    def _on_frame(self, frame):
        # Playwright 1.x: framereceived passes data directly as str (or bytes)
        raw = frame if isinstance(frame, str) else frame.payload
        msg = _parse_sockjs_frame(raw)
        if msg is None:
            return

        if self._debug:
            log.info(f"[WS FRAME] keys={list(msg.keys())}")

        values = msg.get("values", {})
        if values:
            self._all_output_ids.update(values.keys())
            if self._debug:
                for k, v in values.items():
                    preview = str(v)[:120] if not isinstance(v, str) else v[:120]
                    log.info(f"  [WS VALUE] {k} = {preview!r}")

        for output_id, future in list(self._listeners.items()):
            if output_id in values and not future.done():
                log.debug(f"[WS] captured output: {output_id}")
                future.set_result(values[output_id])

    async def wait_for_output(self, output_id: str, timeout: float = 90.0) -> Any:
        """
        Returns the value Shiny sends for `output_id`.
        Raises asyncio.TimeoutError if nothing arrives within `timeout` seconds.
        """
        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        self._listeners[output_id] = future
        try:
            return await asyncio.wait_for(asyncio.shield(future), timeout=timeout)
        except asyncio.TimeoutError:
            log.warning(
                f"[WS] Timeout waiting for '{output_id}'. "
                f"Output IDs seen so far: {sorted(self._all_output_ids)}"
            )
            raise
        finally:
            self._listeners.pop(output_id, None)
