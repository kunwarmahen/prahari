"""The agent's tools, in-process and as a real ``prahari mcp`` process.

The bias these tests encode: THE AGENT PROPOSES, THE PERSON ACCEPTS, AND
ONE PERSON'S SERVER IS THAT PERSON'S. Reading tools say so
(``readOnlyHint``) and every change does not, so a harness asks before
it; the model has no argument with which to reach another person's
watch; and a preview whose pick found nothing hands back what the tool
said, so the model can write a better pick before anybody is asked.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from helpers import FakeCaller
from prahari import mcp, watches
from prahari.store import Store

CHECK = {"tool": "web_fetch", "args": {"url": "https://x.example"}}


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "prahari.sqlite3")


def tools(store, tmp_path, person="asha", answer="Last 47"):
    return mcp.Tools(store, tmp_path, FakeCaller(answer), person=person, agent="/agents/a")


class TestTheHints:
    def test_reads_say_so_and_changes_do_not(self):
        hints = {t["name"]: t["annotations"]["readOnlyHint"] for t in mcp.TOOLS}
        assert {n for n, ro in hints.items() if ro} == {
            "preview_watch", "list_watches", "watch_looks"}
        assert hints["create_watch"] is False and hints["delete_watch"] is False


class TestTheTools:
    def test_preview_then_create_for_this_person_and_agent(self, store, tmp_path):
        t = tools(store, tmp_path)
        said = t.call("preview_watch", {"check": CHECK, "pick": {"number": ""},
                                        "when": {"below": 50}, "every": "3h"})
        assert "every 3 hours" in said and "already matches" in said
        made = t.call("create_watch", {"name": "ALAB", "check": CHECK,
                                       "pick": {"number": ""}, "when": {"below": 50},
                                       "every": "3h"})
        assert made.startswith("Saved ") and "not running on this machine" in made
        (watch,) = store.watches()
        assert watch.owner == "asha" and watch.agent == "/agents/a"
        assert watch.created_via == "agent"

    def test_a_preview_that_found_nothing_shows_the_answer(self, store, tmp_path):
        said = tools(store, tmp_path, answer="<b>Price</b> forty seven").call(
            "preview_watch", {"check": CHECK, "pick": {"number": ""},
                              "when": {"below": 50}, "every": "3h"})
        assert "found nothing" in said and "<b>Price</b> forty seven" in said

    def test_another_persons_watch_is_no_watch(self, store, tmp_path):
        theirs = watches.create(store, name="x", check=CHECK, pick={}, when={"changed": True},
                                every="1h", owner="ravi")
        t = tools(store, tmp_path, person="asha")
        assert t.call("list_watches", {}) == "No watches yet."
        for name in ("pause_watch", "delete_watch", "watch_looks"):
            with pytest.raises(mcp.ToolFailed, match="no watch"):
                t.call(name, {"id": theirs.id})
        assert store.get(theirs.id).state == "active"

    def test_mend_a_broken_watch(self, store, tmp_path):
        t = tools(store, tmp_path)
        t.call("create_watch", {"name": "p", "check": CHECK, "pick": {"number": "Last"},
                                "when": {"below": 50}, "every": "1h"})
        (watch,) = store.watches()
        watches.pause(store, watch.id, because="broken 3 times in a row; last: ...")
        said = t.call("update_watch", {"id": watch.id, "pick": {"number": "Price"}})
        assert said.startswith(f"Updated {watch.id}")
        assert store.get(watch.id).state == "active"

    def test_a_mistake_is_a_failed_call_the_model_can_read(self, store, tmp_path):
        with pytest.raises(mcp.ToolFailed, match="belw"):
            tools(store, tmp_path).call("create_watch", {
                "name": "x", "check": CHECK, "when": {"belw": 50}, "every": "1h"})


class TestTheProcess:
    def test_it_speaks_mcp_over_stdio(self, tmp_path):
        lines = [{"jsonrpc": "2.0", "id": 1, "method": "initialize",
                  "params": {"protocolVersion": "2025-06-18"}},
                 {"jsonrpc": "2.0", "method": "notifications/initialized"},
                 {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                 {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                  "params": {"name": "list_watches", "arguments": {}}}]
        done = subprocess.run(
            [sys.executable, "-m", "prahari.cli", "--state", str(tmp_path), "mcp",
             "--for", "local"], input="\n".join(json.dumps(m) for m in lines) + "\n",
            capture_output=True, text=True, timeout=30)
        replies = [json.loads(line) for line in done.stdout.splitlines()]
        assert [r["id"] for r in replies] == [1, 2, 3]
        assert replies[0]["result"]["serverInfo"]["name"] == "prahari"
        assert len(replies[1]["result"]["tools"]) == len(mcp.TOOLS)
        assert replies[2]["result"]["content"][0]["text"] == "No watches yet."
