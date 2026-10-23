"""Mail pushed to Prahari: a folder kept open with IMAP IDLE, on a real
local socket (fake_imap.py).

The bias these tests encode: A PUSHED MAIL IS NEWS ONCE, AND ONLY NEW
MAIL IS. The first connection learns what is there and knocks for
nothing; a mail that lands while idling knocks at once, with who it is
from and its subject and nothing of what it says; mail that came while
the connection was down knocks when it is back, by UID, once. And the
password is the person's: kept apart from the watches, readable by them
alone, and never sent to another computer without TLS.
"""

from __future__ import annotations

import stat
import time

import pytest

from fake_imap import FakeImap
from prahari import mailbox
from prahari.store import Store


@pytest.fixture
def imap():
    server = FakeImap()
    yield server
    server.close()


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "prahari.sqlite3")


def added(store, tmp_path, imap, **kw):
    return mailbox.add(store, tmp_path, name=kw.get("name", "work-mail"),
                       owner=kw.get("owner", "local"), server="127.0.0.1",
                       port=imap.port, user="me@example.com",
                       password=kw.get("password", "app-password"), tls=False)


class Knocks:
    def __init__(self) -> None:
        self.heard: list[tuple[str, dict, set]] = []

    def __call__(self, word, body, owners) -> int:
        self.heard.append((word, body, owners))
        return 1

    def wait(self, n: int, limit: float = 10.0) -> None:
        end = time.monotonic() + limit
        while len(self.heard) < n and time.monotonic() < end:
            time.sleep(0.05)


def keeper(store, tmp_path, box, knocks):
    keep = mailbox.Keeper(store, tmp_path, box, knocks, idle_for=2, backoff=(0.2,))
    keep.start()
    return keep


class TestAdding:
    def test_it_opens_before_it_is_kept_and_learns_where_the_folder_is(self, store,
                                                                       tmp_path, imap):
        imap.deliver("Old <old@example.com>", "already here")
        box, said = added(store, tmp_path, imap)
        assert "opened INBOX" in said
        kept = store.mailbox("local", "work-mail")
        assert kept.last_uid == 1 and kept.uidvalidity == 7
        assert "EXAMINE" in imap.commands          # read-only: nothing marked read

    def test_a_wrong_password_is_said_and_nothing_is_kept(self, store, tmp_path, imap):
        with pytest.raises(mailbox.MailboxError, match="app password"):
            added(store, tmp_path, imap, password="wrong")
        assert store.mailboxes() == []

    def test_the_password_is_kept_apart_and_yours_alone(self, store, tmp_path, imap):
        box, _ = added(store, tmp_path, imap)
        secret = tmp_path / mailbox.SECRETS
        assert stat.S_IMODE(secret.stat().st_mode) == 0o600
        assert "app-password" not in (tmp_path / "prahari.sqlite3").read_bytes().decode(
            errors="replace")
        assert mailbox.password_of(tmp_path, box) == "app-password"
        mailbox.remove(store, tmp_path, "local", "work-mail")
        assert mailbox.password_of(tmp_path, box) == ""

    def test_plain_imap_to_another_computer_is_refused(self, store, tmp_path):
        with pytest.raises(mailbox.MailboxError, match="TLS"):
            mailbox.check_new(name="x-mail", server="imap.example.com", user="me",
                              tls=False)

    def test_its_name_is_a_word_at_the_inlet(self):
        with pytest.raises(mailbox.MailboxError, match="lowercase word"):
            mailbox.check_new(name="Work Mail", server="imap.example.com", user="me")


class TestListening:
    def test_a_mail_that_lands_while_idling_knocks_once_with_its_headers(
            self, store, tmp_path, imap):
        imap.deliver("Old <old@example.com>", "already here")
        box, _ = added(store, tmp_path, imap)
        knocks = Knocks()
        keep = keeper(store, tmp_path, box, knocks)
        try:
            assert imap.idle_started.wait(5)
            imap.deliver("Bank <alerts@bank.example>", "Your statement",
                         "<m2@bank.example>")
            knocks.wait(1)
        finally:
            keep.close()
        assert len(knocks.heard) == 1                # the old one was learned, not told
        word, body, owners = knocks.heard[0]
        assert word == "work-mail" and owners == {"local"}
        assert body["from"] == "Bank <alerts@bank.example>"
        assert body["subject"] == "Your statement" and body["id"] == "<m2@bank.example>"
        assert store.mailbox("local", "work-mail").last_uid == 2

    def test_mail_that_came_while_it_was_away_knocks_when_it_is_back(
            self, store, tmp_path, imap):
        box, _ = added(store, tmp_path, imap)
        imap.deliver("A <a@example.com>", "while you were out")
        knocks = Knocks()
        keep = keeper(store, tmp_path, store.mailbox("local", "work-mail"), knocks)
        try:
            knocks.wait(1)
        finally:
            keep.close()
        assert [b["subject"] for _, b, _ in knocks.heard] == ["while you were out"]

    def test_the_first_connection_of_a_renumbered_folder_learns_again(
            self, store, tmp_path, imap):
        imap.deliver("A <a@example.com>", "one")
        box, _ = added(store, tmp_path, imap)
        imap.validity = 8                          # the server renumbered the folder
        imap.deliver("B <b@example.com>", "two")
        knocks = Knocks()
        keep = keeper(store, tmp_path, store.mailbox("local", "work-mail"), knocks)
        try:
            assert imap.idle_started.wait(5)
        finally:
            keep.close()
        assert knocks.heard == []
        assert store.mailbox("local", "work-mail").uidvalidity == 8

    def test_trouble_is_said_on_the_mailbox_and_it_tries_again(self, store, tmp_path,
                                                               imap):
        box, _ = added(store, tmp_path, imap)
        mailbox.forget_password(tmp_path, box)
        keep = keeper(store, tmp_path, box, Knocks())
        time.sleep(0.5)
        keep.close()
        kept = store.mailbox("local", "work-mail")
        assert kept.state == "trouble" and "no password kept" in kept.said
