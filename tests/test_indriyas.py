"""Indriyas -- shared readings -- and the watches that sense them.

The bias these tests encode: ONE CALL OUT, ANY NUMBER OF WATCHES, AND A
SHARED THING MUST NOT FAIL QUIETLY. Two watches on one number make one
call per reading, not two, and each is judged by the same rules it would
be if it looked itself (edges, first-look learning, its own pick from the
whole answer). A reading that failed is said on every watch that senses
it, counted once against the indriya, and three in a row pause it and
tell its owner which watches went quiet with it. An indriya in use is not
removed out from under its watches. And sharing is the owner's choice: a
person's readings are theirs until they mark them for the house, and even
then nobody else may change them.
"""

from __future__ import annotations

import json

import pytest

from helpers import FakeCaller, FakeNotifier, Hands, make_clock
from prahari import cli, indriyas, mcp, store as store_module, watches
from prahari.http import Api
from prahari.looking import Called
from prahari.watches import WatchError

WEATHER = {"tool": "weather_now", "args": {"place": "Cary"}}
ANSWER = '{"temperature": 56, "humidity": 81}'


def outside(store, **extra):
    return indriyas.create(store, name="outside-temp", check=WEATHER,
                           pick={"json": "temperature"}, every="15m",
                           thing="the outside temperature", **extra)


def band(store):
    """The guestroom: heat below 60, cool above 70, one number."""
    heat = watches.create(store, name="Heat the guestroom", sense="outside-temp",
                          when={"below": 60})
    cool = watches.create(store, name="Cool the guestroom", sense="outside-temp",
                          when={"above": 70})
    return heat, cool


def read(clock, indriya):
    reading = clock.read_now(indriya.id)
    clock.close()
    return reading


class TestMakingOne:
    def test_a_name_is_one_short_word(self, tmp_path):
        store, clock = make_clock(tmp_path, FakeCaller(ANSWER))
        with pytest.raises(WatchError, match="one short lowercase word"):
            indriyas.create(store, name="Outside temp", check=WEATHER)
        with pytest.raises(WatchError, match="needs a check"):
            indriyas.create(store, name="outside-temp", check=None)

    def test_one_name_and_one_call_per_person(self, tmp_path):
        store, _ = make_clock(tmp_path, FakeCaller(ANSWER))
        outside(store)
        with pytest.raises(WatchError, match="already has an indriya called"):
            indriyas.create(store, name="outside-temp",
                            check={"tool": "web_fetch", "args": {"url": "https://x"}})
        with pytest.raises(WatchError, match="already reads with exactly this call"):
            indriyas.create(store, name="weather", check=WEATHER)

    def test_a_cap_per_person(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PRAHARI_MAX_INDRIYAS", "1")
        store, _ = make_clock(tmp_path, FakeCaller(ANSWER))
        outside(store)
        with pytest.raises(WatchError, match="1 indriyas already"):
            indriyas.create(store, name="btc", check={"tool": "price", "args": {}})


class TestOneCallManyWatches:
    def test_the_band_makes_one_call_per_reading_and_each_watch_decides(self, tmp_path):
        caller, notes = FakeCaller(ANSWER), FakeNotifier()
        store, clock = make_clock(tmp_path, caller, notifier=notes)
        indriya = outside(store)
        heat, cool = band(store)
        reading = read(clock, indriya)
        assert reading.outcome == "read" and reading.value == "56"
        assert len(caller.calls) == 1                         # not one per watch
        assert store.looks(heat.id)[0].outcome == "fired"     # 56 is below 60
        assert store.looks(cool.id)[0].outcome == "learned"   # 56 is not above 70
        assert [watch for watch, _ in notes.sent] == [heat.id]
        kept = store.get_indriya(indriya.id)
        assert kept.value == "56" and kept.read_at

    def test_a_sensing_watch_looks_at_nothing_itself(self, tmp_path):
        hands = Hands()
        caller = FakeCaller(ANSWER)
        store, clock = make_clock(tmp_path, caller, now=hands)
        indriya = outside(store)
        heat, _ = band(store)
        assert store.get(heat.id).next_at is None and not store.get(heat.id).check
        store.update_indriya(indriya.id, next_at="2026-10-22T09:00:00+00:00")
        started = clock.tick()                    # only the indriya is due
        assert len(started) == 1
        [f.result() for f in started]
        assert len(caller.calls) == 1
        with pytest.raises(RuntimeError, match="prahari indriya look outside-temp"):
            clock.look_now(heat.id)
        clock.close()

    def test_it_reads_on_its_own_every(self, tmp_path):
        hands = Hands()
        store, clock = make_clock(tmp_path, FakeCaller(ANSWER), now=hands)
        indriya = outside(store)
        store.update_indriya(indriya.id, next_at="2026-10-22T09:00:00+00:00")
        [f.result() for f in clock.tick()]
        assert store.get_indriya(indriya.id).next_at == "2026-10-22T09:15:00+00:00"
        assert clock.tick() == []
        hands.move(minutes=15)
        assert len(clock.tick()) == 1
        clock.close()

    def test_a_watch_may_pick_something_else_from_the_whole_answer(self, tmp_path):
        store, clock = make_clock(tmp_path, FakeCaller(ANSWER))
        indriya = outside(store)
        damp = watches.create(store, name="Damp outside", sense="outside-temp",
                              pick={"json": "humidity"}, thing="the humidity",
                              when={"above": 80})
        read(clock, indriya)
        look = store.looks(damp.id)[0]
        assert look.outcome == "fired" and look.value == "81"

    def test_the_edge_holds_across_readings(self, tmp_path):
        caller = FakeCaller(ANSWER)
        store, clock = make_clock(tmp_path, caller)
        indriya = outside(store)
        heat, _ = band(store)
        clock.read_now(indriya.id)
        clock.read_now(indriya.id)                # still 56: no second fire
        caller.say('{"temperature": 64}')
        clock.read_now(indriya.id)                # back above the line: re-armed
        caller.say('{"temperature": 58}')
        read(clock, indriya)
        assert [lk.outcome for lk in reversed(store.looks(heat.id))] == [
            "fired", "quiet", "quiet", "fired"]

    def test_a_sensing_watch_has_no_every_or_check_of_its_own(self, tmp_path):
        store, _ = make_clock(tmp_path, FakeCaller(ANSWER))
        outside(store)
        with pytest.raises(WatchError, match="has no every"):
            watches.create(store, name="w", sense="outside-temp", when={"below": 60},
                           every="1h")
        with pytest.raises(WatchError, match="one of them"):
            watches.create(store, name="w", sense="outside-temp", check=WEATHER,
                           when={"below": 60})
        heat, _ = band(store)
        with pytest.raises(WatchError, match="mend the indriya"):
            watches.update(store, heat.id, every="5m")
        mended = watches.update(store, heat.id, when={"below": 55})
        assert mended.when == {"below": 55} and mended.next_at is None

    def test_a_twin_on_the_same_reading_is_refused_but_a_band_is_not(self, tmp_path):
        store, _ = make_clock(tmp_path, FakeCaller(ANSWER))
        outside(store)
        band(store)
        with pytest.raises(WatchError, match="already has a watch on exactly this"):
            watches.create(store, name="again", sense="outside-temp", when={"below": 50})

    def test_its_words_name_the_reading(self, tmp_path):
        store, _ = make_clock(tmp_path, FakeCaller(ANSWER))
        outside(store)
        heat, _ = band(store)
        said = watches.sentence(heat, store)
        assert said.startswith("senses outside-temp (every 15 minutes)")
        assert "the outside temperature is below 60" in said


class TestAFailureIsSaidNotSwallowed:
    def test_a_failed_reading_shows_on_each_watch_but_counts_once(self, tmp_path):
        caller = FakeCaller(Called(ok=False, detail="weather service down"))
        notes = FakeNotifier()
        store, clock = make_clock(tmp_path, caller, notifier=notes)
        indriya = outside(store)
        heat, cool = band(store)
        clock.read_now(indriya.id)
        look = store.looks(heat.id)[0]
        assert look.outcome == "failed" and "outside-temp could not read" in look.why
        assert store.get(heat.id).trouble == 0 and store.get(cool.id).trouble == 0
        clock.read_now(indriya.id)
        read(clock, indriya)
        kept = store.get_indriya(indriya.id)
        assert kept.state == "paused" and "failed 3 times" in kept.paused_because
        [(whom, text)] = notes.sent
        assert whom == indriya.id and "Paused: indriya outside-temp" in text
        assert "Heat the guestroom" in text and "Cool the guestroom" in text
        assert store.get(heat.id).state == "active"     # the watch itself is fine

    def test_a_pick_that_finds_nothing_is_broken(self, tmp_path):
        store, clock = make_clock(tmp_path, FakeCaller("<html>moved</html>"))
        indriya = outside(store)
        reading = read(clock, indriya)
        assert reading.outcome == "broken" and "moved" in reading.detail
        assert store.get_indriya(indriya.id).trouble == 1

    def test_a_good_reading_resets_the_count(self, tmp_path):
        caller = FakeCaller(Called(ok=False, detail="down"), ANSWER)
        store, clock = make_clock(tmp_path, caller)
        indriya = outside(store)
        clock.read_now(indriya.id)
        read(clock, indriya)
        assert store.get_indriya(indriya.id).trouble == 0


class TestItsHistory:
    def test_readings_are_kept_newest_first_and_only_so_many(self, tmp_path, monkeypatch):
        monkeypatch.setattr(store_module, "READINGS_KEPT", 3)
        hands = Hands()
        caller = FakeCaller(ANSWER)
        store, clock = make_clock(tmp_path, caller, now=hands)
        indriya = outside(store)
        for degrees in (50, 51, 52, 53, 54):
            caller.say(json.dumps({"temperature": degrees}))
            clock.read_now(indriya.id)
            hands.move(minutes=15)
        clock.close()
        assert [r.value for r in store.readings(indriya.id)] == ["54", "53", "52"]


class TestRemovingAndMending:
    def test_one_in_use_is_not_removed(self, tmp_path):
        store, _ = make_clock(tmp_path, FakeCaller(ANSWER))
        indriya = outside(store)
        heat, cool = band(store)
        with pytest.raises(WatchError, match="remove those watches first"):
            indriyas.remove(store, indriya)
        watches.remove(store, heat.id)
        watches.remove(store, cool.id)
        indriyas.remove(store, indriya)
        assert store.indriyas() == []

    def test_a_new_pick_starts_its_watches_over(self, tmp_path):
        store, clock = make_clock(tmp_path, FakeCaller(ANSWER))
        indriya = outside(store)
        heat, _ = band(store)
        read(clock, indriya)
        assert store.get(heat.id).looked
        indriyas.update(store, indriya.id, pick={"json": "temp_f"})
        assert not store.get(heat.id).looked
        assert store.get_indriya(indriya.id).value == ""

    def test_how_often_is_changed_without_forgetting(self, tmp_path):
        store, clock = make_clock(tmp_path, FakeCaller(ANSWER))
        indriya = outside(store)
        read(clock, indriya)
        mended = indriyas.update(store, indriya.id, every="1h")
        assert mended.every == "1h" and mended.value == "56"


class TestSharing:
    def test_mine_is_mine_and_house_is_everyones_to_read(self, tmp_path):
        store, _ = make_clock(tmp_path, FakeCaller(ANSWER))
        indriya = outside(store)
        with pytest.raises(WatchError, match="no indriya outside-temp"):
            indriyas.find(store, "outside-temp", "asha")
        indriyas.update(store, indriya.id, share="house")
        assert indriyas.find(store, "outside-temp", "asha").id == indriya.id
        with pytest.raises(WatchError, match="no indriya"):
            indriyas.find(store, "outside-temp", "asha", own_only=True)

    def test_someone_elses_watch_may_sense_a_house_reading(self, tmp_path):
        store, clock = make_clock(tmp_path, FakeCaller(ANSWER))
        indriya = outside(store, share="house")
        theirs = watches.create(store, name="Cold out", sense="outside-temp",
                                when={"below": 60}, owner="asha")
        read(clock, indriya)
        assert store.looks(theirs.id)[0].outcome == "fired"
        with pytest.raises(WatchError, match="other people's watches"):
            indriyas.update(store, indriya.id, share="mine")

    def test_ones_own_wins_over_a_house_one_of_the_same_name(self, tmp_path):
        store, _ = make_clock(tmp_path, FakeCaller(ANSWER))
        outside(store, share="house")
        own = indriyas.create(store, name="outside-temp", owner="asha",
                              check={"tool": "weather_now", "args": {"place": "Pune"}})
        assert indriyas.find(store, "outside-temp", "asha").id == own.id


class TestTheAgentsTools:
    def tools(self, store, tmp_path, person="local"):
        return mcp.Tools(store, tmp_path, FakeCaller(ANSWER), person=person,
                         agent="/agents/a")

    def test_create_then_sense_then_read(self, tmp_path):
        store, clock = make_clock(tmp_path, FakeCaller(ANSWER))
        t = self.tools(store, tmp_path)
        said = t.call("create_indriya", {"name": "outside-temp", "check": WEATHER,
                                         "pick": {"json": "temperature"},
                                         "thing": "the outside temperature"})
        assert "Saved indriya outside-temp" in said and 'sense: "outside-temp"' in said
        said = t.call("preview_watch", {"sense": "outside-temp", "when": {"below": 60}})
        assert "senses outside-temp" in said and "already matches" in said
        said = t.call("create_watch", {"name": "Heat the guestroom", "asked": "heat it "
                                       "when it's cold out", "sense": "outside-temp",
                                       "when": {"below": 60}})
        assert "senses outside-temp" in said
        read(clock, store.indriyas()[0])
        listed = t.call("list_indriyas", {})
        assert listed.startswith("outside-temp: 56 (") and "ago" in listed
        assert "read" in t.call("read_indriya", {"name": "outside-temp"})

    def test_another_person_sees_only_house_readings_and_changes_none(self, tmp_path):
        store, _ = make_clock(tmp_path, FakeCaller(ANSWER))
        outside(store)
        t = self.tools(store, tmp_path, person="asha")
        assert t.call("list_indriyas", {}).startswith("No indriyas yet")
        indriyas.update(store, store.indriyas()[0].id, share="house")
        assert "(local's)" in t.call("list_indriyas", {})
        with pytest.raises(mcp.ToolFailed, match="no indriya"):
            t.call("update_indriya", {"name": "outside-temp", "every": "5m"})
        with pytest.raises(mcp.ToolFailed, match="no indriya"):
            t.call("delete_indriya", {"name": "outside-temp"})


class TestTheOtherDoors:
    def test_the_api_reads_one_by_name_with_its_history(self, tmp_path):
        store, clock = make_clock(tmp_path, FakeCaller(ANSWER))
        indriya = outside(store)
        band(store)
        clock.read_now(indriya.id)
        api = Api(store, clock, tmp_path)
        status, card = api.handle("GET", "/api/indriyas/outside-temp", {}, {})
        assert status == 200 and card["value"] == "56" and len(card["sensed_by"]) == 2
        status, body = api.handle("GET", "/api/indriyas/outside-temp/readings", {}, {})
        assert [r["value"] for r in body["readings"]] == ["56"]
        status, body = api.handle("GET", "/api/indriyas", {}, {})
        assert [i["name"] for i in body["indriyas"]] == ["outside-temp"]
        clock.close()

    def test_by_hand_at_the_terminal(self, tmp_path, capsys):
        def run(*argv):
            rc = cli.main(["--state", str(tmp_path), *argv])
            out = capsys.readouterr()
            return rc, out.out, out.err

        rc, out, err = run("indriya", "add", "outside-temp", "--check", "weather_now",
                           "--args", '{"place": "Cary"}', "--pick", "json:temperature",
                           "--thing", "the outside temperature")
        assert rc == 0, err
        assert "reads the outside temperature every 15 minutes" in out
        rc, out, err = run("add", "Heat the guestroom", "--sense", "outside-temp",
                           "--when", "below 60")
        assert rc == 0, err
        assert "senses outside-temp" in out and "is below 60" in out
        rc, out, _ = run("indriya", "get", "outside-temp", "--json")
        card = json.loads(out)
        assert card["sensed_by"][0]["name"] == "Heat the guestroom"
        rc, out, err = run("indriya", "rm", "outside-temp")
        assert rc == 2 and "remove those watches first" in err
        rc, out, _ = run("indriya", "list")
        assert "outside-temp: not read yet" in out and "sensed by:" in out
