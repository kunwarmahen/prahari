"""A reading made from a template whose review was taken back stops.

The bias these tests encode: against a take-back that reaches too far or
not far enough -- a reading made here, from one that comes with Prahari,
or mended by its owner, paused because a template of the same name was
taken back; a reading made from the exact reviewed text left running;
resume quietly undoing the pause; and Vidhi out of reach taken to mean
"pause everything" (or crashing the clock).
"""

from __future__ import annotations

import hashlib
import json
import sys

import pytest

from helpers import FakeCaller, FakeNotifier, Hands, make_clock
from prahari import indriyas, recipe, templates
from prahari.watches import WatchError

TEXT = """kind = "indriya"
name = "city-temp"
title = "A city's temperature"
version = "2"
[inputs.city]
kind = "text"
[check]
tool = "web_fetch"
args = { url = "https://w.example/now?city={{inputs.city}}" }
pick = "number"
"""
SHA = hashlib.sha256(TEXT.encode()).hexdigest()
BACK = {"name": "city-temp", "version": "2", "sha256": SHA, "reviewer": "rita",
        "why": "it calls a page that sells your city"}


def _vidhi(tmp_path, monkeypatch, answers: dict):
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


def _made(tmp_path, monkeypatch, revoked):
    _vidhi(tmp_path, monkeypatch, {
        "market get city-temp": {"kind": "indriya", "toml": TEXT, "signed_by": "rita"},
        "market revoked": revoked})
    notifier = FakeNotifier()
    store, clock = make_clock(tmp_path, FakeCaller("70"), notifier=notifier, now=Hands())
    made = templates.install(store, templates.fetch("city-temp"), {"city": "Cary"},
                             owner="asha")
    return store, clock, notifier, made


def test_a_reading_from_the_marketplace_keeps_the_exact_texts_hash(tmp_path, monkeypatch):
    store, _, _, made = _made(tmp_path, monkeypatch, [])
    assert made.template_sha256 == SHA
    own = templates.install(store, templates.find("coin-price"), {}, owner="asha")
    assert own.template_sha256 == ""


def test_the_clock_pauses_the_reading_and_says_who_and_why(tmp_path, monkeypatch):
    store, clock, notifier, made = _made(tmp_path, monkeypatch, [BACK])
    assert clock.check_take_backs() == ["city-temp"]
    now = store.get_indriya(made.id)
    assert now.state == "paused"
    assert now.paused_because == ("review taken back by rita (template city-temp version "
                                  "2): it calls a page that sells your city")
    text = notifier.sent[-1][1]
    assert "Paused: indriya city-temp" in text and "make it your own" in text
    assert "prahari indriya resume" not in text
    assert clock.check_take_backs() == []          # told once


def test_only_the_reviewed_text_is_paused(tmp_path, monkeypatch):
    other = {**BACK, "sha256": "0" * 64}
    store, clock, _, made = _made(tmp_path, monkeypatch, [other])
    plain = templates.install(store, templates.find("coin-price"), {}, owner="asha")
    assert clock.check_take_backs() == []
    assert store.get_indriya(made.id).state == "active"
    assert store.get_indriya(plain.id).state == "active"


def test_resume_is_refused_and_a_mended_reading_is_its_owners(tmp_path, monkeypatch):
    store, clock, _, made = _made(tmp_path, monkeypatch, [BACK])
    clock.check_take_backs()
    with pytest.raises(WatchError, match="review taken back by rita"):
        indriyas.resume(store, store.get_indriya(made.id))
    mended = indriyas.update(store, made.id, pick=recipe.pick_from_text("number:([\\d.]+)"))
    assert mended.state == "active" and mended.template_sha256 == ""
    assert clock.check_take_backs() == []


def test_vidhi_out_of_reach_pauses_nothing(tmp_path, monkeypatch):
    store, clock, _, made = _made(tmp_path, monkeypatch, "cannot reach vidhi")
    assert clock.check_take_backs() == []
    assert store.get_indriya(made.id).state == "active"


def test_the_clock_asks_hourly_and_only_when_a_reading_came_from_a_marketplace(tmp_path):
    asked = []
    store, clock = make_clock(tmp_path, FakeCaller("1"), now=Hands())
    clock.take_backs = lambda: asked.append(1) or []
    templates.install(store, templates.find("coin-price"), {})
    for future in clock.tick():
        future.result()
    assert asked == []                             # nothing from a marketplace
    made = templates.install(store, templates.find("air-quality"),
                             {"latitude": 1, "longitude": 2})
    store.update_indriya(made.id, template_sha256=SHA)
    for future in clock.tick():
        future.result()
    for future in clock.tick():
        future.result()
    assert asked == [1]                            # once, not every tick
    clock.now.move(hours=1, seconds=1)
    for future in clock.tick():
        future.result()
    assert asked == [1, 1]
