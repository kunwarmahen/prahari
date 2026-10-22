"""The page's API and the inlet, on a real local socket.

The bias these tests encode: THE INLET'S KEY CAN ONLY KNOCK. It goes
into phone apps and webhook settings, where keys leak, so with it
nothing can be read, made or deleted -- and without the page's token
the API answers nobody, because any web page can send a request to
127.0.0.1.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

import pytest

from helpers import FakeCaller, FakeNotifier, make_clock
from prahari import watches
from prahari.http import Api, PrahariServer

TOKEN = "page-token-0123456789"
KEY = "inlet-key-0123456789ab"


@pytest.fixture
def served(tmp_path):
    notifier = FakeNotifier()
    store, clock = make_clock(tmp_path, FakeCaller("Last 47"), notifier=notifier)
    server = PrahariServer(Api(store, clock, tmp_path), TOKEN, KEY, port=0)
    server.start()
    yield server, store, notifier
    server.stop()
    clock.close()


def call(server, method, path, body=None, *, token=TOKEN, kind="application/json",
         raw=None):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None
                                        else None)
    headers = {"Content-Type": kind}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(server.url.rstrip("/") + path, data=data,
                                     method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


def listener(store):
    return watches.create(store, name="Mum", listen="whatsapp", pick={"json": "title"},
                          when={"contains": "Mum"})


class TestTheToken:
    def test_no_token_no_answer(self, served):
        server, _, _ = served
        assert call(server, "GET", "/api/watches", token="")[0] == 401
        assert call(server, "GET", "/api/watches", token="wrong-token-123456")[0] == 401

    def test_the_inlet_key_cannot_read_or_change(self, served):
        server, store, _ = served
        listener(store)
        for method, path in (("GET", "/api/watches"), ("GET", "/api/inlet"),
                             ("POST", "/api/watches")):
            assert call(server, method, path, {}, token=KEY)[0] == 401

    def test_the_page_token_does_not_open_the_inlet(self, served):
        server, store, _ = served
        listener(store)
        assert call(server, "POST", "/inlet/whatsapp", {"title": "Mum"})[0] == 401

    def test_the_page_itself_needs_no_token(self, served):
        server, _, _ = served
        with urllib.request.urlopen(server.url, timeout=10) as response:
            assert b"<title>Prahari</title>" in response.read()


class TestTheApi:
    def test_make_try_and_remove(self, served):
        server, store, _ = served
        recipe = {"check": {"tool": "web_fetch", "args": {"url": "https://x.example"}},
                  "pick": {"number": ""}, "when": {"below": 50}, "every": "1h"}
        status, said = call(server, "POST", "/api/preview", recipe)
        assert status == 200 and said["holds"] is True
        status, made = call(server, "POST", "/api/watches", {**recipe, "name": "ALAB"})
        assert status == 201 and made["sentence"].startswith("every hour")
        status, listed = call(server, "GET", "/api/watches")
        assert [w["name"] for w in listed["watches"]] == ["ALAB"]
        assert call(server, "PATCH", f"/api/watches/{made['id']}",
                    {"every": "3h"})[1]["every"] == "3h"
        assert call(server, "DELETE", f"/api/watches/{made['id']}")[0] == 200
        assert call(server, "GET", f"/api/watches/{made['id']}")[0] == 404

    def test_a_mistake_is_a_400_in_words(self, served):
        server, _, _ = served
        status, said = call(server, "POST", "/api/watches",
                            {"name": "x", "check": {"tool": "t", "args": {}},
                             "when": {"belw": 1}, "every": "1h"})
        assert status == 400 and "belw" in said["detail"]

    def test_the_inlet_address_and_key_for_the_page(self, served):
        server, store, _ = served
        listener(store)
        status, said = call(server, "GET", "/api/inlet")
        assert said == {"url": server.url + "inlet/", "key": KEY, "words": ["whatsapp"]}


class TestTheInlet:
    def wait_for(self, store, watch_id):
        for _ in range(100):
            looks = store.looks(watch_id)
            if looks and looks[0].outcome != "running":
                return looks[0]
            time.sleep(0.02)
        raise AssertionError("nothing was heard")

    def test_json_heard_at_once_and_fired_behind(self, served):
        server, store, notifier = served
        watch = listener(store)
        status, said = call(server, "POST", "/inlet/whatsapp",
                            {"title": "Mum", "text": "call me"}, token=KEY)
        assert status == 202 and said == {"heard_by": 1}
        assert self.wait_for(store, watch.id).outcome == "fired"
        assert notifier.sent and "Mum" in notifier.sent[0][1]

    def test_the_key_in_the_address_for_a_sender_without_headers(self, served):
        server, store, _ = served
        watch = listener(store)
        assert call(server, "POST", f"/inlet/whatsapp?key={KEY}", {"title": "Mum"},
                    token="")[0] == 202
        assert self.wait_for(store, watch.id).outcome == "fired"

    def test_a_form_and_plain_text(self, served):
        server, store, _ = served
        text_watch = watches.create(store, name="door", listen="doorbell", pick={},
                                    when={"contains": "ring"})
        assert call(server, "POST", "/inlet/doorbell", token=KEY, kind="text/plain",
                    raw=b"ring ring")[0] == 202
        assert self.wait_for(store, text_watch.id).outcome == "fired"

    def test_too_big_or_badly_named(self, served):
        server, _, _ = served
        assert call(server, "POST", "/inlet/WhatsApp", token=KEY, raw=b"x")[0] in (400, 404)
        assert call(server, "POST", "/inlet/x", token=KEY, kind="text/plain",
                    raw=b"x" * 20000)[0] == 413
        assert call(server, "GET", "/inlet/x", token=KEY)[0] == 405

    def test_nobody_listening_is_still_202(self, served):
        server, _, _ = served
        assert call(server, "POST", "/inlet/nobody", {"a": 1}, token=KEY) == (
            202, {"heard_by": 0})
