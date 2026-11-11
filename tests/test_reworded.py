"""A mended test, and the words that still say the old one.

"Cool the guestroom above 70" mended to ``above 80`` acted at 80 and
still said 70 in every list, on every page and in every chat that showed
it. The bias these tests encode: A WATCH WHOSE NAME LIES ABOUT ITS TEST.

* A mend that changes the test's number says which words still carry
  the old one, and what they would say -- to the terminal, the agent and
  the page alike.
* Words the person changed in the same mend are theirs, and left alone;
  a number that is not the test's is left alone.
* Nothing is renamed by itself: the page carries the number into its
  boxes before Save, the agent offers it, the terminal says the flags.
"""

from __future__ import annotations

import json
import urllib.request

import pytest

from helpers import FakeCaller, FakeNotifier, make_clock
from prahari import mcp, watches
from prahari.http import Api, PrahariServer
from prahari.store import Store

CHECK = {"tool": "web_fetch", "args": {"url": "https://x.example"}}


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "p.sqlite3")


def cool(store, **extra):
    base = dict(name="Cool the guestroom above 70", asked="turn the AC on above 70",
                thing="guestroom at 70", check=CHECK, pick={"number": ""},
                when={"above": 70}, every="15m", owner="asha")
    return watches.create(store, **{**base, **extra})


class TestTheOldNumberIsNamed:
    def test_a_new_number_names_every_word_still_saying_the_old(self, store):
        made = cool(store)
        notes: list[str] = []
        after = watches.update(store, made.id, when={"above": 80}, notes=notes)
        assert after.when == {"above": 80}
        assert after.name == "Cool the guestroom above 70"      # not renamed by itself
        said = watches.reworded(made, after)
        assert said == {"name": "Cool the guestroom above 80",
                        "asked": "turn the AC on above 80", "thing": "guestroom at 80"}
        assert len(notes) == 1 and "still say the old test" in notes[0]
        assert '"Cool the guestroom above 80"' in notes[0]

    def test_words_changed_in_the_same_mend_are_the_person_s(self, store):
        made = cool(store)
        notes: list[str] = []
        after = watches.update(store, made.id, when={"above": 80},
                               name="AC on when hot", notes=notes)
        assert after.name == "AC on when hot"
        assert "name" not in watches.reworded(made, after, {"name", "when"})
        assert "asked" in notes[0] and "AC on when hot" not in notes[0]

    def test_a_number_not_in_the_test_is_left_alone(self, store):
        made = cool(store, name="Bedroom 2 above 70")
        after = watches.update(store, made.id, when={"above": 80})
        assert watches.reworded(made, after)["name"] == "Bedroom 2 above 80"

    def test_a_mend_that_keeps_the_number_says_nothing(self, store):
        made = cool(store)
        notes: list[str] = []
        watches.update(store, made.id, every="30m", notes=notes)
        watches.update(store, made.id, when={"at_least": 70}, notes=notes)
        assert notes == []

    def test_words_already_saying_the_new_number_say_nothing(self, store):
        made = cool(store)
        notes: list[str] = []
        watches.update(store, made.id, when={"above": 80}, name="Cool above 80",
                       asked="AC above 80", thing="guestroom heat", notes=notes)
        assert notes == []


class TestEveryDoorSaysIt:
    def test_the_agent_is_told_what_to_offer(self, store, tmp_path):
        made = cool(store)
        server = mcp.Tools(store, tmp_path, FakeCaller("Last 47"), person="asha",
                           agent="/agents/a")
        said = server.call("update_watch", {"id": made.id, "when": {"above": 80}})
        assert "still say the old test" in said and "Cool the guestroom above 80" in said

    def test_the_page_gets_the_note_with_the_card(self, tmp_path):
        store, clock = make_clock(tmp_path, FakeCaller("Last 47"), notifier=FakeNotifier())
        token = "page-token-0123456789"
        server = PrahariServer(Api(store, clock, tmp_path), token, "k" * 32, port=0)
        server.start()
        try:
            made = cool(store, owner="local")
            request = urllib.request.Request(
                server.url.rstrip("/") + f"/api/watches/{made.id}", method="PATCH",
                data=json.dumps({"when": {"above": 80},
                                 "name": "Cool the guestroom above 80"}).encode(),
                headers={"Authorization": f"Bearer {token}",
                         "Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=10) as response:
                card = json.loads(response.read())
        finally:
            server.stop()
            clock.close()
        assert card["name"] == "Cool the guestroom above 80"
        assert card["when"] == {"above": 80}
        assert len(card["notes"]) == 1 and "asked" in card["notes"][0]


class TestCarriedWhenAskedFor:
    def test_carry_words_changes_them_in_the_same_mend(self, store):
        made = cool(store)
        notes: list[str] = []
        after = watches.update(store, made.id, when={"above": 80}, carry_words=True,
                               notes=notes)
        assert after.name == "Cool the guestroom above 80"
        assert after.asked == "turn the AC on above 80" and after.thing == "guestroom at 80"
        assert notes == ["its name, asked, thing now say the new test too"]

    def test_the_terminal_flag(self, tmp_path, capsys):
        from prahari.cli import main
        made = cool(Store(tmp_path / "prahari.sqlite3"), owner="local")
        code = main(["--state", str(tmp_path), "edit", made.id, "--when", "above 80",
                     "--carry-words", "--json"])
        assert code == 0
        card = json.loads(capsys.readouterr().out)
        assert card["name"] == "Cool the guestroom above 80"

    def test_words_that_never_said_the_old_test_are_left_and_it_says_so(self, store):
        made = cool(store)
        watches.update(store, made.id, when={"above": 80})          # words still 70
        notes: list[str] = []
        after = watches.update(store, made.id, when={"above": 82}, carry_words=True,
                               notes=notes)
        assert after.name == "Cool the guestroom above 70"
        assert notes and "don't say its old test (above 80)" in notes[0]
