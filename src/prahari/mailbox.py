"""Mail pushed to Prahari: a mail folder kept open with IMAP IDLE.

A watch on mail looks every 15-30 minutes, so a mail waits that long to
be news. A mail server can say so itself: IMAP's IDLE leaves a
connection open, and the server writes ``* 12 EXISTS`` the moment a mail
lands. Prahari keeps such a connection per mailbox (``prahari mailbox
add``), and each new mail KNOCKS ON THE INLET, as the mailbox's person,
on the mailbox's name -- so the two kinds of watch work on it unchanged:

* a watch that LISTENS (``--listen work-mail``) reads the knock: who it
  is from, the subject, the date -- enough for "tell me when the bank
  writes", with no tool and no account anywhere but here;
* a watch that LOOKS and is woken by it (``--wake work-mail``) looks at
  once with its own check (a Gmail search through Setu, say) instead of
  at its next ``every``.

ONLY THE HEADERS, ONLY PEEKED. A new mail is fetched with ``BODY.PEEK``
for From, To, Subject, Date and Message-ID: nothing of what it says, and
nothing marked read. The folder is opened read-only (``EXAMINE``).

THE FIRST CONNECTION ONLY LEARNS, like a watch's first look: the folder's
next UID is remembered and nothing knocks. After a dropped connection,
mail that came meanwhile knocks when it is back (by UID, so once each);
a folder whose UIDVALIDITY changed is learned again, not replayed.

A PASSWORD, KEPT APART. IMAP needs one -- an app password, for Gmail, iCloud,
Fastmail or Outlook -- and it is not in Prahari's SQLite file but in
``mailboxes.secret.json`` beside it, readable by you alone. It is never
printed, never sent anywhere but the mail server, over TLS (plain IMAP is
refused except to this computer, for a test server).

NOT GMAIL'S OWN PUSH. Gmail's push goes through Google Cloud Pub/Sub to a
public address; that is ``renew`` and the public inlet (README). IDLE
needs neither: it is an ordinary connection out, from this computer.

Standard library only, as everywhere in Prahari.
"""

from __future__ import annotations

import email
import imaplib
import json
import os
import re
import select
import ssl
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from email.header import decode_header, make_header
from pathlib import Path

from prahari.store import Store, iso, now_utc

SECRETS = "mailboxes.secret.json"
#: RFC 2177: a client re-issues IDLE at least every 29 minutes.
IDLE_FOR = 25 * 60
#: How long connecting, signing in and one answer may take.
CONNECT_TIMEOUT = 30
#: Waits between tries after a failure, doubling up to the last.
BACKOFF = (5, 15, 60, 300)
HEADERS = ("FROM", "TO", "SUBJECT", "DATE", "MESSAGE-ID")
#: The most new mail one wake fetches, so a flood is a few knocks, not
#: thousands.
FETCH_CAP = 50

_WORD = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
_EXISTS = re.compile(rb"^\* \d+ EXISTS", re.I)


class MailboxError(ValueError):
    """A mailbox that cannot be added or opened, said in words."""


@dataclass
class Mailbox:
    #: The word it knocks on at the inlet ("work-mail").
    name: str
    owner: str
    server: str
    port: int = 993
    user: str = ""
    folder: str = "INBOX"
    tls: bool = True
    made_at: str = ""
    uidvalidity: int | None = None
    #: The highest UID already told about; None until the first connection.
    last_uid: int | None = None
    #: "new", "listening", "trouble"
    state: str = "new"
    #: The last thing that happened, in a line ("listening since 09:14").
    said: str = ""
    said_at: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def check_new(*, name: str, server: str, user: str, port: int = 993,
              folder: str = "INBOX", tls: bool = True) -> None:
    if not _WORD.match(name or ""):
        raise MailboxError(f"a mailbox's name is one short lowercase word (work-mail), "
                           f"not {name!r}: it is the word it knocks on at the inlet")
    if not server or any(c.isspace() for c in server):
        raise MailboxError("server is the mail server's name: imap.gmail.com, "
                           "imap.fastmail.com, outlook.office365.com")
    if not user:
        raise MailboxError("user is the address you sign in to the mail server with")
    if not 1 <= int(port) <= 65535:
        raise MailboxError("port is a number (993 for IMAP over TLS)")
    if not folder.strip():
        raise MailboxError("folder is a mail folder's name (INBOX)")
    if not tls and server not in ("127.0.0.1", "localhost", "::1"):
        raise MailboxError("a mailbox is opened over TLS: a password sent in plain text "
                           "to another computer is a password given away")


# -- the password, kept apart ---------------------------------------------------


def _secrets_path(state: Path) -> Path:
    return Path(state) / SECRETS


def _read_secrets(state: Path) -> dict:
    try:
        data = json.loads(_secrets_path(state).read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_secrets(state: Path, data: dict) -> None:
    path = _secrets_path(state)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as out:
        json.dump(data, out)
    os.chmod(path, 0o600)


def password_of(state: Path, box: Mailbox) -> str:
    return str(_read_secrets(state).get(f"{box.owner}/{box.name}") or "")


def keep_password(state: Path, box: Mailbox, password: str) -> None:
    data = _read_secrets(state)
    data[f"{box.owner}/{box.name}"] = password
    _write_secrets(state, data)


def forget_password(state: Path, box: Mailbox) -> None:
    data = _read_secrets(state)
    if data.pop(f"{box.owner}/{box.name}", None) is not None:
        _write_secrets(state, data)


# -- adding one -------------------------------------------------------------------


def add(store: Store, state: Path, *, name: str, owner: str, server: str, user: str,
        password: str, port: int = 993, folder: str = "INBOX", tls: bool = True,
        opener=None) -> tuple[Mailbox, str]:
    """Check it opens, then keep it. (the mailbox, what the server said)."""
    check_new(name=name, server=server, user=user, port=port, folder=folder, tls=tls)
    if not password:
        raise MailboxError("a mailbox needs its password (an app password, for most "
                           "mail services)")
    if store.mailbox(owner, name) is not None:
        raise MailboxError(f"{owner} has a mailbox {name!r} already; remove it first")
    box = Mailbox(name=name, owner=owner, server=server, port=int(port), user=user,
                  folder=folder.strip(), tls=tls, made_at=iso(now_utc()))
    try:
        conn = (opener or open_folder)(box, password)
    except MailboxError:
        raise
    except (OSError, imaplib.IMAP4.error, ssl.SSLError) as exc:
        raise MailboxError(f"could not open {folder} on {server}: {_said(exc)}") from None
    try:
        validity, next_uid = folder_marks(conn, box.folder)
    finally:
        _close(conn)
    box.uidvalidity, box.last_uid = validity, max(0, next_uid - 1)
    box.said = "opened; listening starts with prahari serve"
    box.said_at = iso(now_utc())
    store.put_mailbox(box)
    keep_password(state, box, password)
    return box, f"opened {folder} on {server} as {user}"


def remove(store: Store, state: Path, owner: str, name: str) -> Mailbox:
    box = store.mailbox(owner, name)
    if box is None:
        raise MailboxError(f"{owner} has no mailbox {name!r}")
    store.delete_mailbox(owner, name)
    forget_password(state, box)
    return box


# -- IMAP ---------------------------------------------------------------------------


def open_folder(box: Mailbox, password: str) -> imaplib.IMAP4:
    """Signed in, the folder opened read-only."""
    if box.tls:
        conn: imaplib.IMAP4 = imaplib.IMAP4_SSL(box.server, box.port,
                                                timeout=CONNECT_TIMEOUT,
                                                ssl_context=ssl.create_default_context())
    else:
        conn = imaplib.IMAP4(box.server, box.port, timeout=CONNECT_TIMEOUT)
    try:
        conn.login(box.user, password)
        kind, said = conn.select(_quoted(box.folder), readonly=True)
        if kind != "OK":
            raise MailboxError(f"no folder {box.folder!r}: {_words(said)}")
    except BaseException:
        _close(conn)
        raise
    return conn


def folder_marks(conn: imaplib.IMAP4, folder: str = "INBOX") -> tuple[int, int]:
    """(UIDVALIDITY, UIDNEXT) of the open folder: what the server said when
    it was opened, else asked for with STATUS."""
    validity = _first_int(conn.response("UIDVALIDITY")[1])
    next_uid = _first_int(conn.response("UIDNEXT")[1])
    if validity is None or next_uid is None:
        kind, said = conn.status(_quoted(folder), "(UIDVALIDITY UIDNEXT)")
        text = _words(said) if kind == "OK" else ""
        found = dict(re.findall(r"(UIDVALIDITY|UIDNEXT) (\d+)", text))
        validity = validity if validity is not None else _first_int(
            [found.get("UIDVALIDITY")])
        next_uid = next_uid if next_uid is not None else _first_int([found.get("UIDNEXT")])
    if validity is None or next_uid is None:
        raise MailboxError("the server did not say the folder's UIDVALIDITY and UIDNEXT")
    return validity, next_uid


def new_mail(conn: imaplib.IMAP4, after: int, limit: int = FETCH_CAP) -> list[dict]:
    """Headers of every mail with a UID above ``after``, oldest first."""
    kind, data = conn.uid("FETCH", f"{after + 1}:*",
                          f"(UID BODY.PEEK[HEADER.FIELDS ({' '.join(HEADERS)})])")
    if kind != "OK":
        raise MailboxError(f"the server would not list new mail: {_words(data)}")
    found = []
    for part in data or []:
        if not isinstance(part, tuple) or len(part) < 2:
            continue
        uid = _uid_of(part[0])
        if uid is None or uid <= after:
            continue          # n:* always answers with the last mail, even an old one
        message = email.message_from_bytes(part[1])
        found.append({"uid": uid, **{h.lower().replace("-", "_"): _header(message, h)
                                     for h in HEADERS}})
    found.sort(key=lambda m: m["uid"])
    return found[-limit:]


def idle(conn: imaplib.IMAP4, wait: float, stop: threading.Event) -> bool:
    """IDLE until the server says a mail came, ``wait`` runs out, or
    ``stop``. True when something came. (imaplib has no IDLE before
    Python 3.14, so it is said by hand: RFC 2177.)

    WAITED ON WITH ``select``, NEVER A READ THAT TIMES OUT: a socket file
    whose read timed out cannot be read again. A line the reader had
    already buffered before IDLE is the one thing this can miss, which is
    why the keeper also catches up after every quiet round."""
    tag = conn._new_tag()
    conn.send(tag + b" IDLE\r\n")
    first = conn.readline()
    if not first.startswith(b"+"):
        raise MailboxError(f"the server would not IDLE: {first.decode(errors='replace')}")
    came = False
    deadline = time.monotonic() + wait
    try:
        while not stop.is_set():
            left = deadline - time.monotonic()
            if left <= 0:
                break
            if not _ready(conn, min(left, 5.0)):
                continue
            line = conn.readline()
            if not line:
                raise MailboxError("the server closed the connection")
            if _EXISTS.match(line):
                came = True
                break
    finally:
        conn.send(b"DONE\r\n")
    while True:
        line = conn.readline()
        if not line:
            raise MailboxError("the server closed the connection")
        if line.startswith(tag):
            break
        if _EXISTS.match(line):
            came = True
    return came


def _ready(conn: imaplib.IMAP4, wait: float) -> bool:
    sock = conn.sock
    if isinstance(sock, ssl.SSLSocket) and sock.pending():
        return True
    readable, _, _ = select.select([sock], [], [], wait)
    return bool(readable)


# -- the keeper -----------------------------------------------------------------------


class Keeper:
    """One mailbox, kept open while ``prahari serve`` runs, on a thread.

    ``knock(word, body, owners)`` is the clock's ``hear``: each new mail is
    sent to the inlet as the mailbox's person, on the mailbox's name."""

    def __init__(self, store: Store, state: Path, box: Mailbox,
                 knock: Callable[[str, dict, set[str]], int], *, opener=None,
                 idle_for: float = IDLE_FOR, backoff: tuple = BACKOFF,
                 log: Callable[[str], None] | None = None) -> None:
        self.store = store
        self.state = state
        self.box = box
        self.knock = knock
        self.opener = opener or open_folder
        self.idle_for = idle_for
        self.backoff = backoff
        self.log = log
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True,
                                       name=f"prahari-mail-{box.name}")

    def start(self) -> None:
        self.thread.start()

    def close(self, wait: float = 10.0) -> None:
        self.stop.set()
        self.thread.join(wait)

    def run(self) -> None:
        tries = 0
        while not self.stop.is_set():
            try:
                self.once()
                tries = 0
            except (OSError, imaplib.IMAP4.error, ssl.SSLError, MailboxError) as exc:
                wait = self.backoff[min(tries, len(self.backoff) - 1)]
                tries += 1
                self._said("trouble", f"{_said(exc)}; trying again in {wait}s")
                self.stop.wait(wait)

    def once(self) -> None:
        """One connection: catch up, then IDLE until it drops or ``stop``."""
        password = password_of(self.state, self.box)
        if not password:
            raise MailboxError("no password kept for it: remove it and add it again")
        conn = self.opener(self.box, password)
        try:
            validity, next_uid = folder_marks(conn, self.box.folder)
            if self.box.last_uid is None or validity != self.box.uidvalidity:
                # The first connection, or a folder renumbered: learn, don't replay.
                self._mark(validity, max(0, next_uid - 1))
            self._catch_up(conn)
            self._said("listening", f"listening to {self.box.folder} since "
                                    f"{now_utc().astimezone():%H:%M}")
            while not self.stop.is_set():
                if not idle(conn, self.idle_for, self.stop):
                    conn.noop()           # a quiet round: still there?
                self._catch_up(conn)
        finally:
            _close(conn)

    def _catch_up(self, conn) -> None:
        mail = new_mail(conn, self.box.last_uid or 0)
        for one in mail:
            body = {"id": one["message_id"] or f"{self.box.name}:{self.box.uidvalidity}:"
                                               f"{one['uid']}",
                    "from": one["from"], "to": one["to"], "subject": one["subject"],
                    "date": one["date"], "mailbox": self.box.name}
            try:
                self.knock(self.box.name, body, {self.box.owner})
            except Exception as exc:          # the clock's trouble, not the mailbox's
                if self.log:
                    self.log(f"mailbox {self.box.name}: a knock failed: {exc}")
        if mail:
            self._mark(self.box.uidvalidity, mail[-1]["uid"])

    def _mark(self, validity: int | None, last: int) -> None:
        self.box.uidvalidity, self.box.last_uid = validity, last
        self.store.update_mailbox(self.box.owner, self.box.name, uidvalidity=validity,
                                  last_uid=last)

    def _said(self, state: str, said: str) -> None:
        self.box.state, self.box.said = state, said
        self.store.update_mailbox(self.box.owner, self.box.name, state=state, said=said,
                                  said_at=iso(now_utc()))
        if self.log:
            self.log(f"mailbox {self.box.name} ({self.box.owner}): {said}")


# -- small parts ---------------------------------------------------------------------


def _quoted(folder: str) -> str:
    return '"' + folder.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _first_int(values) -> int | None:
    for value in values or []:
        if value is None:
            continue
        text = value.decode() if isinstance(value, bytes) else str(value)
        match = re.search(r"\d+", text)
        if match:
            return int(match.group())
    return None


def _uid_of(head) -> int | None:
    text = head.decode(errors="replace") if isinstance(head, bytes) else str(head)
    match = re.search(r"UID (\d+)", text)
    return int(match.group(1)) if match else None


def _header(message, name: str) -> str:
    raw = message.get(name)
    if raw is None:
        return ""
    try:
        text = str(make_header(decode_header(raw)))
    except (ValueError, LookupError):
        text = str(raw)
    text = " ".join(text.split())
    return text if len(text) <= 300 else text[:299] + "…"


def _words(said) -> str:
    parts = [p.decode(errors="replace") if isinstance(p, bytes) else str(p)
             for p in (said or []) if p is not None]
    return " ".join(parts) or "no reason given"


def _said(exc: BaseException) -> str:
    text = " ".join(str(exc).split())
    if isinstance(exc, imaplib.IMAP4.error) and "AUTHENTICATIONFAILED" in text.upper():
        return ("the server refused the sign-in (for Gmail, iCloud and Outlook, use an "
                "app password)")
    return text or type(exc).__name__


def _close(conn) -> None:
    for step in (getattr(conn, "close", None), getattr(conn, "logout", None)):
        if step is None:
            continue
        try:
            step()
        except Exception:
            pass
