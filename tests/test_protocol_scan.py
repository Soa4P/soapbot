"""Finding the protocol end instead of asking the operator to describe it.

The behaviour that matters is the classification, not the HTTP wrapper: a logged-in OneBot
must be recognised *and named* (so the adapter's account_id can be filled in), a plain HTTP
server must not be mistaken for one, and a closed port must stay quiet. Each of those is a
different mistake the panel used to make by omission — it showed an empty table and let the
person work it out.
"""

from __future__ import annotations

import json
import socket
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

from soapbot.api.protocol import scan_ports


def _free_port() -> int:
    """A port nothing is listening on, closed immediately.

    Bound-then-closed rather than a constant: a hardcoded port is fine until the machine
    running the tests already uses it, and then the "closed" test fails for a reason that
    has nothing to do with this code.
    """
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def test_a_logged_in_onebot_is_found_and_named() -> None:
    from websockets.asyncio.server import serve

    async def handler(websocket) -> None:
        await websocket.recv()
        await websocket.send(
            json.dumps(
                {"status": "ok", "retcode": 0, "data": {"user_id": 10086, "nickname": "机器人"}}
            )
        )

    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        results = await scan_ports([port])

    found = results[0]
    assert found["kind"] == "onebot"
    assert found["account"] == "10086"
    # The panel applies this without asking the operator to retype anything.
    assert found["ws_url"] == f"ws://127.0.0.1:{port}"


async def test_an_http_server_is_not_called_onebot() -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib naming
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"napcat webui")

        def log_message(self, *args) -> None:  # silence the test output
            return

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    thread = Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        results = await scan_ports([port])
    finally:
        httpd.shutdown()

    assert results[0]["kind"] == "http"


async def test_a_closed_port_is_reported_as_closed_not_as_an_error() -> None:
    results = await scan_ports([_free_port()])
    assert results[0]["kind"] == "closed"


async def test_the_best_answer_comes_first() -> None:
    from websockets.asyncio.server import serve

    async def handler(websocket) -> None:
        await websocket.recv()
        await websocket.send(json.dumps({"status": "ok", "retcode": 0, "data": {"user_id": 7}}))

    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        results = await scan_ports([_free_port(), port])

    # The point of sorting: the row the operator should click is the first one.
    assert results[0]["kind"] == "onebot"
    assert results[-1]["kind"] == "closed"


async def test_duplicate_ports_are_probed_once() -> None:
    port = _free_port()
    results = await scan_ports([port, port, port])
    assert len(results) == 1
