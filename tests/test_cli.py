"""The commands a person types, end to end on a state folder.

The bias these tests encode: WHAT A PERSON TYPES IS CHECKED THE SAME WAY
AS WHAT AN AGENT SENDS. The short forms (``--pick number``, ``--when
'below 50'``) become the same recipe the JSON would, and a mistake exits
2 with the words to fix it. ``prahari hear`` tries the inlet without the
network, the way a person checks a phone app's message before trusting
it.
"""

from __future__ import annotations

import json

from prahari import cli
from prahari.status import hold_watch, serving


def run(tmp_path, capsys, *argv) -> tuple[int, str, str]:
    rc = cli.main(["--state", str(tmp_path), *argv])
    out = capsys.readouterr()
    return rc, out.out, out.err


class TestAWatchByHand:
    def test_add_list_show_edit_rm(self, tmp_path, capsys):
        rc, out, _ = run(tmp_path, capsys, "add", "ALAB under $50", "--check", "web_fetch",
                         "--args", '{"url": "https://x.example"}', "--pick", "number",
                         "--when", "below 50", "--every", "3h")
        assert rc == 0 and "every 3 hours, looks at x.example (with web_fetch)" in out
        assert "prahari serve is not running" in out
        watch_id = out.split()[1].rstrip(":")
        rc, out, _ = run(tmp_path, capsys, "list")
        assert "ALAB under $50" in out and "not looked" not in out
        rc, out, _ = run(tmp_path, capsys, "show", watch_id[:4])
        assert '"below": 50' in out and "web_fetch" in out
        rc, out, _ = run(tmp_path, capsys, "edit", watch_id, "--every", "6h")
        assert rc == 0 and "every 6 hours" in out
        rc, out, _ = run(tmp_path, capsys, "rm", watch_id)
        assert rc == 0 and run(tmp_path, capsys, "list")[1].startswith("no watches")

    def test_a_mistake_exits_2_in_words(self, tmp_path, capsys):
        rc, _, err = run(tmp_path, capsys, "add", "x", "--check", "t", "--when",
                         "belw 50")
        assert rc == 2 and "when is one of" in err
        rc, _, err = run(tmp_path, capsys, "add", "x", "--check", "t", "--args", "{no",
                         "--when", "changed")
        assert rc == 2 and "--args is not JSON" in err


class TestHear:
    def test_hear_fires_what_listens(self, tmp_path, capsys):
        run(tmp_path, capsys, "add", "Mum", "--listen", "whatsapp", "--pick", "json:title",
            "--when", "contains Mum")
        rc, out, _ = run(tmp_path, capsys, "hear", "whatsapp",
                         '{"title": "Mum", "text": "call me"}', "--json")
        said = json.loads(out)
        assert rc == 0 and said["heard_by"] == 1 and len(said["fired"]) == 1
        rc, out, _ = run(tmp_path, capsys, "looks")
        assert "fired" in out and "Mum" in out


class TestStatus:
    def test_not_running_then_running(self, tmp_path, capsys):
        rc, out, _ = run(tmp_path, capsys, "status", "--json")
        said = json.loads(out)
        assert said["format"] == "prahari.status.v1" and said["serving"] is False
        assert said["mcp"]["args"][-1] == "mcp"
        held = hold_watch(tmp_path)
        try:
            (tmp_path / "serve.json").write_text(json.dumps({"url": "http://h:8782/"}))
            assert serving(tmp_path) == {"url": "http://h:8782/"}
            assert hold_watch(tmp_path) is None          # one watch at a time
            rc, out, _ = run(tmp_path, capsys, "status", "--json")
            assert json.loads(out)["inlet"] == "http://h:8782/inlet/"
        finally:
            held.close()
        assert serving(tmp_path) is None                  # gone with its holder

    def test_the_inlet_key_is_kept(self, tmp_path, capsys):
        rc, out, _ = run(tmp_path, capsys, "inlet", "--json")
        key = json.loads(out)["key"]
        assert len(key) >= 16 and json.loads(run(tmp_path, capsys, "inlet",
                                                 "--json")[1])["key"] == key
        assert oct((tmp_path / "inlet.token").stat().st_mode)[-3:] == "600"


class TestPushAndPeople:
    def test_a_watch_woken_by_a_word_says_so(self, tmp_path, capsys):
        rc, out, _ = run(tmp_path, capsys, "add", "Bank mail", "--check", "t",
                         "--args", '{"q": "from:bank"}', "--pick", r"items:thread (\w+)",
                         "--when", "new", "--every", "6h", "--wake", "work-mail")
        assert rc == 0 and "at once whenever work-mail knocks" in out

    def test_each_person_gets_their_own_inlet_key(self, tmp_path, capsys, monkeypatch):
        monkeypatch.delenv("PRAHARI_DVARA_URL", raising=False)
        mine = json.loads(run(tmp_path, capsys, "inlet", "--json")[1])
        theirs = json.loads(run(tmp_path, capsys, "inlet", "--for", "asha", "--json")[1])
        again = json.loads(run(tmp_path, capsys, "inlet", "--for", "asha", "--json")[1])
        fresh = json.loads(run(tmp_path, capsys, "inlet", "--for", "asha", "--new-key",
                               "--json")[1])
        assert mine["key"] != theirs["key"] and theirs["key"] == again["key"]
        assert fresh["key"] != theirs["key"] and theirs["for"] == "asha"

    def test_a_mailbox_names_its_setu_account_and_keeps_no_password(
            self, tmp_path, capsys, monkeypatch):
        import sys as _sys

        from fake_imap import FakeImap

        imap = FakeImap()
        setu = tmp_path / "setu"
        setu.write_text(f"#!{_sys.executable}\nimport json\nprint(json.dumps("
                        f"{{'server': '127.0.0.1', 'port': {imap.port}, 'user': "
                        "'me@example.com', 'password': 'app-password', 'folder': 'INBOX', "
                        "'tls': False}))\n")
        setu.chmod(0o755)
        monkeypatch.setenv("PRAHARI_SETU", str(setu))
        monkeypatch.delenv("PRAHARI_DVARA_URL", raising=False)
        try:
            rc, out, _ = run(tmp_path, capsys, "mailbox", "add", "work-mail", "--account",
                             "mail:work")
        finally:
            imap.close()
        assert rc == 0 and "kept as work-mail" in out and "--wake work-mail" in out
        rc, out, _ = run(tmp_path, capsys, "mailbox", "list")
        assert "mail:work" in out and "app-password" not in out
        assert b"app-password" not in (tmp_path / "prahari.sqlite3").read_bytes()
        rc, out, _ = run(tmp_path, capsys, "mailbox", "rm", "work-mail")
        assert rc == 0 and "stays in Setu" in out


def test_a_file_made_before_wake_opens_and_gains_it(tmp_path):
    import sqlite3

    from prahari.store import Store

    path = tmp_path / "prahari.sqlite3"
    Store(path)
    db = sqlite3.connect(path)
    for column in ("wake", "renew", "renew_at"):
        db.execute(f'ALTER TABLE watch DROP COLUMN "{column}"')
    db.commit()
    db.close()
    store = Store(path)
    from prahari import watches
    made = watches.create(store, name="x", check={"tool": "t", "args": {}},
                          when={"changed": True}, every="1h")
    assert store.get(made.id).wake == "" and store.get(made.id).renew == {}
