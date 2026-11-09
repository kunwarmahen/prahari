"""Pushed indriyas: a value sent in, instead of read.

The bias these tests encode: A SENDER IS OUTSIDE, AND IT CAN GO QUIET.
A value comes with an inlet key, so it reaches only that key's person's
indriyas -- another person's name answers like one that doesn't exist.
What it sends is picked and handed to the watches exactly as a reading
the clock took. And because a sender that broke looks, to a watch, like
a number that never crossed its line, silence is a failed reading said
on every watch, "unavailable" is not a temperature, and three of either
pause it and tell its owner -- until the sender comes back.
"""

from __future__ import annotations

import json
import time

import pytest

from helpers import FakeCaller, FakeNotifier, Hands, make_clock
from prahari import cli, indriyas, mcp, watches
from prahari.http import Api, PrahariServer
from prahari.watches import WatchError
from test_http import KEY, TOKEN, call


def guestroom(store, **extra):
    return indriyas.create(store, name="guestroom-temp", pushed=True,
                           thing="the guestroom temperature", **extra)


def too_cold(store):
    return watches.create(store, name="Guestroom too cold", sense="guestroom-temp",
                          when={"below": 62})


@pytest.fixture
def served(tmp_path):
    notifier = FakeNotifier()
    caller = FakeCaller("never called")
    store, clock = make_clock(tmp_path, caller, notifier=notifier)
    server = PrahariServer(Api(store, clock, tmp_path), TOKEN, KEY, port=0)
    server.start()
    yield server, store, notifier, caller
    server.stop()
    clock.close()


def settle(store, watch_id, count, wait=5.0):
    """The inlet answers at once and decides behind: wait for the looks."""
    until = time.monotonic() + wait
    while time.monotonic() < until:
        if len(store.looks(watch_id)) >= count:
            return store.looks(watch_id)
        time.sleep(0.05)
    return store.looks(watch_id)


class TestMakingOne:
    def test_it_has_no_call_and_says_what_it_expects(self, tmp_path):
        store, clock = make_clock(tmp_path, FakeCaller("x"))
        made = guestroom(store)
        assert made.pushed and made.check == {} and made.pick == {"json": "value"}
        assert made.every == "1h" and made.next_at       # its first deadline
        assert indriyas.sentence(made) == (
            "keeps the guestroom temperature, pushed in to the inlet as guestroom-temp "
            "(a value expected at least every hour)")
        with pytest.raises(WatchError, match="makes no call"):
            indriyas.create(store, name="x-temp", pushed=True,
                            check={"tool": "t", "args": {}})
        with pytest.raises(RuntimeError, match="pushed in: it has nothing to read"):
            clock.read_now(made.id)
        clock.close()

    def test_a_fresh_read_says_it_waits_for_its_sender(self, tmp_path):
        caller = FakeCaller("x")
        store, clock = make_clock(tmp_path, caller)
        made = guestroom(store)
        _, said = indriyas.fresh(store, caller, made, indriyas.max_age("0"))
        assert "pushed in by its sender" in said and caller.calls == []
        clock.close()


class TestThroughTheInlet:
    def test_a_value_reaches_its_watches_as_a_reading(self, served):
        server, store, notifier, caller = served
        made = guestroom(store)
        watch = too_cold(store)
        path = "/inlet/indriya/guestroom-temp"
        assert call(server, "POST", path, {"value": 64.5}, token=KEY) == (
            202, {"pushed": "guestroom-temp"})
        assert settle(store, watch.id, 1)[0].outcome == "learned"
        assert call(server, "POST", path, token=KEY, kind="text/plain",
                    raw=b"61.8")[0] == 202                      # the number alone
        assert settle(store, watch.id, 2)[0].outcome == "fired"
        assert [w for w, _ in notifier.sent] == [watch.id]
        kept = store.get_indriya(made.id)
        assert kept.value == "61.8" and caller.calls == []      # nothing was called

    def test_only_with_a_key_and_only_the_keys_people(self, served):
        server, store, _, _ = served
        indriyas.create(store, name="pool-temp", pushed=True, owner="asha")
        path = "/inlet/indriya/pool-temp"
        assert call(server, "POST", path, {"value": 80}, token="")[0] == 401
        assert call(server, "POST", path, {"value": 80}, token=TOKEN)[0] == 401
        status, said = call(server, "POST", path, {"value": 80}, token=KEY)
        assert status == 404 and "no indriya pool-temp to push to" in said["detail"]
        assert store.readings(store.indriyas()[0].id) == []

    def test_one_that_reads_takes_no_pushes(self, served):
        server, store, _, _ = served
        indriyas.create(store, name="outside-temp", check={"tool": "w", "args": {}})
        status, said = call(server, "POST", "/inlet/indriya/outside-temp", {"value": 1},
                            token=KEY)
        assert status == 409 and "reads on its own" in said["detail"]

    def test_a_listening_word_still_works_beside_it(self, served):
        server, store, _, _ = served
        watches.create(store, name="Mum", listen="whatsapp", pick={"json": "title"},
                       when={"contains": "Mum"})
        assert call(server, "POST", "/inlet/whatsapp", {"title": "Mum"},
                    token=KEY)[1] == {"heard_by": 1}


class TestTheSenderGoingQuiet:
    def test_unavailable_is_not_a_temperature(self, tmp_path):
        store, clock = make_clock(tmp_path, FakeCaller("x"))
        made = guestroom(store)
        watch = too_cold(store)
        reading = clock.push(made, json.dumps({"value": "unavailable"}))
        assert reading.outcome == "broken" and "has no value" in reading.why
        look = store.looks(watch.id)[0]
        assert look.outcome == "failed" and "got no value from its sender" in look.why
        assert store.get_indriya(made.id).trouble == 1 and not store.get_indriya(made.id).value
        clock.close()

    def test_silence_past_its_every_is_said_and_three_pause_it(self, tmp_path):
        hands, notes = Hands(), FakeNotifier()
        caller = FakeCaller("never called")
        store, clock = make_clock(tmp_path, caller, notifier=notes, now=hands)
        made = guestroom(store)
        watch = too_cold(store)
        store.update_indriya(made.id, next_at="2026-10-22T09:00:00+00:00",
                             used_at="2026-10-22T09:00:00+00:00")
        for _ in range(3):
            clock.tick()
            hands.move(hours=1)
        assert caller.calls == []
        looks = store.looks(watch.id)
        assert len(looks) == 3 and looks[0].outcome == "failed"
        assert looks[0].detail == "nothing pushed in for an hour"
        kept = store.get_indriya(made.id)
        assert kept.state == "paused" and "failed 3 times" in kept.paused_because
        assert "Paused: indriya guestroom-temp" in notes.sent[0][1]
        assert "Guestroom too cold" in notes.sent[0][1]
        clock.close()

    def test_a_value_pushes_its_deadline_on(self, tmp_path):
        hands = Hands()
        store, clock = make_clock(tmp_path, FakeCaller("x"), now=hands)
        made = guestroom(store, every="30m")
        clock.push(made, json.dumps({"value": 70}))
        assert store.get_indriya(made.id).next_at == "2026-10-22T09:30:00+00:00"
        clock.close()

    def test_the_sender_coming_back_starts_it_again(self, served):
        server, store, _, _ = served
        made = guestroom(store)
        store.update_indriya(made.id, state="paused",
                             paused_because="failed 3 times in a row; last: nothing")
        assert call(server, "POST", "/inlet/indriya/guestroom-temp", {"value": 63},
                    token=KEY)[0] == 202
        assert store.get_indriya(made.id).state == "active"
        indriyas.pause(store, store.get_indriya(made.id))         # by hand: stays
        status, said = call(server, "POST", "/inlet/indriya/guestroom-temp",
                            {"value": 63}, token=KEY)
        assert status == 409 and "paused by you" in said["detail"]


class TestOtherDoors:
    def test_by_hand_at_the_terminal(self, tmp_path, capsys):
        def run(*argv):
            rc = cli.main(["--state", str(tmp_path), *argv])
            out = capsys.readouterr()
            return rc, out.out, out.err

        rc, out, err = run("indriya", "add", "guestroom-temp", "--pushed", "--thing",
                           "the guestroom temperature")
        assert rc == 0, err
        assert "inlet/indriya/guestroom-temp" in out and "prahari indriya push" in out
        assert run("add", "Cold", "--sense", "guestroom-temp", "--when", "below 62")[0] == 0
        rc, out, err = run("indriya", "push", "guestroom-temp", "61")
        assert rc == 0, err
        assert "read       61" in out and "fired" in out
        rc, _, err = run("indriya", "look", "guestroom-temp")
        assert rc == 1 and "waits for its sender" in err

    def test_the_agent_makes_one_and_gets_the_address(self, tmp_path):
        store, clock = make_clock(tmp_path, FakeCaller("x"))
        tools = mcp.Tools(store, tmp_path, FakeCaller("x"), person="local")
        said = tools.call("create_indriya", {"name": "guestroom-temp", "pushed": True,
                                             "thing": "the guestroom temperature"})
        assert "inlet/indriya/guestroom-temp?key=" in said
        assert "rest_command" in said and "sense: \"guestroom-temp\"" in said
        clock.close()
