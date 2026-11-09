"""An indriya's history: each reading with what every watch decided on it.

The bias these tests encode: "WHAT HAPPENED?" HAS ONE ANSWER, IN ONE
PLACE. A watch has its looks; an indriya had only a list of values, and
why a watch on it stayed quiet meant reading two histories side by side.
So each reading carries how it came (its clock, by hand, asked for fresh,
sent in, a sender gone quiet) and the looks it was handed to -- and
another person's watches on a shared reading are counted, never named.
"""

from __future__ import annotations

import json

from helpers import FakeCaller, Hands, make_clock
from prahari import cli, indriyas, mcp, watches
from prahari.http import Api
from prahari.looking import Called

WEATHER = {"tool": "weather_now", "args": {"place": "Cary"}}


def outside(store, **extra):
    return indriyas.create(store, name="outside-temp", check=WEATHER,
                           pick={"json": "temperature"}, thing="the outside temperature",
                           **extra)


def band(store, owner="local"):
    heat = watches.create(store, name="Heat the guestroom", sense="outside-temp",
                          when={"below": 60}, owner=owner)
    cool = watches.create(store, name="Cool the guestroom", sense="outside-temp",
                          when={"above": 70}, owner=owner)
    return heat, cool


class TestEachReadingSaysWhatCameOfIt:
    def test_a_reading_names_each_watchs_decision(self, tmp_path):
        store, clock = make_clock(tmp_path, FakeCaller('{"temperature": 56}'))
        made = outside(store)
        band(store)
        clock.read_now(made.id)
        [row] = indriyas.history(store, made)
        assert row["value"] == "56" and row["came_by"] == "now"
        assert row["came_words"] == "read now, by hand"
        decided = {d["name"]: d["outcome"] for d in row["decided"]}
        assert decided == {"Heat the guestroom": "fired", "Cool the guestroom": "learned"}
        assert next(d for d in row["decided"] if d["outcome"] == "fired")["notified"]
        clock.close()

    def test_a_failed_reading_shows_each_watch_told_why(self, tmp_path):
        store, clock = make_clock(tmp_path, FakeCaller(Called(ok=False, detail="down")))
        made = outside(store)
        band(store)
        clock.read_now(made.id)
        [row] = indriyas.history(store, made)
        assert row["outcome"] == "failed" and row["detail"] == "down"
        assert {d["outcome"] for d in row["decided"]} == {"failed"}
        assert "could not read" in row["decided"][0]["why"]
        clock.close()

    def test_how_each_came(self, tmp_path):
        hands = Hands()
        caller = FakeCaller('{"temperature": 56}')
        store, clock = make_clock(tmp_path, caller, now=hands)
        made = outside(store)
        store.update_indriya(made.id, next_at="2026-10-22T09:00:00+00:00")
        [f.result() for f in clock.tick()]
        indriyas.fresh(store, caller, store.get_indriya(made.id), indriyas.max_age("0"))
        sent = indriyas.create(store, name="room-temp", pushed=True)
        clock.push(sent, json.dumps({"value": 66}))
        store.update_indriya(sent.id, next_at="2026-10-22T09:00:00+00:00")
        clock.tick()
        assert [r["came_by"] for r in indriyas.history(store, made)] == ["asked", "clock"]
        assert [r["came_by"] for r in indriyas.history(store, sent)] == ["silence", "pushed"]
        assert indriyas.history(store, sent)[0]["came_words"] == "nothing came in time"
        clock.close()

    def test_a_fresh_read_says_no_watch_decides_on_it(self, tmp_path):
        caller = FakeCaller('{"temperature": 49}')
        store, clock = make_clock(tmp_path, caller)
        made = outside(store)
        band(store)
        indriyas.fresh(store, caller, made, indriyas.max_age("0"))
        rows = indriyas.history(store, made)
        assert rows[0]["came_by"] == "asked" and rows[0]["decided"] == []
        assert "    (read on asking: no watch decides on these)" in \
            indriyas.history_lines(rows)
        clock.close()


class TestSomeoneElsesWatches:
    def test_are_counted_not_named(self, tmp_path):
        store, clock = make_clock(tmp_path, FakeCaller('{"temperature": 56}'))
        made = outside(store, share="house")
        band(store)
        watches.create(store, name="Asha's balcony", sense="outside-temp",
                       when={"below": 40}, owner="asha")
        clock.read_now(made.id)
        [row] = indriyas.history(store, made, people={"asha"})
        assert [d["name"] for d in row["decided"]] == ["Asha's balcony"]
        assert row["others"] == 2
        [everyone] = indriyas.history(store, made)      # the computer's own page
        assert len(everyone["decided"]) == 3 and everyone["others"] == 0
        clock.close()


class TestEveryDoor:
    def test_the_terminal(self, tmp_path, capsys):
        store, clock = make_clock(tmp_path, FakeCaller('{"temperature": 56}'))
        made = outside(store)
        band(store)
        clock.read_now(made.id)
        clock.close()
        del store
        assert cli.main(["--state", str(tmp_path), "indriya", "readings", "outside-temp"]) == 0
        out = capsys.readouterr().out
        assert "read 56  (read now, by hand)" in out
        assert "→ Heat the guestroom: fired -- told you" in out
        assert "→ Cool the guestroom: learned" in out
        assert cli.main(["--state", str(tmp_path), "indriya", "readings", "outside-temp",
                         "--full"]) == 0
        full = capsys.readouterr().out
        assert "why: Read 56" in full and "came in: {\"temperature\": 56}" in full

    def test_the_api_and_the_agent(self, tmp_path):
        store, clock = make_clock(tmp_path, FakeCaller('{"temperature": 56}'))
        made = outside(store)
        band(store)
        clock.read_now(made.id)
        _, body = Api(store, clock, tmp_path).handle(
            "GET", "/api/indriyas/outside-temp/readings", {}, {})
        assert {d["outcome"] for d in body["readings"][0]["decided"]} == {"fired", "learned"}
        said = mcp.Tools(store, tmp_path, FakeCaller("x"), person="local").call(
            "read_indriya", {"name": "outside-temp"})
        assert "→ Heat the guestroom: fired -- told you" in said
        clock.close()
