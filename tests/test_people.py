"""Watches for everyone in the house: each one looks as its person.

The bias these tests encode: A WATCH IS ITS PERSON'S, ALL THE WAY DOWN. A
watch on the Dvara road looks through Dvara as its person (``POST
/call``), so a guest's watch reads the guest's accounts and never this
computer's; and a knock is heard only by the watches of the person whose
key it came with, so one person's phone can't fire another's watch. The
computer's own person goes by two names ("local", and Dvara's name for
them), and a knock for one is a knock for both.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from helpers import FakeCaller, make_clock
from prahari import watches
from prahari.dvara import Dvara, DvaraCaller
from prahari.http import Api
from prahari.looking import Roads
from prahari.store import Store


class FakeDvara:
    """Dvara's ``/call`` and ``/agents``, answering what it is told to."""

    def __init__(self, answer: dict | None = None, status: int = 200) -> None:
        self.answer = answer or {"format": "yantra.call.v1", "ok": True, "tool": "t",
                                 "text": "thread aa11 · from Bank", "detail": "",
                                 "images": 0, "needs_person": [], "busy": []}
        self.status = status
        self.bodies: list[dict] = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _reply(self, status, data):
                raw = json.dumps(data).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                self._reply(200, {"agents": ["minder"]})

            def do_POST(self):
                size = int(self.headers.get("Content-Length") or 0)
                fake.bodies.append({"path": self.path,
                                    **json.loads(self.rfile.read(size) or b"{}")})
                self._reply(fake.status, fake.answer)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.dvara = Dvara(url=f"http://127.0.0.1:{self.httpd.server_address[1]}",
                           token="t" * 20, actor="mahen")

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def dvara():
    fake = FakeDvara()
    yield fake
    fake.close()


def guests_watch(store, dvara, **kw):
    return watches.create(store, name="Bank mail", check={
        "tool": "mcp__gmail__search_threads", "args": {"account": "asha",
                                                       "query": "from:bank"}},
        pick={"items": r"thread (\w+)"}, when={"new": True}, every="30m",
        owner="asha", runner="dvara", agent="minder", dvara=dvara.dvara, **kw)


class TestALookAsThePerson:
    def test_a_dvara_road_look_goes_to_dvara_as_its_person_granted_word_for_word(
            self, tmp_path, dvara):
        store = Store(tmp_path / "p.sqlite3")
        watch = guests_watch(store, dvara)
        here = FakeCaller("the owner's inbox")
        said = Roads(here, DvaraCaller(dvara.dvara)).call(watch)
        assert said.ok and "from Bank" in said.text
        assert here.calls == []                       # never this computer's accounts
        body = dvara.bodies[-1]
        assert body["path"] == "/call" and body["actor"] == "asha"
        assert body["agent"] == "minder" and body["tool"] == "mcp__gmail__search_threads"
        assert body["allow_tools"] == [
            "mcp__gmail__search_threads(account=asha, query=from:bank)"]

    def test_a_preview_through_dvara_is_granted_nothing(self, tmp_path, dvara):
        store = Store(tmp_path / "p.sqlite3")
        roads = Roads(FakeCaller("x"), DvaraCaller(dvara.dvara))
        watches.preview(roads, check={"tool": "web_fetch", "args": {"url": "https://a.b"}},
                        when={"changed": True}, every="1h", agent="minder",
                        runner="dvara", owner="asha")
        assert dvara.bodies[-1]["allow_tools"] == [] and dvara.bodies[-1]["actor"] == "asha"
        assert store.watches() == []

    def test_a_dvara_road_look_with_no_dvara_says_so(self, tmp_path, dvara):
        watch = guests_watch(Store(tmp_path / "p.sqlite3"), dvara)
        said = Roads(FakeCaller("x"), None).call(watch)
        assert not said.ok and "PRAHARI_DVARA_URL" in said.detail

    def test_dvaras_refusal_is_the_looks_answer(self, tmp_path):
        fake = FakeDvara({"detail": "watches are off for asha on this service"}, 404)
        try:
            watch = guests_watch(Store(tmp_path / "p.sqlite3"), fake)
            said = DvaraCaller(fake.dvara).call(watch)
        finally:
            fake.close()
        assert not said.ok and "watches are off for asha" in said.detail

    def test_an_older_dvara_without_call_is_named(self, tmp_path):
        fake = FakeDvara({"ok": True})
        try:
            said = DvaraCaller(fake.dvara).call(guests_watch(Store(tmp_path / "p.sqlite3"),
                                                              fake))
        finally:
            fake.close()
        assert not said.ok and "older than POST /call" in said.detail

    def test_the_dvara_road_names_its_agent(self, tmp_path, dvara):
        with pytest.raises(watches.WatchError, match="--agent NAME"):
            watches.create(Store(tmp_path / "p.sqlite3"), name="x",
                           check={"tool": "t", "args": {}}, when={"changed": True},
                           every="1h", owner="asha", runner="dvara", dvara=dvara.dvara)


def listening(store, owner, word="whatsapp"):
    return watches.create(store, name=f"Mum for {owner}", listen=word,
                          pick={"json": "title"}, when={"contains": "Mum"}, owner=owner)


class TestAKnockIsItsPersons:
    def test_a_knock_reaches_only_the_watches_of_the_person_it_is_for(self, tmp_path):
        store, clock = make_clock(tmp_path, FakeCaller("x"))
        clock.home = {"local", "mahen"}
        mine, theirs = listening(store, "local"), listening(store, "asha")
        try:
            assert clock.event("whatsapp", {"title": "Mum"}, {"asha"}) == [theirs.id]
            assert clock.event("whatsapp", {"title": "Mum", "id": "2"},
                               {"mahen"}) == [mine.id]       # Dvara's name for local
        finally:
            clock.close()

    def test_each_persons_key_opens_the_inlet_for_them_alone(self, tmp_path):
        store, clock = make_clock(tmp_path, FakeCaller("x"))
        clock.home = {"local", "mahen"}
        api = Api(store, clock, tmp_path, inlet_key="the-computers-key-0123")
        theirs = store.inlet_key("asha")
        try:
            assert api.owners_of("the-computers-key-0123") == {"local", "mahen"}
            assert api.owners_of(theirs) == {"asha"}
            assert api.owners_of("a-key-nobody-has-012345") is None
            assert api.owners_of("") is None
            fresh = store.new_inlet_key("asha")
            assert fresh != theirs and api.owners_of(theirs) is None
        finally:
            clock.close()

    def test_a_person_keeps_their_key(self, tmp_path):
        store = Store(tmp_path / "p.sqlite3")
        assert store.inlet_key("asha") == store.inlet_key("asha")
        assert store.inlet_key("asha") != store.inlet_key("ravi")


class TestWatchesNamedForTheirPerson:
    def test_inlet_address_gives_a_person_their_own_key(self, tmp_path):
        from prahari import mcp

        store = Store(tmp_path / "p.sqlite3")
        tools = mcp.Tools(store, tmp_path, FakeCaller("x"), person="asha",
                          home={"local", "mahen"})
        said = tools.call("inlet_address", {})
        assert f"key={store.inlet_key('asha')}" in said and "reaches only their" in said

    def test_the_computers_person_gets_the_kept_key(self, tmp_path):
        from prahari import mcp
        from prahari.http import inlet_token

        tools = mcp.Tools(Store(tmp_path / "p.sqlite3"), tmp_path, FakeCaller("x"),
                          person="mahen", home={"local", "mahen"})
        assert f"key={inlet_token(tmp_path)}" in tools.call("inlet_address", {})

