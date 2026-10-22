"""Making and mending watches.

The bias these tests encode: A WATCH IS CHECKED WHOLE BEFORE ANYTHING IS
SAVED, AND ONE PERSON'S WATCHES ARE NOBODY ELSE'S. A watch that both
looks and listens, or neither, is refused; another person's watch is "no
watch" to every lookup; and a mended recipe starts its memory over, so
values picked by the old pick are never compared with the new one's.
"""

from __future__ import annotations

import pytest

from helpers import FakeCaller
from prahari import watches
from prahari.looking import Called
from prahari.store import Store
from prahari.watches import WatchError

CHECK = {"tool": "web_fetch", "args": {"url": "https://x.example"}}


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "p.sqlite3")


def make(store, **extra):
    base = dict(name="price", check=CHECK, pick={"number": ""}, when={"below": 50},
                every="1h")
    return watches.create(store, **{**base, **extra})


class TestMadeWhole:
    def test_looks_or_listens_never_both(self, store):
        with pytest.raises(WatchError, match="not both"):
            make(store, listen="whatsapp")
        with pytest.raises(WatchError, match="needs a check"):
            make(store, check=None)

    def test_a_check_needs_every_and_a_listen_has_none(self, store):
        with pytest.raises(WatchError, match="how often"):
            make(store, every="")
        with pytest.raises(WatchError, match="has no every"):
            watches.create(store, name="w", listen="whatsapp", pick={}, when={"any": True},
                           every="1h")

    def test_a_check_is_a_tool_and_its_arguments(self, store):
        with pytest.raises(WatchError, match="unknown key.*url"):
            make(store, check={"tool": "web_fetch", "url": "x"})
        with pytest.raises(WatchError, match="exact name"):
            make(store, check={"tool": "web fetch", "args": {}})

    def test_a_listen_is_one_word_and_hears_anything_by_default(self, store):
        with pytest.raises(WatchError, match="one short lowercase word"):
            watches.create(store, name="w", listen="Whats App")
        watch = watches.create(store, name="w", listen="whatsapp")
        assert watch.when == {"any": True} and watch.looked and watch.next_at is None

    def test_a_new_watch_looks_soon(self, store):
        watch = make(store)
        assert watch.next_at and not watch.looked and watch.armed

    def test_a_cap_per_person(self, store, monkeypatch):
        monkeypatch.setenv("PRAHARI_MAX_WATCHES", "2")
        make(store)
        make(store)
        with pytest.raises(WatchError, match="has 2 watches already"):
            make(store)
        make(store, owner="asha")                 # someone else's count is theirs


class TestOnePersonsWatches:
    def test_another_persons_watch_is_no_watch(self, store):
        theirs = make(store, owner="asha")
        with pytest.raises(WatchError, match="no watch"):
            watches.find(store, theirs.id, owner="ravi")
        with pytest.raises(WatchError, match="no watch"):
            watches.pause(store, theirs.id, owner="ravi")
        assert watches.find(store, theirs.id[:4], owner="asha").id == theirs.id


class TestMending:
    def test_a_new_pick_starts_the_memory_over(self, store):
        watch = make(store)
        store.update(watch.id, looked=True, last_value="47.0", armed=False, trouble=2)
        store.remember(watch.id, ["a", "b"])
        mended = watches.update(store, watch.id, pick={"number": r"Last ([\d.]+)"})
        assert mended.pick == {"number": r"Last ([\d.]+)"}
        assert not mended.looked and mended.armed and mended.last_value == ""
        assert mended.trouble == 0 and store.unseen(watch.id, ["a"]) == ["a"]

    def test_a_watch_paused_because_it_broke_comes_back_when_mended(self, store):
        watch = make(store)
        watches.pause(store, watch.id, because="broken 3 times in a row; last: ...")
        assert watches.update(store, watch.id, pick={"number": "Last"}).state == "active"

    def test_a_watch_the_person_paused_stays_paused(self, store):
        watch = make(store)
        watches.pause(store, watch.id)
        assert watches.update(store, watch.id, pick={"number": "Last"}).state == "paused"

    def test_only_what_can_change(self, store):
        with pytest.raises(WatchError, match="can.t change listen"):
            watches.update(store, make(store).id, listen="sms")

    def test_a_new_then_keeps_the_memory(self, store):
        watch = make(store)
        store.update(watch.id, looked=True, last_value="47.0")
        assert watches.update(store, watch.id, then="say it").last_value == "47.0"


class TestPreview:
    def test_it_looks_without_a_grant_and_says_what_it_sees(self):
        caller = FakeCaller("Last 47.10")
        said = watches.preview(caller, check=CHECK, pick={"number": r"Last ([\d.]+)"},
                               when={"below": 50}, every="3h")
        assert caller.calls == [(CHECK, False)]          # nothing granted before a yes
        assert said["holds"] and "already matches" in said["said"]

    def test_a_pick_that_finds_nothing_shows_what_the_tool_said(self):
        said = watches.preview(FakeCaller("<html>Price: 47.10</html>"), check=CHECK,
                               pick={"number": "Last"}, when={"below": 50}, every="3h")
        assert said["found"] is False and "Price: 47.10" in said["result"]

    def test_a_tool_that_is_not_read_only_cannot_be_tried(self):
        caller = FakeCaller(Called(ok=False, detail="web_fetch is not read-only; ..."))
        said = watches.preview(caller, check=CHECK, pick={}, when={"changed": True},
                               every="1h")
        assert "can't be tried before the person accepts it" in said["said"]

    def test_a_listen_is_tried_on_a_sample(self):
        said = watches.preview(FakeCaller(), listen="whatsapp", pick={"json": "title"},
                               when={"contains": "Mum"}, sample={"title": "Mum"})
        assert said["holds"] is True
