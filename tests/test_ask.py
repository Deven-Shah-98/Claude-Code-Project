import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from stadium_atlas import ask, server

VENUES = [
    {"id": "barclays", "name": "Barclays Center", "team": "Brooklyn Nets", "league": "NBA",
     "city": "Brooklyn", "state": "NY", "opened_year": 2012, "verdict": "signal", "caveats": [],
     "sc": {"effect_pct": 31.7141, "p_value": 0.0244, "pre_rmspe": 0.0034, "n_treated": 21},
     "robustness": {"effect_pct": 18.12, "p_value": 0.0976, "n_donors": 1158}},
    {"id": "oracle-park", "name": "Oracle Park", "team": "SF Giants", "league": "MLB",
     "city": "San Francisco", "state": "CA", "opened_year": 2000, "verdict": "no-data",
     "caveats": ["Not enough pre-opening or ZIP-level data to estimate."],
     "error": "insufficient pre-period"},
]


class FakeBeta:
    """Stands in for client.beta.messages; records the request and returns a canned reply."""

    def __init__(self, text=None, stop_reason="end_turn"):
        self.calls, self._text, self._stop = [], text, stop_reason
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw)
        block = SimpleNamespace(type="text", text=self._text)
        return SimpleNamespace(stop_reason=self._stop, content=[block])


def fake_client(**kw):
    return SimpleNamespace(beta=FakeBeta(**kw))


def test_context_has_exact_numbers_and_caveats():
    ctx = ask.build_context(VENUES)
    assert "effect=+31.7%" in ctx and "placebo_p=0.024" in ctx
    assert "density_matched_effect=+18.1%" in ctx
    assert "no estimate (insufficient pre-period)" in ctx
    assert ctx == ask.build_context(list(reversed(VENUES)))  # deterministic -> cacheable prefix


def test_ask_request_shape_and_parsing():
    c = fake_client(text=json.dumps({"answer": "Barclays.", "venue_ids": ["barclays", "ghost"]}))
    out = ask.ask("Which venue stands out?", VENUES, client=c)
    assert out.text == "Barclays." and out.venue_ids == ["barclays"]  # unknown ids dropped
    call = c.beta.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["fallbacks"] == "default" and call["betas"] == ["server-side-fallback-2026-07-01"]
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert "Barclays Center" in call["system"][0]["text"]
    assert call["messages"] == [{"role": "user", "content": "Which venue stands out?"}]


def test_ask_handles_refusal_and_bad_json():
    assert ask.ask("x", VENUES, client=fake_client(text="", stop_reason="refusal")).refused
    assert ask.ask("x", VENUES, client=fake_client(text="plain words")).text == "plain words"


@pytest.mark.parametrize("q", ["", "   ", "x" * 501])
def test_ask_rejects_bad_questions(q):
    with pytest.raises(ValueError):
        ask.ask(q, VENUES, client=fake_client(text="{}"))


def _post(port, body, raw=False):
    conn = HTTPConnection("127.0.0.1", port)
    conn.request("POST", "/api/ask", body if raw else json.dumps(body))
    r = conn.getresponse()
    return r.status, json.loads(r.read())


@pytest.fixture
def live_server():
    server.Handler.venues = VENUES
    server.Handler.hits.clear()
    server.Handler.asker = staticmethod(lambda q, v: ask.Answer(f"echo:{q}", ["barclays"]))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_address[1]
    httpd.shutdown()
    server.Handler.asker = staticmethod(ask.ask)


def test_server_ok_bad_json_and_rate_limit(live_server):
    assert _post(live_server, {"question": "hi"}) == (
        200, {"answer": "echo:hi", "venue_ids": ["barclays"], "refused": False})
    assert _post(live_server, "{nope", raw=True)[0] == 400
    assert _post(live_server, "[1]", raw=True)[0] == 400
    for _ in range(server.RATE_LIMIT):
        status, _ = _post(live_server, {"question": "again"})
    assert status == 429


def test_missing_credentials_is_a_distinct_error():
    def no_creds(**kw):
        raise TypeError('"Could not resolve authentication method. Expected one of api_key"')

    def other_bug(**kw):
        raise TypeError("something else")

    wrap = lambda f: SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=f)))
    with pytest.raises(ask.MissingCredentials):
        ask.ask("hi", VENUES, client=wrap(no_creds))
    with pytest.raises(TypeError):  # unrelated bugs must not be disguised as a config problem
        ask.ask("hi", VENUES, client=wrap(other_bug))


def test_server_returns_503_when_unconfigured(live_server):
    def boom(q, v):
        raise ask.MissingCredentials("x")

    server.Handler.asker = staticmethod(boom)
    status, body = _post(live_server, {"question": "hi"})
    assert status == 503 and "ANTHROPIC_API_KEY" in body["error"]
