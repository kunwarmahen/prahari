"""A watch that starts a routine (Vidhi) when it fires.

BIAS: against a fire that does two things or none -- a watch that asks
the agent AND starts a routine, a routine started as someone other than
the watch's person, a routine that didn't start and nobody heard.
"""

from __future__ import annotations

import json
import sys

import pytest

from helpers import FakeCaller, make_clock
from prahari import looking, watches
from prahari.watches import WatchError

CHECK = {"tool": "web_fetch", "args": {"url": "https://p.example"}}


def _watch(store, **extra):
    return watches.create(store, name="Cheap", check=CHECK, pick={"number": ""},
                          when={"below": 10}, every="1h", **extra)


def test_it_starts_the_routine_as_its_person_with_what_it_saw(tmp_path):
    store, clock = make_clock(tmp_path, FakeCaller("price 12", "price 8"))
    started = []
    clock.start_routine = lambda watch, found: (started.append((watch.owner, found))
                                                or (True, "ab12cd34"))
    watch = _watch(store, routine="price-then-plan")
    clock.look_now(watch.id)
    look = clock.look_now(watch.id)
    assert look.outcome == "fired" and look.turn == "routine"
    assert look.reply == "started the routine price-then-plan (run ab12cd34)"
    assert started == [("local", "8")]
    assert clock.notifier.sent == [], "Vidhi tells the person, not Prahari"


def test_a_routine_that_did_not_start_is_said(tmp_path):
    store, clock = make_clock(tmp_path, FakeCaller("price 12", "price 8"))
    clock.start_routine = lambda watch, found: (False, "price-then-plan is paused")
    watch = _watch(store, routine="price-then-plan")
    clock.look_now(watch.id)
    look = clock.look_now(watch.id)
    assert look.turn == "failed" and "is paused" in look.detail
    assert "didn't start: price-then-plan is paused" in clock.notifier.sent[-1][1]


def test_then_and_routine_are_never_both(tmp_path):
    store, _ = make_clock(tmp_path, FakeCaller("1"))
    with pytest.raises(WatchError, match="not both"):
        _watch(store, then="plan it", routine="price-then-plan")
    with pytest.raises(WatchError, match="not a routine's name"):
        _watch(store, routine="Price Then Plan")


def test_giving_a_then_later_takes_the_routine_away(tmp_path):
    store, _ = make_clock(tmp_path, FakeCaller("1"))
    watch = _watch(store, routine="price-then-plan")
    assert watches.card(watch)["does"].startswith("Then it starts the routine")
    watch = watches.update(store, watch.id, then="Plan it")
    assert watch.routine == "" and watch.then == "Plan it"


def test_vidhi_start_is_asked_as_the_watchs_person(tmp_path):
    script = tmp_path / "vidhi.py"
    script.write_text("import json, sys\nopen(sys.argv[0] + '.log', 'w').write("
                      "json.dumps(sys.argv[1:]))\nprint(json.dumps({'id': 'ab12cd34'}))\n")
    watch = watches.Watch(id="w1", owner="asha", name="x", routine="cold-night")
    ok, said = looking.start_routine(watch, "38.5", command=[sys.executable, str(script)])
    assert ok and said == "ab12cd34"
    assert json.loads((tmp_path / "vidhi.py.log").read_text()) == [
        "start", "cold-night", "--as=asha", "--by=prahari:w1", "--found=38.5", "--json"]


# A watch's own inputs. BIAS: one routine for two places meant two installs,
# or a watch that quietly ran with the installed place.


def test_a_watchs_own_inputs_go_with_the_start(tmp_path):
    script = tmp_path / "vidhi.py"
    script.write_text("import json, sys\nopen(sys.argv[0] + '.log', 'w').write("
                      "json.dumps(sys.argv[1:]))\nprint(json.dumps({'id': 'ab12cd34'}))\n")
    watch = watches.Watch(id="w1", owner="asha", name="x", routine="cold-night",
                          routine_inputs={"room": "guestroom"})
    looking.start_routine(watch, "38.5", command=[sys.executable, str(script)])
    argv = json.loads((tmp_path / "vidhi.py.log").read_text())
    assert argv[-1] == "--input=room=guestroom" and "--found=38.5" in argv


def test_inputs_are_kept_mended_and_dropped_with_the_routine(tmp_path):
    store, _ = make_clock(tmp_path, FakeCaller("1"))
    watch = _watch(store, routine="cold-night", routine_inputs={"room": "guestroom"})
    assert store.get(watch.id).routine_inputs == {"room": "guestroom"}
    assert "cold-night (room = guestroom)" in watches.card(watch)["does"]
    watch = watches.update(store, watch.id, routine_inputs={"room": "porch"})
    assert watch.routine_inputs == {"room": "porch"}
    watch = watches.update(store, watch.id, then="Tell me")
    assert watch.routine == "" and watch.routine_inputs == {}


def test_inputs_need_a_routine_and_found_is_the_watchs_own(tmp_path):
    store, _ = make_clock(tmp_path, FakeCaller("1"))
    with pytest.raises(WatchError, match="give the watch a routine too"):
        _watch(store, routine_inputs={"room": "porch"})
    with pytest.raises(WatchError, match="fills that one itself"):
        _watch(store, routine="cold-night", routine_inputs={"found": "x"})
    with pytest.raises(WatchError, match="one lowercase word"):
        _watch(store, routine="cold-night", routine_inputs={"The Room": "x"})
