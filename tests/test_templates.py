"""Indriya templates: a reading with blanks, installed filled in.

The bias these tests encode: A TEMPLATE IS SOMEBODY ELSE'S WORDS, so
against one that does more than it says -- a blank that adds a parameter
to an address, a template with a second call or a key nobody reads, an
input it never declared taken anyway, one fetched from a marketplace that
no reviewer the person trusts signed -- and against an install that runs
a reading for someone else instead of making the person their own.
"""

from __future__ import annotations

import json
import sys

import pytest

from helpers import FakeCaller, make_clock
from prahari import indriyas, mcp, templates
from prahari.watches import WatchError

MINE = """kind = "indriya"
name = "city-temp"
title = "A city's temperature"
version = "2"
thing = "the temperature"
[inputs.city]
kind = "text"
[check]
tool = "web_fetch"
args = { url = "https://w.example/now?city={{inputs.city}}&units=f" }
pick = "number"
"""


def test_the_ones_that_come_with_prahari_read_and_say_what_they_call():
    found = {t.name: t for t in templates.bundled()}
    assert {"outside-temp", "air-quality", "coin-price", "home-sensor"} <= set(found)
    calls = found["outside-temp"].card()["calls"]
    assert calls.startswith("web_fetch ") and "[latitude]" in calls and "every 15m" in calls
    assert found["home-sensor"].pushed
    assert found["home-sensor"].card()["calls"].startswith("no call")


def test_installing_fills_the_blanks_into_the_persons_own_indriya(tmp_path):
    store, _ = make_clock(tmp_path, FakeCaller("1"))
    made = templates.install(store, templates.find("outside-temp"),
                             {"latitude": "35.79", "longitude": -78.78}, owner="asha")
    assert made.owner == "asha" and made.name == "outside-temp"
    url = made.check["args"]["url"]
    assert "latitude=35.79&longitude=-78.78&" in url and "temperature_unit=fahrenheit" in url
    assert made.pick == {"json": "current.temperature_2m"} and made.every == "15m"
    assert made.created_via == "cli: template outside-temp v1"


def test_a_blank_in_an_address_is_one_value_and_cannot_add_a_parameter(tmp_path):
    store, _ = make_clock(tmp_path, FakeCaller("1"))
    made = templates.install(store, templates.parse(MINE), {"city": "Cary&key=stolen"})
    assert made.check["args"]["url"] == ("https://w.example/now?city=Cary%26key%3Dstolen"
                                         "&units=f")


def test_a_number_blank_takes_only_a_number_and_none_is_left_empty(tmp_path):
    store, _ = make_clock(tmp_path, FakeCaller("1"))
    template = templates.find("outside-temp")
    with pytest.raises(WatchError, match="latitude is a number"):
        templates.install(store, template, {"latitude": "north", "longitude": 1})
    with pytest.raises(WatchError, match="needs longitude filled in"):
        templates.install(store, template, {"latitude": 1})
    with pytest.raises(WatchError, match="has no input city"):
        templates.install(store, template, {"latitude": 1, "longitude": 1, "city": "x"})


def test_a_template_with_more_than_one_call_and_blanks_is_refused():
    with pytest.raises(WatchError, match="unknown keys"):
        templates.parse(MINE + '[[steps]]\nid = "x"\n')
    with pytest.raises(WatchError, match="not one of the template's inputs"):
        templates.parse(MINE.replace("{{inputs.city}}", "{{inputs.place}}"))
    with pytest.raises(WatchError, match='kind = "indriya"'):
        templates.parse(MINE.replace('kind = "indriya"\n', ""))
    with pytest.raises(WatchError, match="indriya's name"):
        templates.parse(MINE.replace('name = "city-temp"', 'name = "City Temp"'))


def test_a_name_of_your_own_and_a_pace_of_your_own(tmp_path):
    store, _ = make_clock(tmp_path, FakeCaller("1"))
    template = templates.find("coin-price")
    btc = templates.install(store, template, {}, name="btc", every="30m")
    eth = templates.install(store, template, {"coin": "ETH"}, name="eth")
    assert (btc.name, btc.every, eth.name) == ("btc", "30m", "eth")
    assert eth.check["args"]["url"].endswith("/ETH-USD/spot")


def test_a_pushed_template_makes_no_call(tmp_path):
    store, _ = make_clock(tmp_path, FakeCaller("1"))
    made = templates.install(store, templates.find("home-sensor"), {}, name="guestroom-temp")
    assert made.pushed and made.check == {} and made.every == "1h"


# -- from a marketplace, through Vidhi --------------------------------------------


def _vidhi(tmp_path, monkeypatch, answers: dict):
    """A stand-in ``vidhi`` that answers ``market list`` / ``market get``."""
    script = tmp_path / "vidhi.py"
    script.write_text(
        "import json, sys\nargs = sys.argv[1:]\n"
        f"answers = {json.dumps(answers)}\n"
        "key = ' '.join(args[:2]) + (' ' + args[2] if args[1] == 'get' else '')\n"
        "got = answers.get(key)\n"
        "if isinstance(got, str):\n"
        "    print('error: ' + got, file=sys.stderr); sys.exit(1)\n"
        "print(json.dumps(got))\n")
    monkeypatch.setenv("PRAHARI_VIDHI", f"{sys.executable} {script}")


def test_one_from_the_marketplace_says_who_signed_it(tmp_path, monkeypatch):
    _vidhi(tmp_path, monkeypatch, {
        "market get city-temp": {"kind": "indriya", "toml": MINE, "signed_by": "rita"},
        "market list": [{"name": "city-temp", "title": "A city's temperature",
                         "kind": "indriya", "reviewer": "rita"}]})
    assert [t["name"] for t in templates.market()] == ["city-temp"]
    store, _ = make_clock(tmp_path, FakeCaller("1"))
    template = templates.fetch("city-temp")
    made = templates.install(store, template, {"city": "Cary"})
    assert made.created_via == "cli: template city-temp v2, signed by rita"


def test_one_no_trusted_reviewer_signed_is_not_installed(tmp_path, monkeypatch):
    _vidhi(tmp_path, monkeypatch, {
        "market get city-temp": "its signature is by nobody on the trusted reviewers' list",
        "market get brief": {"kind": "routine", "toml": "", "signed_by": "rita"}})
    with pytest.raises(WatchError, match="nobody on the trusted reviewers"):
        templates.fetch("city-temp")
    with pytest.raises(WatchError, match="is a routine, not an indriya template"):
        templates.fetch("brief")


def test_the_agent_installs_one_and_hears_what_it_made(tmp_path):
    store, _ = make_clock(tmp_path, FakeCaller("1"))
    tools = mcp.Tools(store, tmp_path, FakeCaller("1"), person="asha", agent="/agents/a")
    listed = tools.call("indriya_templates", {})
    assert "outside-temp: Outside temperature -- calls web_fetch" in listed
    said = tools.call("install_indriya_template", {
        "template": "air-quality", "inputs": {"latitude": 35.79, "longitude": -78.78}})
    assert said.startswith("Saved indriya air-quality from the template air-quality")
    assert indriyas.find(store, "air-quality", "asha").owner == "asha"
