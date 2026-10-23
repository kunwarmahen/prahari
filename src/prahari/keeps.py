"""What Prahari keeps on this computer, for a backup to take.

A backup of the house (Sarathi's ``sarathi backup``) is one file holding
every program's own files, and each program says where its are --
``prahari keeps --json``, asked the way ``status --json`` is -- so the
program that packs it knows nothing of what is inside.

Prahari's is its state folder: the watches, their looks and what each
last saw (``prahari.sqlite3``, copied with SQLite's own backup), the
inlet's key a phone or Home Assistant knocks with -- restored, the
senders keep working without being given a new one -- the page's key,
and each look's working folder.

WHAT IS LEFT OUT: the record of a running watch (``serve.json``, and its
lock), which would name a process that isn't there.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

FORMAT = "prahari.keeps.v1"
LEAVE_OUT = ["serve.json", "serve.lock"]


def report(state: Path) -> dict[str, Any]:
    keeps = [{"id": "state", "path": str(state.resolve()),
              "what": "your watches, what each last saw, and the inlet's key",
              "leave_out": LEAVE_OUT, "exists": state.exists()}]
    return {"format": FORMAT, "keeps": keeps}
