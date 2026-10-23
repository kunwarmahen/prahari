"""What Prahari keeps: the watches, every look, and what each has seen.

One SQLite file, ``prahari.sqlite3`` in the state directory, three
tables:

* ``watch`` -- the promise: what to look at, what to pick, when it
  matters, what to do then. A row changes (paused, its next look moved
  on, the last value it saw);
* ``look`` -- the receipt: one row per look or event, written once when
  it starts and once when it ends. ``fired`` says the watch woke the
  agent, and what came back;
* ``seen`` -- the keys of items a watch has already reported, so a mail
  is news once;
* ``inlet_key`` -- each person's own key to the inlet (http.py), so what
  one person's phone says reaches only that person's watches;
* ``mailbox`` -- the mail folders Prahari keeps open (mailbox.py), and
  where each one got to. Each names a Setu mail account; the password is
  in Setu, never here.

A LOOK THAT FOUND NOTHING IS A ROW TOO (``quiet``). "Is it still
watching?" deserves an answer with a time on it, not an absence.

EVERY TIME IS UTC, as ISO text, the same as Samay's file: readable with
the ``sqlite3`` shell and nothing else.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, fields
from datetime import UTC, datetime
from pathlib import Path

#: How a look ended.
#:   learned   the first look: what is there now is remembered, nothing fires
#:   quiet     looked; nothing worth telling
#:   fired     it mattered: the person was told, or the agent woke
#:   limited   it mattered, but the watch had fired its most for the day
#:   broken    the check answered, and the pick found nothing in it
#:   failed    the check itself failed (the tool's own words in detail)
#:   needs_person  a sign-in wall: paused until the person is back
#:   running   still going
#:   interrupted   Prahari stopped while it ran
OUTCOMES = ("learned", "quiet", "fired", "limited", "broken", "failed",
            "needs_person", "running", "interrupted")

#: Looks that count towards pausing a watch after too many in a row.
TROUBLE = ("broken", "failed")

RUNNERS = ("direct", "dvara")
STATES = ("active", "paused")

#: A then-turn's answer is kept, but not without limit.
REPLY_CAP = 20_000
#: Keys a watch remembers; the oldest go first past this.
SEEN_CAP = 5000


def now_utc() -> datetime:
    return datetime.now(UTC)


def iso(moment: datetime | None) -> str | None:
    return None if moment is None else moment.astimezone(UTC).isoformat(timespec="seconds")


def from_iso(text: str | None) -> datetime | None:
    return None if not text else datetime.fromisoformat(text)


@dataclass
class Watch:
    id: str
    owner: str
    #: A few words a person knows it by ("ALAB under $50").
    name: str
    #: One tool call that reads: {"tool": NAME, "args": {...}}. Empty for
    #: a watch that listens at the inlet instead.
    check: dict = field(default_factory=dict)
    #: The inlet's word this watch hears ("whatsapp"); "" for a check.
    listen: str = ""
    pick: dict = field(default_factory=dict)
    when: dict = field(default_factory=dict)
    #: How often to look ("3h"); "" for an inlet watch.
    every: str = ""
    #: What the agent is asked when it fires; "" to just tell the person.
    then: str = ""
    runner: str = "direct"
    agent: str = ""                  # package dir (direct) or name (dvara)
    #: Tools the then-turn may use without asking.
    allow_tools: list[str] = field(default_factory=list)
    #: Minutes a then-turn's question may wait for the person, in all.
    wait: int = 30
    time_limit: int = 600            # seconds, for the then-turn
    max_per_day: int = 10
    state: str = "active"
    paused_because: str = ""
    created_at: str = ""
    created_via: str = "cli"
    next_at: str | None = None
    #: Broken or failed looks in a row; reset by any look that worked.
    trouble: int = 0
    #: The first look has been made (it only learns what is there).
    looked: bool = False
    #: The last value picked, as JSON, for ``changed``.
    last_value: str = ""
    #: An edged test may fire: it was false at the last look.
    armed: bool = True
    #: A word at the inlet that makes this watch look NOW, instead of at
    #: its next ``every`` -- mail pushed by a mailbox or by Gmail. "" for
    #: none. The look is the same check; the knock only says "look".
    wake: str = ""
    #: A call that keeps the sender knocking -- Gmail's push lasts seven
    #: days -- made when the watch starts and once a day: {"tool", "args"}.
    renew: dict = field(default_factory=dict)
    renew_at: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Look:
    id: str
    watch: str
    started_at: str
    outcome: str = "running"
    ended_at: str | None = None
    #: How the look came: "clock", "now" (a person asked), "inlet", "wake"
    #: (a knock on its word), "renew" (the call keeping a push alive).
    came_by: str = "clock"
    #: The picked value, in a few words.
    value: str = ""
    #: What it found worth telling (new items' lines, the value said).
    found: list[str] = field(default_factory=list)
    detail: str = ""
    #: The then-turn: how it went, what it said, and whether it was sent.
    turn: str = ""
    reply: str = ""
    notified: bool = False
    cost_usd: float = 0.0
    dvara_run_id: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


_JSON_COLUMNS = {"check", "pick", "when", "allow_tools", "found", "renew"}
_BOOL_COLUMNS = {"looked", "armed", "notified", "tls"}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS watch (
    id TEXT PRIMARY KEY,
    owner TEXT NOT NULL,
    name TEXT NOT NULL,
    "check" TEXT NOT NULL,
    listen TEXT NOT NULL,
    pick TEXT NOT NULL,
    "when" TEXT NOT NULL,
    every TEXT NOT NULL,
    "then" TEXT NOT NULL,
    runner TEXT NOT NULL,
    agent TEXT NOT NULL,
    allow_tools TEXT NOT NULL,
    wait INTEGER NOT NULL,
    time_limit INTEGER NOT NULL,
    max_per_day INTEGER NOT NULL,
    state TEXT NOT NULL,
    paused_because TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_via TEXT NOT NULL,
    next_at TEXT,
    trouble INTEGER NOT NULL,
    looked INTEGER NOT NULL,
    last_value TEXT NOT NULL,
    armed INTEGER NOT NULL,
    wake TEXT NOT NULL DEFAULT '',
    renew TEXT NOT NULL DEFAULT '{}',
    renew_at TEXT
);
CREATE TABLE IF NOT EXISTS look (
    id TEXT PRIMARY KEY,
    watch TEXT NOT NULL,
    started_at TEXT NOT NULL,
    outcome TEXT NOT NULL,
    ended_at TEXT,
    came_by TEXT NOT NULL,
    value TEXT NOT NULL,
    found TEXT NOT NULL,
    detail TEXT NOT NULL,
    turn TEXT NOT NULL,
    reply TEXT NOT NULL,
    notified INTEGER NOT NULL,
    cost_usd REAL NOT NULL,
    dvara_run_id TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS look_by_watch ON look (watch, started_at);
CREATE TABLE IF NOT EXISTS seen (
    watch TEXT NOT NULL,
    key TEXT NOT NULL,
    at TEXT NOT NULL,
    PRIMARY KEY (watch, key)
);
CREATE TABLE IF NOT EXISTS inlet_key (
    owner TEXT PRIMARY KEY,
    key TEXT NOT NULL,
    made_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS mailbox (
    name TEXT NOT NULL,
    owner TEXT NOT NULL,
    account TEXT NOT NULL DEFAULT '',
    server TEXT NOT NULL,
    port INTEGER NOT NULL,
    user TEXT NOT NULL,
    folder TEXT NOT NULL,
    tls INTEGER NOT NULL,
    made_at TEXT NOT NULL,
    uidvalidity INTEGER,
    last_uid INTEGER,
    state TEXT NOT NULL,
    said TEXT NOT NULL,
    said_at TEXT,
    PRIMARY KEY (owner, name)
);
"""

#: Columns a file made before them lacks, added on open: (name, SQL type).
_ADDED = {"watch": (("wake", "TEXT NOT NULL DEFAULT ''"),
                    ("renew", "TEXT NOT NULL DEFAULT '{}'"),
                    ("renew_at", "TEXT")),
          "mailbox": (("account", "TEXT NOT NULL DEFAULT ''"),)}


class Store:
    """The file, and the only code that touches it."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript(_SCHEMA)
            for table, added in _ADDED.items():
                have = {r[1] for r in db.execute(f"PRAGMA table_info({table})")}
                for name, kind in added:
                    if name not in have:
                        db.execute(f'ALTER TABLE {table} ADD COLUMN "{name}" {kind}')

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        # A connection per use, as in Samay: the clock writes from worker
        # threads, the CLI and the page from elsewhere, and SQLite's own
        # locking keeps them apart.
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    # -- watches -----------------------------------------------------------

    def add(self, watch: Watch) -> Watch:
        if not watch.id:
            watch.id = self._new_id("watch")
        if not watch.created_at:
            watch.created_at = iso(now_utc())
        self._put("watch", watch)
        return watch

    def get(self, watch_id: str) -> Watch | None:
        with self._db() as db:
            row = db.execute("SELECT * FROM watch WHERE id = ?", (watch_id,)).fetchone()
        return _load(Watch, row) if row else None

    def watches(self, owner: str | None = None, state: str | None = None,
                listen: str | None = None, wake: str | None = None) -> list[Watch]:
        query, where, args = "SELECT * FROM watch", [], []
        for column, value in (("owner", owner), ("state", state), ("listen", listen),
                              ("wake", wake)):
            if value is not None:
                where.append(f"{column} = ?")
                args.append(value)
        if where:
            query += " WHERE " + " AND ".join(where)
        with self._db() as db:
            rows = db.execute(query + " ORDER BY created_at", args).fetchall()
        return [_load(Watch, r) for r in rows]

    def update(self, watch_id: str, **changes) -> None:
        if not changes:
            return
        cols = ", ".join(f'"{k}" = ?' for k in changes)
        with self._db() as db:
            db.execute(f"UPDATE watch SET {cols} WHERE id = ?",
                       [*(_dump(k, v) for k, v in changes.items()), watch_id])

    def delete(self, watch_id: str) -> bool:
        """Forget a watch, its looks and what it saw."""
        with self._db() as db:
            gone = db.execute("DELETE FROM watch WHERE id = ?", (watch_id,)).rowcount
            db.execute("DELETE FROM look WHERE watch = ?", (watch_id,))
            db.execute("DELETE FROM seen WHERE watch = ?", (watch_id,))
        return bool(gone)

    # -- looks -------------------------------------------------------------

    def start_look(self, watch_id: str, came_by: str = "clock",
                   at: datetime | None = None) -> Look:
        look = Look(id=self._new_id("look"), watch=watch_id,
                    started_at=iso(at or now_utc()), came_by=came_by)
        self._put("look", look)
        return look

    def finish_look(self, look: Look, at: datetime | None = None) -> None:
        look.ended_at = look.ended_at or iso(at or now_utc())
        look.reply = look.reply[:REPLY_CAP]
        self._put("look", look)

    def looks(self, watch_id: str | None = None, limit: int = 50,
              owner: str | None = None) -> list[Look]:
        query = "SELECT look.* FROM look"
        where, args = [], []
        if owner is not None:
            query += " JOIN watch ON watch.id = look.watch"
            where.append("watch.owner = ?")
            args.append(owner)
        if watch_id is not None:
            where.append("look.watch = ?")
            args.append(watch_id)
        if where:
            query += " WHERE " + " AND ".join(where)
        query += " ORDER BY look.started_at DESC LIMIT ?"
        with self._db() as db:
            rows = db.execute(query, [*args, limit]).fetchall()
        return [_load(Look, r) for r in rows]

    def fired_since(self, watch_id: str, since: datetime) -> int:
        """How many times it fired since a time -- the day's limit."""
        with self._db() as db:
            return db.execute(
                "SELECT COUNT(*) FROM look WHERE watch = ? AND outcome = 'fired' "
                "AND started_at >= ?", (watch_id, iso(since))).fetchone()[0]

    def limited_since(self, watch_id: str, since: datetime) -> int:
        with self._db() as db:
            return db.execute(
                "SELECT COUNT(*) FROM look WHERE watch = ? AND outcome = 'limited' "
                "AND started_at >= ?", (watch_id, iso(since))).fetchone()[0]

    def interrupt_unfinished(self, at: datetime | None = None) -> int:
        with self._db() as db:
            return db.execute(
                "UPDATE look SET outcome = 'interrupted', ended_at = ?, detail = "
                "'Prahari stopped while this was running; it was not run again.' "
                "WHERE outcome = 'running'", (iso(at or now_utc()),)).rowcount

    # -- seen --------------------------------------------------------------

    def unseen(self, watch_id: str, keys: list[str]) -> list[str]:
        """The keys among these not seen before, in their order."""
        if not keys:
            return []
        with self._db() as db:
            have = set()
            for start in range(0, len(keys), 500):
                chunk = keys[start:start + 500]
                marks = ",".join("?" for _ in chunk)
                have |= {r[0] for r in db.execute(
                    f"SELECT key FROM seen WHERE watch = ? AND key IN ({marks})",
                    [watch_id, *chunk])}
        return [k for k in dict.fromkeys(keys) if k not in have]

    def remember(self, watch_id: str, keys: list[str], at: datetime | None = None) -> None:
        if not keys:
            return
        when = iso(at or now_utc())
        with self._db() as db:
            db.executemany("INSERT OR IGNORE INTO seen (watch, key, at) VALUES (?, ?, ?)",
                           [(watch_id, k, when) for k in keys])
            db.execute(
                "DELETE FROM seen WHERE watch = ? AND key NOT IN (SELECT key FROM seen "
                "WHERE watch = ? ORDER BY at DESC, rowid DESC LIMIT ?)",
                (watch_id, watch_id, SEEN_CAP))

    def forget_seen(self, watch_id: str) -> None:
        with self._db() as db:
            db.execute("DELETE FROM seen WHERE watch = ?", (watch_id,))

    # -- each person's inlet key ---------------------------------------------

    def inlet_key(self, owner: str) -> str:
        """This person's key to the inlet, made the first time it is asked for."""
        with self._db() as db:
            row = db.execute("SELECT key FROM inlet_key WHERE owner = ?",
                             (owner,)).fetchone()
            if row:
                return row[0]
            key = secrets.token_urlsafe(24)
            db.execute("INSERT INTO inlet_key (owner, key, made_at) VALUES (?, ?, ?)",
                       (owner, key, iso(now_utc())))
            return key

    def inlet_keys(self) -> dict[str, str]:
        """Every person's key, by person."""
        with self._db() as db:
            return {r[0]: r[1] for r in db.execute("SELECT owner, key FROM inlet_key")}

    def new_inlet_key(self, owner: str) -> str:
        """A fresh key for this person; the old one stops opening the inlet."""
        with self._db() as db:
            db.execute("DELETE FROM inlet_key WHERE owner = ?", (owner,))
        return self.inlet_key(owner)

    # -- mailboxes -----------------------------------------------------------

    def put_mailbox(self, box) -> None:
        self._put("mailbox", box)

    def mailboxes(self, owner: str | None = None):
        from prahari.mailbox import Mailbox

        query, args = "SELECT * FROM mailbox", []
        if owner is not None:
            query, args = query + " WHERE owner = ?", [owner]
        with self._db() as db:
            rows = db.execute(query + " ORDER BY owner, name", args).fetchall()
        return [_load(Mailbox, r) for r in rows]

    def mailbox(self, owner: str, name: str):
        found = [b for b in self.mailboxes(owner) if b.name == name]
        return found[0] if found else None

    def update_mailbox(self, owner: str, name: str, **changes) -> None:
        if not changes:
            return
        cols = ", ".join(f'"{k}" = ?' for k in changes)
        with self._db() as db:
            db.execute(f"UPDATE mailbox SET {cols} WHERE owner = ? AND name = ?",
                       [*(_dump(k, v) for k, v in changes.items()), owner, name])

    def delete_mailbox(self, owner: str, name: str) -> bool:
        with self._db() as db:
            return bool(db.execute("DELETE FROM mailbox WHERE owner = ? AND name = ?",
                                   (owner, name)).rowcount)

    # -- plumbing ----------------------------------------------------------

    def _new_id(self, table: str) -> str:
        with self._db() as db:
            while True:
                candidate = secrets.token_hex(4)
                if not db.execute(f"SELECT 1 FROM {table} WHERE id = ?",
                                  (candidate,)).fetchone():
                    return candidate

    def _put(self, table: str, record) -> None:
        names = [f.name for f in fields(record)]
        cols = ", ".join(f'"{n}"' for n in names)
        marks = ", ".join("?" for _ in names)
        with self._db() as db:
            db.execute(f"INSERT OR REPLACE INTO {table} ({cols}) VALUES ({marks})",
                       [_dump(n, getattr(record, n)) for n in names])


def _dump(name: str, value):
    if name in _JSON_COLUMNS:
        return json.dumps(value)
    if isinstance(value, bool):
        return int(value)
    return value


def _load(cls, row: sqlite3.Row):
    data = {}
    for f in fields(cls):
        value = row[f.name]
        if f.name in _JSON_COLUMNS:
            value = json.loads(value)
        elif f.name in _BOOL_COLUMNS:
            value = bool(value)
        data[f.name] = value
    return cls(**data)
