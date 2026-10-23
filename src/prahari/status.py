"""What Prahari can tell a harness: is it here, is it watching, how to
talk to it -- ``prahari status --json``, the shape Setu and Samay set for
this family of programs.

THE WATCH HOLDS A LOCK, NOT A PID, as Samay's clock does (Samay's note
05): ``prahari serve`` takes an exclusive ``flock`` on ``serve.lock`` for
as long as it runs. A lock is let go by the kernel however its holder
dies, and every process that opens the same file sees it, whichever
container it is in; a pid in a file says neither.

WHERE NEWS GOES is the running watch's own (``dvara``, ``local_to``),
written by ``prahari serve``: a harness asks with its own environment,
which is not the watch's.

NO SECRET IS IN IT: neither the page's token nor the inlet's.
"""

from __future__ import annotations

import fcntl
import json
import os
import shutil
import sys
from pathlib import Path

from prahari import __version__
from prahari.store import Store

FORMAT = "prahari.status.v1"
LOCK_FILE = "serve.lock"


def prahari_command() -> str:
    beside = Path(sys.executable).parent / "prahari"
    if beside.exists():
        return str(beside)
    return shutil.which("prahari") or "prahari"


def hold_watch(state: Path):
    """Take the lock for this process's lifetime; the open file, or None
    when another ``prahari serve`` holds it."""
    state.mkdir(parents=True, exist_ok=True)
    held = open(state / LOCK_FILE, "a")  # noqa: SIM115 -- held until exit
    try:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        held.close()
        return None
    return held


def serving(state: Path) -> dict | None:
    """What ``prahari serve`` wrote when it started, if it still runs."""
    try:
        with open(state / LOCK_FILE) as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError:
                pass
            else:
                return None
    except OSError:
        return None
    try:
        info = json.loads((state / "serve.json").read_text())
    except (OSError, ValueError):
        info = {}
    return info if isinstance(info, dict) else {}


def report(state: Path, store: Store) -> dict:
    counts = {"active": 0, "paused": 0, "listening": 0}
    for watch in store.watches():
        counts[watch.state] = counts.get(watch.state, 0) + 1
        if watch.listen and watch.state == "active":
            counts["listening"] += 1
    served = serving(state)
    dvara = ((served or {}).get("dvara")
             or os.environ.get("PRAHARI_DVARA_URL", "").strip() or None)
    return {
        "format": FORMAT,
        "version": __version__,
        "state": str(state),
        "serving": served is not None,
        "url": served.get("url") if served else None,
        "watches": counts,
        "dvara": dvara,
        "local_to": str((served or {}).get("local_to") or ""),
        # Where something is sent to be heard: add the word, and the inlet's
        # key (prahari inlet prints both).
        "inlet": (served.get("url") + "inlet/") if served and served.get("url") else None,
        "inlet_public": ((served.get("inlet_public") + "inlet/")
                         if served and served.get("inlet_public") else None),
        "mailboxes": len(store.mailboxes()),
        "mcp": {"command": prahari_command(), "args": ["--state", str(state), "mcp"]},
    }
