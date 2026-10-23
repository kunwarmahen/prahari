"""`prahari keeps`: where the watches are, for a backup.

The bias: A BACKUP THAT MISSES THE WATCHES, OR MAKES A FILE. Sarathi packs
what this says and nothing else, so the folder must be the one Prahari
uses ($PRAHARI_STATE, --state), and asking must never create a database
in a folder that had none -- a fresh computer asked before a restore
would otherwise hold an empty file where the real watches go.
"""

from __future__ import annotations

import json

from prahari.cli import main


def test_the_place_is_prahari_state_and_asking_makes_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PRAHARI_STATE", str(tmp_path / "prahari"))
    assert main(["keeps", "--json"]) == 0
    said = json.loads(capsys.readouterr().out)
    assert said["format"] == "prahari.keeps.v1"
    place = said["keeps"][0]
    assert place["path"] == str(tmp_path / "prahari") and place["exists"] is False
    assert not (tmp_path / "prahari").exists()


def test_the_running_watchs_record_is_left_out_and_the_watches_are_not(tmp_path, capsys):
    assert main(["--state", str(tmp_path), "keeps", "--json"]) == 0
    place = json.loads(capsys.readouterr().out)["keeps"][0]
    assert place["path"] == str(tmp_path) and place["exists"] is True
    assert "serve.json" in place["leave_out"]
    assert "prahari.sqlite3" not in place["leave_out"] and "inlet.token" not in place["leave_out"]
