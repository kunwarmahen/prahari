"""How often a reading reads, where its values came from, and what it
decided before looks said so.

The bias these tests encode: A PACE SOMEONE ASKED FOR IS KEPT, AND ONE
NOBODY ASKS FOR ANY MORE IS GIVEN BACK. A watch that sped a reading up
leaves it at the slowest pace still wanted when it goes (removed, ended,
or back to its own call), and the owner's --every is the last word. A
site that asks for fewer calls is never called faster, by a new watch, an
old one, a speed-up or a reader in a hurry. A watch moved back off a
reading keeps what it remembered, and only the person's own reading's
call can become a watch's own. A value that says when it was measured is
aged by that time, and one measured before what is kept never fires a
watch on the past. And a reading from before looks named it still shows
what each watch decided, said as matched by time, never as recorded.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from helpers import FakeCaller, make_clock
from prahari import cli, floors, indriyas, mcp, watches
from prahari.store import iso, now_utc
from prahari.watches import WatchError

WEATHER = {"tool": "weather_now", "args": {"place": "Cary"}}
METEO = {"tool": "web_fetch",
         "args": {"url": "https://api.open-meteo.com/v1/forecast?latitude=35.8"}}
ANSWER = '{"temperature": 56, "humidity": 81}'


def outside(store, check=None, **extra):
    extra.setdefault("every", "15m")
    return indriyas.create(store, name="outside-temp", check=check or WEATHER,
                           pick={"json": "temperature"},
                           thing="the outside temperature", **extra)


def on_it(store, name="Heat the guestroom", every="5m", when=None, notes=None, **extra):
    """A watch written the old way, on the reading's call: it goes by the reading."""
    return watches.create(store, name=name, check=WEATHER, pick={"json": "temperature"},
                          when=when or {"below": 60}, every=every, notes=notes, **extra)


class TestSlowingBackDown:
    def test_a_watch_keeps_the_pace_it_asked_for(self, tmp_path):
        store, clock = make_clock(tmp_path, FakeCaller(ANSWER))
        made = outside(store)
        assert made.own_every == "15m"
        watch = on_it(store)
        assert watch.sense == made.id and watch.wants_every == "5m"
        assert store.get_indriya(made.id).every == "5m"
        clock.close()

    def test_removing_the_fastest_watch_slows_it_to_the_owners_pace(self, tmp_path):
        store, clock = make_clock(tmp_path, FakeCaller(ANSWER))
        made = outside(store)
        watch = on_it(store)
        notes: list[str] = []
        watches.remove(store, watch.id, notes=notes)
        assert store.get_indriya(made.id).every == "15m"
        assert notes == ["outside-temp now reads every 15 minutes (it read every 5 "
                         "minutes), as you set it"]
        clock.close()

    def test_it_slows_only_as_far_as_the_fastest_watch_left(self, tmp_path):
        store, clock = make_clock(tmp_path, FakeCaller(ANSWER))
        made = outside(store)
        fast = on_it(store)
        on_it(store, name="Cool the guestroom", every="10m", when={"above": 70})
        notes: list[str] = []
        watches.remove(store, fast.id, notes=notes)
        assert store.get_indriya(made.id).every == "10m"
        assert "as often as the fastest watch still on it asks" in notes[0]
        clock.close()

    def test_a_watch_that_ends_gives_its_pace_back(self, tmp_path):
        store, clock = make_clock(tmp_path, FakeCaller(ANSWER))
        made = outside(store)
        watch = on_it(store)
        clock._end(watch, "Its end came.")
        assert store.get_indriya(made.id).every == "15m"
        clock.close()

    def test_a_paused_watch_still_counts(self, tmp_path):
        store, clock = make_clock(tmp_path, FakeCaller(ANSWER))
        made = outside(store)
        watch = on_it(store)
        watches.pause(store, watch.id)
        assert indriyas.settle(store, made) == ""
        assert store.get_indriya(made.id).every == "5m"
        clock.close()

    def test_the_owners_every_is_the_last_word(self, tmp_path):
        store, clock = make_clock(tmp_path, FakeCaller(ANSWER))
        made = outside(store)
        watch = on_it(store)
        indriyas.update(store, made.id, every="30m")
        assert store.get_indriya(made.id).every == "30m"
        assert store.get(watch.id).wants_every == "30m"        # lowered to the word
        watches.remove(store, watch.id)
        assert store.get_indriya(made.id).every == "30m"
        clock.close()

    def test_a_reading_with_no_known_pace_is_not_slowed(self, tmp_path):
        store, clock = make_clock(tmp_path, FakeCaller(ANSWER))
        made = outside(store, every="5m")
        store.update_indriya(made.id, own_every="")             # made before it was kept
        assert indriyas.settle(store, made) == ""
        assert store.get_indriya(made.id).every == "5m"
        clock.close()

    def test_its_first_speed_up_remembers_the_pace_to_come_back_to(self, tmp_path):
        store, clock = make_clock(tmp_path, FakeCaller(ANSWER))
        made = outside(store)
        store.update_indriya(made.id, own_every="")
        watch = on_it(store)
        assert store.get_indriya(made.id).own_every == "15m"
        watches.remove(store, watch.id)
        assert store.get_indriya(made.id).every == "15m"
        clock.close()

    def test_the_agent_hears_it_slowed(self, tmp_path):
        store, clock = make_clock(tmp_path, FakeCaller(ANSWER))
        outside(store)
        watch = on_it(store)
        tools = mcp.Tools(store, tmp_path, FakeCaller(ANSWER), person="local")
        said = tools.call("delete_watch", {"id": watch.id})
        assert "outside-temp now reads every 15 minutes" in json.dumps(said)
        clock.close()


class TestAFloorPerSite:
    def test_a_site_is_an_address_host_or_a_tools_name(self):
        assert floors.site_of(METEO) == "api.open-meteo.com"
        assert floors.site_of(WEATHER) == "weather_now"
        assert floors.site_of({"tool": "web_fetch",
                               "args": {"url": "https://www.example.com/x"}}) \
            == "example.com"

    def test_a_floor_covers_the_sites_subdomains(self, tmp_path):
        store, clock = make_clock(tmp_path, FakeCaller(ANSWER))
        floors.put(store, "open-meteo.com", "15m", "their free tier")
        step, which = floors.floor_for(store, METEO)
        assert step == timedelta(minutes=15) and which.site == "open-meteo.com"
        assert floors.floor_for(store, WEATHER)[1] is None
        clock.close()

    def test_a_new_watch_or_reading_faster_than_the_floor_is_refused(self, tmp_path):
        store, clock = make_clock(tmp_path, FakeCaller(ANSWER))
        floors.put(store, "weather_now", "15m", "it asks for that")
        with pytest.raises(WatchError, match="weather_now is called no more than once "
                                             "every 15 minutes"):
            watches.create(store, name="Too eager", check=WEATHER,
                           pick={"json": "temperature"}, when={"below": 60}, every="5m")
        with pytest.raises(WatchError, match="every 15m or slower"):
            outside(store, every="5m")
        clock.close()

    def test_setting_a_floor_slows_what_already_calls_faster(self, tmp_path):
        store, clock = make_clock(tmp_path, FakeCaller(ANSWER))
        made = outside(store, every="5m")
        _, slowed = floors.put(store, "weather_now", "15m")
        assert store.get_indriya(made.id).every == "15m"
        assert store.get_indriya(made.id).own_every == "15m"
        assert slowed == ["indriya outside-temp now reads every 15 minutes (it read "
                          "every 5 minutes)"]
        clock.close()

    def test_a_speed_up_stops_at_the_floor_and_says_so(self, tmp_path):
        store, clock = make_clock(tmp_path, FakeCaller(ANSWER))
        floors.put(store, "weather_now", "10m")
        made = outside(store)
        notes: list[str] = []
        watch = on_it(store, notes=notes)
        assert watch.sense == made.id
        assert store.get_indriya(made.id).every == "10m"
        assert "not every 5 minutes: weather_now is called no more than once every " \
               "10 minutes" in notes[-1]
        clock.close()

    def test_a_fresh_read_waits_for_the_floor(self, tmp_path):
        store, clock = make_clock(tmp_path, FakeCaller(ANSWER))
        made = outside(store)
        clock.read_now(made.id)
        floors.put(store, "weather_now", "1h")
        with store._db() as db:                       # the reading, ten minutes old
            db.execute("UPDATE reading SET at = ?", (iso(now_utc() - timedelta(minutes=10)),))
        _, said = indriyas.fresh(store, clock.caller, store.get_indriya(made.id),
                                 timedelta(0))
        assert "not made again within an hour (weather_now is called no more" in said
        clock.close()

    def test_floors_at_the_terminal(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("PRAHARI_STATE", str(tmp_path))
        assert cli.main(["floor", "set", "https://api.open-meteo.com/v1", "15m",
                         "--why", "their free tier"]) == 0
        assert "api.open-meteo.com is called no more than once every 15 minutes " \
               "(their free tier)" in capsys.readouterr().out
        assert cli.main(["floor", "list"]) == 0
        assert "api.open-meteo.com" in capsys.readouterr().out
        assert cli.main(["floor", "rm", "api.open-meteo.com"]) == 0
        assert cli.main(["floor", "rm", "api.open-meteo.com"]) == 1


class TestBackOffTheReading:
    def test_it_takes_the_call_back_and_keeps_what_it_remembered(self, tmp_path):
        store, clock = make_clock(tmp_path, FakeCaller(ANSWER))
        made = outside(store)
        watch = on_it(store)
        store.update(watch.id, last_value="56", armed=False, looked=True)
        notes: list[str] = []
        back = watches.update(store, watch.id, look_itself=True, notes=notes)
        assert back.check == WEATHER and not back.sense and back.every == "5m"
        assert back.last_value == "56" and back.armed is False and back.looked
        assert back.next_at and back.wants_every == ""
        assert store.get_indriya(made.id).every == "15m"
        assert notes == ["outside-temp now reads every 15 minutes (it read every 5 "
                         "minutes), as you set it"]
        clock.close()

    def test_a_watch_with_no_wish_takes_the_readings_pace(self, tmp_path):
        store, clock = make_clock(tmp_path, FakeCaller(ANSWER))
        outside(store)
        watch = watches.create(store, name="Cold", sense="outside-temp",
                               when={"below": 40})
        back = watches.update(store, watch.id, look_itself=True)
        assert back.every == "15m"
        clock.close()

    def test_not_from_someone_elses_reading_or_a_pushed_one(self, tmp_path):
        store, clock = make_clock(tmp_path, FakeCaller(ANSWER))
        outside(store, share="house", owner="asha")
        mine = watches.create(store, name="Cold", sense="outside-temp",
                              when={"below": 40})
        with pytest.raises(WatchError, match="is asha's: its call is made with their "
                                             "accounts"):
            watches.update(store, mine.id, look_itself=True)
        indriyas.create(store, name="guestroom-temp", pushed=True)
        sent = watches.create(store, name="Guestroom", sense="guestroom-temp",
                              when={"below": 62})
        with pytest.raises(WatchError, match="is sent in, not read"):
            watches.update(store, sent.id, look_itself=True)
        clock.close()

    def test_it_is_a_change_of_its_own(self, tmp_path):
        store, clock = make_clock(tmp_path, FakeCaller(ANSWER))
        outside(store)
        watch = on_it(store)
        with pytest.raises(WatchError, match="a change of its own"):
            watches.update(store, watch.id, look_itself=True, when={"below": 50})
        with pytest.raises(WatchError, match="looks itself already"):
            plain = watches.create(store, name="Own", check={"tool": "other", "args": {}},
                                   pick={"number": ""}, when={"below": 1}, every="1h")
            watches.update(store, plain.id, look_itself=True)
        clock.close()

    def test_at_the_terminal(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("PRAHARI_STATE", str(tmp_path))
        store, clock = make_clock(tmp_path, FakeCaller(ANSWER))
        outside(store)
        watch = on_it(store)
        clock.close()
        assert cli.main(["edit", watch.id, "--look-itself"]) == 0
        out = capsys.readouterr().out
        assert "looks at" in out or "weather_now" in out
        assert "outside-temp now reads every 15 minutes" in out


class TestAValuesOwnTime:
    def guestroom(self, store):
        made = indriyas.create(store, name="guestroom-temp", pushed=True,
                               thing="the guestroom temperature")
        watch = watches.create(store, name="Too cold", sense="guestroom-temp",
                               when={"below": 62})
        return made, watch

    def test_its_age_is_when_it_was_measured(self, tmp_path):
        store, clock = make_clock(tmp_path, FakeCaller(ANSWER))
        made, _ = self.guestroom(store)
        then = clock.now() - timedelta(minutes=40)
        reading = clock.push(made, json.dumps({"value": 64.2, "at": then.isoformat()}))
        assert reading.outcome == "read" and reading.at == iso(clock.now())
        assert reading.measured_at == iso(then)
        assert store.get_indriya(made.id).read_at == iso(then)
        assert "measured" in reading.why
        clock.close()

    def test_seconds_since_1970_too(self, tmp_path):
        store, clock = make_clock(tmp_path, FakeCaller(ANSWER))
        made, _ = self.guestroom(store)
        then = clock.now() - timedelta(minutes=5)
        reading = clock.push(made, json.dumps({"value": 64, "at": then.timestamp()}))
        assert reading.measured_at == iso(then)
        clock.close()

    def test_measured_before_what_is_kept_is_history_not_news(self, tmp_path):
        store, clock = make_clock(tmp_path, FakeCaller(ANSWER))
        made, watch = self.guestroom(store)
        now = clock.now()
        clock.push(made, json.dumps({"value": 64.2, "at": iso(now - timedelta(minutes=5))}))
        looks = len(store.looks(watch.id))
        late = clock.push(made, json.dumps({"value": 55,
                                            "at": iso(now - timedelta(minutes=30))}))
        assert late.outcome == "late"
        assert "kept in the history only, and not handed to the watches" in late.why
        assert store.get_indriya(made.id).value == "64.2"
        assert len(store.looks(watch.id)) == looks             # nothing fired on the past
        clock.close()

    def test_a_time_it_cant_believe_counts_as_arrival(self, tmp_path):
        store, clock = make_clock(tmp_path, FakeCaller(ANSWER))
        made, _ = self.guestroom(store)
        ahead = clock.push(made, json.dumps(
            {"value": 64, "at": iso(clock.now() + timedelta(hours=2))}))
        assert ahead.measured_at is None and "ahead of this computer's clock" in ahead.why
        bare = clock.push(made, json.dumps({"value": 64, "at": "2026-11-09T08:40:00"}))
        assert bare.measured_at is None and "has no zone" in bare.why
        junk = clock.push(made, json.dumps({"value": 64, "at": "teatime"}))
        assert junk.outcome == "read" and "isn't one I can read" in junk.why
        clock.close()

    def test_at_the_terminal(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("PRAHARI_STATE", str(tmp_path))
        store, clock = make_clock(tmp_path, FakeCaller(ANSWER))
        made, _ = self.guestroom(store)
        clock.close()
        then = iso(now_utc() - timedelta(minutes=20))
        assert cli.main(["indriya", "push", "guestroom-temp", "63", "--at", then]) == 0
        assert "(measured" in capsys.readouterr().out
        assert store.get_indriya(made.id).read_at == then


class TestOlderReadingsHistory:
    def test_a_look_with_no_reading_named_is_matched_by_time(self, tmp_path):
        store, clock = make_clock(tmp_path, FakeCaller(ANSWER))
        made = indriyas.create(store, name="guestroom-temp", pushed=True)
        watch = watches.create(store, name="Too cold", sense="guestroom-temp",
                               when={"below": 62})
        clock.push(made, json.dumps({"value": 61.5}))
        with store._db() as db:                       # as a look made before it was kept
            db.execute("UPDATE look SET reading = ''")
        rows = indriyas.history(store, made)
        assert rows[0]["matched_by_time"] is True
        assert rows[0]["decided"][0]["watch"] == watch.id
        assert rows[0]["decided"][0]["matched_by_time"] is True
        lines = indriyas.history_lines(rows)
        assert any("→ Too cold:" in line and "(matched by time)" in line for line in lines)
        clock.close()

    def test_a_look_too_long_after_is_not_matched(self, tmp_path):
        store, clock = make_clock(tmp_path, FakeCaller(ANSWER))
        made = indriyas.create(store, name="guestroom-temp", pushed=True)
        watches.create(store, name="Too cold", sense="guestroom-temp", when={"below": 62})
        clock.push(made, json.dumps({"value": 61.5}))
        later = iso(now_utc() + timedelta(minutes=20))
        with store._db() as db:
            db.execute("UPDATE look SET reading = '', started_at = ?", (later,))
            db.execute("UPDATE reading SET at = ?", (iso(now_utc()),))
        rows = indriyas.history(store, made)
        assert rows[0]["decided"] == [] and rows[0]["matched_by_time"] is False
        clock.close()

    def test_recorded_looks_are_never_said_as_matched(self, tmp_path):
        store, clock = make_clock(tmp_path, FakeCaller(ANSWER))
        made = indriyas.create(store, name="guestroom-temp", pushed=True)
        watches.create(store, name="Too cold", sense="guestroom-temp", when={"below": 62})
        clock.push(made, json.dumps({"value": 61.5}))
        rows = indriyas.history(store, made)
        assert rows[0]["decided"] and rows[0]["matched_by_time"] is False
        clock.close()


class TestShowingOne:
    def test_a_pushed_one_shows_in_full_at_the_terminal(self, tmp_path, monkeypatch,
                                                        capsys):
        monkeypatch.setenv("PRAHARI_STATE", str(tmp_path))
        store, clock = make_clock(tmp_path, FakeCaller(ANSWER))
        indriyas.create(store, name="guestroom-temp", pushed=True)
        clock.close()
        assert cli.main(["indriya", "get", "guestroom-temp"]) == 0
        out = capsys.readouterr().out
        assert "check: none, its value is sent in" in out and "a value due by" in out

    def test_a_sped_up_one_says_the_pace_it_comes_back_to(self, tmp_path, monkeypatch,
                                                          capsys):
        monkeypatch.setenv("PRAHARI_STATE", str(tmp_path))
        store, clock = make_clock(tmp_path, FakeCaller(ANSWER))
        outside(store)
        on_it(store)
        clock.close()
        assert cli.main(["indriya", "get", "outside-temp"]) == 0
        assert "you set every 15m; a watch on it asked for 5m" in capsys.readouterr().out
