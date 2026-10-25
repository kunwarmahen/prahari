"""Mail pushed, not polled: a knock that wakes a watch, the call that keeps
the knocking going, and the inlet on the public road.

The bias these tests encode: A KNOCK ONLY SAYS "LOOK NOW". A watch woken
by its word looks with its own check, the knock's body unread, so a
sender that can say "something came" cannot say what; a knock while it
looks makes one more look, not a pile. The push is kept alive by its own
call, granted word for word, and a renewal that fails is trouble, never
quiet. And the address put on the internet is the inlet ALONE: no page,
no API, a limit on knocks, and a Pub/Sub push read through its envelope.
"""

from __future__ import annotations

import base64
import json
import threading
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta

import pytest

from helpers import FakeCaller, make_clock
from prahari import watches
from prahari.clock import RENEW_RETRY
from prahari.http import KNOCKS_PER_MINUTE, Api, PrahariServer, _event_body
from prahari.looking import Called

KEY = "inlet-key-0123456789ab"
TOKEN = "page-token-0123456789"
TOPIC = "projects/my-house/topics/gmail-push"


def mail_watch(store, **kw):
    return watches.create(store, name="Bank mail", check={
        "tool": "mcp__gmail__search_threads", "args": {"account": "personal",
                                                       "query": "from:bank"}},
        pick={"items": r"thread (\w+)"}, when={"new": True}, every="6h",
        wake="gmail", **kw)


def settle(clock, futures=()):
    for future in futures:
        future.result(10)
    for _ in range(100):
        with clock._lock:
            if not clock._looking:
                return
        time.sleep(0.02)


class TestAKnockWakesALook:
    def test_its_word_makes_it_look_now_with_its_own_check(self, tmp_path):
        caller = FakeCaller("thread aa11 · from bank")
        store, clock = make_clock(tmp_path, caller)
        watch = mail_watch(store)
        try:
            assert clock.hear("gmail", {"emailAddress": "me@example.com"}) == 1
            settle(clock)
        finally:
            clock.close()
        assert caller.calls[0][0]["tool"] == "mcp__gmail__search_threads"
        assert store.looks(watch.id)[0].came_by == "wake"

    def test_a_knock_while_it_looks_makes_one_more_look_not_a_pile(self, tmp_path):
        gate = threading.Event()

        class Slow(FakeCaller):
            def call(self, watch, *, granted=True):
                gate.wait(5)
                return super().call(watch, granted=granted)

        caller = Slow("thread aa11")
        store, clock = make_clock(tmp_path, caller)
        watch = mail_watch(store)
        try:
            for _ in range(5):
                clock.hear("gmail", {})
            gate.set()
            settle(clock)
            time.sleep(0.2)
            settle(clock)
        finally:
            clock.close()
        assert len(caller.calls) == 2
        assert [look.came_by for look in store.looks(watch.id)] == ["wake", "wake"]

    def test_the_knock_is_not_read_so_it_cannot_fire_anything(self, tmp_path):
        caller = FakeCaller("thread aa11")
        store, clock = make_clock(tmp_path, caller)
        mail_watch(store)
        try:
            clock.hear("gmail", {"text": "thread zz99 · new!"})
            settle(clock)
        finally:
            clock.close()
        assert all(look.outcome == "learned" for look in store.looks())

    def test_another_persons_knock_does_not_wake_it(self, tmp_path):
        caller = FakeCaller("thread aa11")
        store, clock = make_clock(tmp_path, caller)
        mail_watch(store)
        try:
            assert clock.hear("gmail", {}, {"asha"}) == 0
        finally:
            clock.close()
        assert caller.calls == []

    def test_a_paused_watch_sleeps_through_its_knock(self, tmp_path):
        caller = FakeCaller("x")
        store, clock = make_clock(tmp_path, caller)
        watches.pause(store, mail_watch(store).id)
        try:
            clock.hear("gmail", {})
        finally:
            clock.close()
        assert caller.calls == []


class TestTheFormOfAWake:
    def test_renew_goes_with_wake(self, tmp_path):
        store, clock = make_clock(tmp_path, FakeCaller("x"))
        clock.close()
        with pytest.raises(watches.WatchError, match="goes with wake"):
            watches.create(store, name="x", check={"tool": "t", "args": {}},
                           when={"changed": True}, every="1h",
                           renew={"tool": "mcp__gmail__watch_mailbox", "args": {}})

    def test_a_watch_that_listens_has_no_wake(self, tmp_path):
        store, clock = make_clock(tmp_path, FakeCaller("x"))
        clock.close()
        with pytest.raises(watches.WatchError, match="for a watch that looks"):
            watches.create(store, name="x", listen="whatsapp", when={"any": True},
                           wake="gmail")

    def test_the_sentence_says_what_a_knock_does(self, tmp_path):
        store, clock = make_clock(tmp_path, FakeCaller("x"))
        clock.close()
        watch = mail_watch(store, renew={"tool": "mcp__gmail__watch_mailbox",
                                         "args": {"topic": TOPIC}})
        said = watches.sentence(watch)
        assert "at once whenever gmail knocks" in said
        assert "kept knocking by mcp__gmail__watch_mailbox, once a day" in said


class TestRenewing:
    def renewing(self, tmp_path, *answers):
        caller = FakeCaller(*answers)
        store, clock = make_clock(tmp_path, caller)
        watch = mail_watch(store, renew={"tool": "mcp__gmail__watch_mailbox",
                                         "args": {"account": "personal", "topic": TOPIC}})
        # past the moment it was made: renew_at is the real clock's, so the
        # test's clock starts from whichever is later, its START or today
        clock.now.at = max(clock.now.at, datetime.now(UTC))
        clock.now.move(days=2)
        return caller, store, clock, watch

    def test_it_renews_at_the_start_and_then_a_day_later(self, tmp_path):
        caller, store, clock, watch = self.renewing(
            tmp_path, Called(ok=True, text="Gmail now tells it until Thu"))
        try:
            settle(clock, clock.tick())
            renewals = [c for c in caller.calls if c[0]["tool"].endswith("watch_mailbox")]
            assert renewals == [({"tool": "mcp__gmail__watch_mailbox",
                                  "args": {"account": "personal", "topic": TOPIC}}, True)]
            assert store.get(watch.id).renew_at == (
                clock.now() + timedelta(days=1)).isoformat(timespec="seconds")
            look = [x for x in store.looks(watch.id) if x.came_by == "renew"][0]
            assert look.outcome == "quiet" and look.detail.startswith("renewed:")
        finally:
            clock.close()

    def test_a_renewal_that_fails_is_trouble_and_is_tried_again_in_an_hour(self,
                                                                           tmp_path):
        caller, store, clock, watch = self.renewing(
            tmp_path, Called(ok=False, detail="no tool 'mcp__gmail__watch_mailbox'"))
        try:
            settle(clock, clock.tick())
        finally:
            clock.close()
        look = [x for x in store.looks(watch.id) if x.came_by == "renew"][0]
        assert look.outcome == "failed" and "renewing its push" in look.detail
        kept = store.get(watch.id)
        assert kept.trouble >= 1
        assert kept.renew_at == (clock.now() + RENEW_RETRY).isoformat(timespec="seconds")


class TestThePublicRoad:
    @pytest.fixture
    def alone(self, tmp_path):
        store, clock = make_clock(tmp_path, FakeCaller("x"))
        api = Api(store, clock, tmp_path, inlet_key=KEY)
        server = PrahariServer(api, TOKEN, KEY, port=0, inlet_only=True,
                               public_url="https://house.example.ts.net/")
        server.start()
        yield server, store, api
        server.stop()
        clock.close()

    def send(self, server, path, body=None, token=None, method="POST"):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        host, port = server.httpd.server_address[:2]
        request = urllib.request.Request(f"http://{host}:{port}{path}", method=method,
                                         data=json.dumps(body or {}).encode()
                                         if method == "POST" else None, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read() or b"{}")

    def test_the_inlet_alone_has_no_page_and_no_api(self, alone):
        server, _, _ = alone
        assert self.send(server, "/", method="GET")[0] == 404
        assert self.send(server, "/api/watches", token=TOKEN, method="GET")[0] == 404
        assert self.send(server, f"/inlet/whatsapp?key={KEY}", {"title": "Mum"})[0] == 202

    def test_its_public_address_is_what_the_page_shows(self, alone):
        _, _, api = alone
        assert api.inlet_public == "https://house.example.ts.net/inlet/"

    def test_too_many_knocks_hear_429(self, alone):
        server, _, api = alone
        start = time.monotonic()
        for n in range(KNOCKS_PER_MINUTE):
            assert api.may_knock(KEY, start + n * 0.01)
        assert not api.may_knock(KEY, start + 1)
        assert api.may_knock(KEY, start + 61)          # a minute on, the door opens
        assert api.may_knock("another-key-0123456789", start + 1)

    def test_a_person_key_on_the_public_road_is_heard_as_them(self, alone):
        server, store, _ = alone
        watches.create(store, name="Mum", listen="whatsapp", pick={"json": "title"},
                       when={"contains": "Mum"}, owner="asha")
        theirs = store.inlet_key("asha")
        assert self.send(server, f"/inlet/whatsapp?key={theirs}",
                         {"title": "Mum"})[1] == {"heard_by": 1}
        assert self.send(server, f"/inlet/whatsapp?key={KEY}",
                         {"title": "Mum"})[1] == {"heard_by": 0}


class TestPubSub:
    def test_a_push_is_read_through_its_envelope(self):
        inner = {"emailAddress": "me@example.com", "historyId": "4242"}
        raw = json.dumps({"message": {"data": base64.b64encode(json.dumps(inner).encode())
                                      .decode(), "messageId": "m-77"},
                          "subscription": "projects/my-house/subscriptions/prahari"})
        assert _event_body(raw.encode(), "application/json") == {**inner, "id": "m-77"}

    def test_anything_else_is_read_as_it_came(self):
        raw = json.dumps({"message": "hello", "title": "Mum"}).encode()
        assert _event_body(raw, "application/json") == {"message": "hello",
                                                        "title": "Mum"}
