"""Tiny server: serves the built web app and a rate-limited POST /api/ask."""
from __future__ import annotations

import json
import time
from collections import defaultdict, deque
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar

import anthropic

from . import ask as ask_mod

RATE_LIMIT = 10        # requests per client per minute; protects the API key's spend
MAX_BODY = 4096


class Handler(SimpleHTTPRequestHandler):
    venues: ClassVar[list[dict]] = []
    asker = staticmethod(ask_mod.ask)
    hits: ClassVar[dict] = defaultdict(deque)

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _limited(self) -> bool:
        q, now = self.hits[self.client_address[0]], time.monotonic()
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= RATE_LIMIT:
            return True
        q.append(now)
        return False

    def do_POST(self):
        if self.path != "/api/ask":
            return self._json(404, {"error": "not found"})
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            return self._json(413, {"error": "request too large"})
        if self._limited():
            return self._json(429, {"error": "too many questions; try again in a minute"})
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self._json(400, {"error": "invalid JSON"})
        if not isinstance(body, dict):
            return self._json(400, {"error": "expected a JSON object"})
        try:
            ans = self.asker(body.get("question", ""), self.venues)
        except ValueError as e:
            return self._json(400, {"error": str(e)})
        except ask_mod.MissingCredentials:
            return self._json(503, {"error": "The question box isn't configured on this server "
                                             "(set ANTHROPIC_API_KEY and restart `atlas serve`)."})
        except anthropic.APIError:  # upstream failure: don't leak details to the browser
            return self._json(502, {"error": "the question service is unavailable right now"})
        self._json(200, {"answer": ans.text, "venue_ids": ans.venue_ids, "refused": ans.refused})


def serve(web_dir: str = "web/dist", data_json: str = "web/public/data/venues.json",
          port: int = 8000) -> None:
    Handler.venues = ask_mod.load_venues(data_json)
    server = ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, directory=web_dir))
    print(f"Serving {web_dir} on http://127.0.0.1:{port}")
    server.serve_forever()
