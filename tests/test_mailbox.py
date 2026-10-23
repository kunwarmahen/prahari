"""Mail pushed to Prahari: a folder kept open with IMAP IDLE, on a real
local socket (fake_imap.py).

The bias these tests encode: A PUSHED MAIL IS NEWS ONCE, AND ONLY NEW
MAIL IS. The first connection learns what is there and knocks for
nothing; a mail that lands while idling knocks at once, with who it is
from and its subject and nothing of what it says; mail that came while
the connection was down knocks when it is back, by UID, once. And the
password is the person's: kept apart from the watches, readable by them
THE PASSWORD IS SETU'S. A mailbox names a Setu mail account and keeps
nothing else: its login is asked for at each connection -- from this
computer's Setu for its own person, from Dvara for anyone else's -- and
no password is ever written into Prahari's folder.
"""

from __future__ import annotations

import json
import sys
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


class SetuSays:
    """Setu's login for a mail account, as a fake: what it hands, and how
    often it was asked."""

    def __init__(self, imap, password="app-password") -> None:
        self.imap = imap
        self.password = password
        self.asked: list[tuple[str, str]] = []

    def __call__(self, box) -> dict:
        self.asked.append((box.owner, box.account))
        return {"server": "127.0.0.1", "port": self.imap.port, "user": "me@example.com",
                "password": self.password, "folder": "INBOX", "tls": False}


def added(store, imap, logins=None, **kw):
    return mailbox.add(store, name=kw.get("name", "work-mail"),
                       owner=kw.get("owner", "local"), account="mail:work",
                       logins=logins or SetuSays(imap))


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


def keeper(store, imap, box, knocks, logins=None):
    keep = mailbox.Keeper(store, box, knocks, logins or SetuSays(imap), idle_for=2,
                          backoff=(0.2,))
    keep.start()
    return keep


class TestAdding:
    def test_it_opens_with_setus_login_and_keeps_only_the_accounts_name(
            self, store, tmp_path, imap):
        imap.deliver("Old <old@example.com>", "already here")
        box, said = added(store, imap)
        assert "opened INBOX" in said and "(mail:work)" in said
        kept = store.mailbox("local", "work-mail")
        assert kept.account == "mail:work" and kept.last_uid == 1 and kept.uidvalidity == 7
        assert "EXAMINE" in imap.commands          # read-only: nothing marked read
        for path in tmp_path.rglob("*"):
            if path.is_file():
                assert b"app-password" not in path.read_bytes()

    def test_a_wrong_password_in_setu_is_said_and_nothing_is_kept(self, store, imap):
        with pytest.raises(mailbox.MailboxError, match="app password"):
            added(store, imap, SetuSays(imap, password="wrong"))
        assert store.mailboxes() == []

    def test_it_names_a_setu_mail_account(self):
        with pytest.raises(mailbox.MailboxError, match="setu connect mail"):
            mailbox.check_new(name="work-mail", account="gmail:personal")

    def test_its_name_is_a_word_at_the_inlet(self):
        with pytest.raises(mailbox.MailboxError, match="lowercase word"):
            mailbox.check_new(name="Work Mail", account="mail:work")


class TestWhereTheLoginComesFrom:
    def fake_setu(self, tmp_path, said: dict) -> list[str]:
        program = tmp_path / "setu"
        log = tmp_path / "setu.argv"
        program.write_text(f"#!{sys.executable}\nimport json, sys\n"
                           f"open({str(log)!r}, 'a').write(json.dumps(sys.argv[1:]) + '\\n')\n"
                           f"print(json.dumps({said!r}))\n")
        program.chmod(0o755)
        return [str(program)]

    def test_this_computers_person_asks_setu_login(self, tmp_path):
        command = self.fake_setu(tmp_path, {"server": "imap.example.com", "port": 993,
                                            "user": "me@example.com", "password": "p",
                                            "folder": "INBOX", "tls": True})
        logins = mailbox.Logins(home={"local", "mahen"}, command=command)
        got = logins(mailbox.Mailbox(name="m", owner="mahen", account="mail:work"))
        assert got["server"] == "imap.example.com"
        assert json.loads((tmp_path / "setu.argv").read_text()) == [
            "login", "mail:work", "--json"]

    def test_setus_refusal_is_said(self, tmp_path):
        command = self.fake_setu(tmp_path, {"error": "mail:work is locked: its folder opens "
                                                     "with its person's passphrase"})
        logins = mailbox.Logins(command=command)
        with pytest.raises(mailbox.MailboxError, match="is locked"):
            logins(mailbox.Mailbox(name="m", owner="local", account="mail:work"))

    def test_anyone_elses_comes_through_dvara_as_them(self):
        class Dvara:
            def __init__(self):
                self.asked = []

            def call(self, method, path, body, timeout=30):
                self.asked.append((method, path, body))
                return {"server": "imap.example.com", "port": 993, "user": "asha@x.com",
                        "password": "p", "folder": "INBOX", "tls": True}

        dvara = Dvara()
        got = mailbox.Logins(home={"local"}, dvara=dvara)(
            mailbox.Mailbox(name="m", owner="asha", account="mail:home"))
        assert got["user"] == "asha@x.com"
        assert dvara.asked == [("POST", "/mail-login", {"actor": "asha", "ref": "mail:home"})]

    def test_anyone_elses_without_dvara_is_refused_never_read_from_here(self, tmp_path):
        command = self.fake_setu(tmp_path, {"server": "s", "port": 1, "user": "u",
                                            "password": "p"})
        with pytest.raises(mailbox.MailboxError, match="through Dvara"):
            mailbox.Logins(home={"local"}, command=command)(
                mailbox.Mailbox(name="m", owner="asha", account="mail:home"))
        assert not (tmp_path / "setu.argv").exists()


class TestListening:
    def test_a_mail_that_lands_while_idling_knocks_once_with_its_headers(
            self, store, tmp_path, imap):
        imap.deliver("Old <old@example.com>", "already here")
        box, _ = added(store, imap)
        knocks = Knocks()
        keep = keeper(store, imap, box, knocks)
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
        box, _ = added(store, imap)
        imap.deliver("A <a@example.com>", "while you were out")
        knocks = Knocks()
        keep = keeper(store, imap, store.mailbox("local", "work-mail"), knocks)
        try:
            knocks.wait(1)
        finally:
            keep.close()
        assert [b["subject"] for _, b, _ in knocks.heard] == ["while you were out"]

    def test_the_first_connection_of_a_renumbered_folder_learns_again(
            self, store, tmp_path, imap):
        imap.deliver("A <a@example.com>", "one")
        box, _ = added(store, imap)
        imap.validity = 8                          # the server renumbered the folder
        imap.deliver("B <b@example.com>", "two")
        knocks = Knocks()
        keep = keeper(store, imap, store.mailbox("local", "work-mail"), knocks)
        try:
            assert imap.idle_started.wait(5)
        finally:
            keep.close()
        assert knocks.heard == []
        assert store.mailbox("local", "work-mail").uidvalidity == 8

    def test_a_login_setu_refuses_is_trouble_and_it_tries_again(self, store, imap):
        box, _ = added(store, imap)

        def locked(_box):
            raise mailbox.MailboxError("mail:work is locked: its folder opens with its "
                                       "person's passphrase")

        keep = keeper(store, imap, box, Knocks(), logins=locked)
        time.sleep(0.5)
        keep.close()
        kept = store.mailbox("local", "work-mail")
        assert kept.state == "trouble" and "is locked" in kept.said

    def test_each_connection_asks_setu_afresh(self, store, imap):
        box, _ = added(store, imap)
        logins = SetuSays(imap)
        keep = keeper(store, imap, box, Knocks(), logins=logins)
        try:
            assert imap.idle_started.wait(5)
        finally:
            keep.close()
        assert logins.asked == [("local", "mail:work")]
