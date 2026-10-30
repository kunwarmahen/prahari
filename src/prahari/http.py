"""Prahari's page, its JSON API, and the inlet -- served by ``prahari serve``.

    GET    /api/status
    GET    /api/watches                    every watch, with its last look
    GET    /api/watches/ID
    GET    /api/looks?watch=ID&limit=N     newest first
    POST   /api/preview   {check|listen, pick, when, every, sample}
    POST   /api/watches   {name, check|listen, pick, when, every, then, ...}
    PATCH  /api/watches/ID   {check, pick, when, every, then, name, ...}
    POST   /api/watches/ID/pause | /resume | /look   (look answers 202 at once)
    DELETE /api/watches/ID
    GET    /api/inlet                      the inlet's addresses and key, for a sender
    GET    /api/mailboxes                  the mail folders kept open (no passwords)

    POST   /inlet/WORD                     something to hear (an inlet key);
                                          202 at once, with how many watches heard

A TOKEN, ALWAYS, as Samay's page has: any web page you visit can send a
request to 127.0.0.1, so every ``/api`` call carries ``Authorization:
Bearer``. The page itself is a static file and carries no data.

THE INLET HAS A KEY OF ITS OWN, AND IT CAN ONLY KNOCK. The inlet's key
goes into other people's software -- MacroDroid on a phone, a Home
Assistant automation, a tracker's webhook settings -- and a key typed
into a phone app is a key that may leak. So it is not the page's token:
with it, something can be SAID to Prahari, and nothing can be read,
made, changed or deleted. What is said is matched against the watches
listening for that word, as text from outside, and fires only what the
person already set up. The key may come as ``Authorization: Bearer``
or, for a sender that can't set headers, ``?key=``.

EACH PERSON HAS A KEY, AND A KNOCK REACHES ONLY THEIRS. The key kept in
the state folder is this computer's person's; anyone else in the house
gets one of their own (``prahari inlet --for NAME``, or their agent's
``inlet_address``). A knock is heard by the watches of the person whose
key it came with, so one person's phone saying "Mum: dinner at 8" never
fires another person's watch for "Mum".

WHAT CAN BE SENT. A JSON object is read as it is; a form is made one;
anything else is ``{"text": ...}``. 16 KB at most: an event is a line
from a notification, not a file. A Google Cloud Pub/Sub push (Gmail's
push comes this way) is unwrapped: its base64 ``data`` is read as the
event, and its message id is the event's ``id``.

A LIMIT ON KNOCKS. At most ``KNOCKS_PER_MINUTE`` a minute for one key,
then 429: a sender stuck in a loop, or a key that leaked, must not be
able to start a look every second.

THE PUBLIC ROAD IS THE INLET ALONE. ``prahari serve --inlet-port`` opens
a second listener that answers ``POST /inlet/WORD`` and nothing else --
no page, no API -- so the one address put on the internet (Tailscale
Funnel, for a webhook or Gmail's push) cannot reach anything that reads.

Standard library only, like the rest of Prahari.
"""

from __future__ import annotations

import base64
import binascii
import hmac
import json
import os
import re
import secrets
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from prahari import watches
from prahari.clock import Clock
from prahari.status import report
from prahari.store import Store

MAX_BODY = 64 * 1024
MAX_EVENT = 16 * 1024
DEFAULT_PORT = 8782
#: Knocks one key may make in a minute before it hears 429.
KNOCKS_PER_MINUTE = 60
_WORD = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")


def _kept_token(state: Path, env: str, filename: str) -> str:
    configured = os.environ.get(env, "").strip()
    if configured:
        if len(configured) < 16:
            raise ValueError(f"{env} must be at least 16 characters")
        return configured
    path = state / filename
    try:
        kept = path.read_text().strip()
        if len(kept) >= 16:
            return kept
    except OSError:
        pass
    token = secrets.token_urlsafe(24)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as out:
        out.write(token + "\n")
    return token


def serve_token(state: Path) -> str:
    """``$PRAHARI_TOKEN``, or the one kept in the state folder (made once)."""
    return _kept_token(state, "PRAHARI_TOKEN", "serve.token")


def inlet_token(state: Path) -> str:
    """``$PRAHARI_INLET_TOKEN``, or the inlet's own, kept beside the page's."""
    return _kept_token(state, "PRAHARI_INLET_TOKEN", "inlet.token")


class ApiError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


class Api:
    """What each endpoint does, apart from HTTP."""

    def __init__(self, store: Store, clock: Clock, state: Path, dvara=None,
                 inlet_url: str = "", inlet_key: str = "",
                 inlet_public: str = "") -> None:
        self.store = store
        self.clock = clock
        self.state = state
        self.dvara = dvara
        self.inlet_url = inlet_url
        self.inlet_key = inlet_key
        #: Where the inlet is reached from outside the house, when it is.
        self.inlet_public = inlet_public
        self._knocks: dict[str, deque] = {}
        self._knock_lock = threading.Lock()

    def owners_of(self, key: str) -> set[str] | None:
        """Whose watches a knock with this key reaches: this computer's
        person's for the kept key, one person's for their own, None for no
        key at all."""
        if not key:
            return None
        found = None
        if self.inlet_key and hmac.compare_digest(key.encode(), self.inlet_key.encode()):
            found = set(self.clock.home) or {watches.LOCAL_OWNER}
        for owner, theirs in self.store.inlet_keys().items():
            if hmac.compare_digest(key.encode(), theirs.encode()):
                found = {owner}
        return found

    def may_knock(self, key: str, now: float | None = None) -> bool:
        """Under the limit for this key, counting this knock."""
        now = time.monotonic() if now is None else now
        with self._knock_lock:
            seen = self._knocks.setdefault(hashlib_key(key), deque())
            while seen and now - seen[0] > 60:
                seen.popleft()
            if len(seen) >= KNOCKS_PER_MINUTE:
                return False
            seen.append(now)
            return True

    def handle(self, method: str, path: str, query: dict, body: dict) -> tuple[int, dict]:
        parts = [p for p in path.split("/") if p][1:]
        try:
            return self._route(method, parts, query, body)
        except watches.WatchError as exc:
            message = str(exc)
            raise ApiError(404 if message.startswith("no watch") else 400, message) from None

    def _route(self, method, parts, query, body) -> tuple[int, dict]:
        if parts == ["status"] and method == "GET":
            return 200, report(self.state, self.store)
        if parts == ["inlet"] and method == "GET":
            return 200, {"url": self.inlet_url, "public_url": self.inlet_public or None,
                         "key": self.inlet_key,
                         "words": sorted({w.listen or w.wake for w in self.store.watches()
                                          if w.listen or w.wake}),
                         "people": sorted(self.store.inlet_keys())}
        if parts == ["mailboxes"] and method == "GET":
            return 200, {"mailboxes": [b.as_dict() for b in self.store.mailboxes()]}
        if parts == ["preview"] and method == "POST":
            return 200, watches.preview(
                self.clock.caller, check=body.get("check"), listen=str(body.get("listen")
                                                                        or ""),
                pick=body.get("pick"), when=body.get("when"),
                every=str(body.get("every") or ""), sample=body.get("sample"),
                agent=str(body.get("agent") or ""), wake=str(body.get("wake") or ""),
                renew=body.get("renew"), thing=str(body.get("thing") or ""))
        if parts == ["looks"] and method == "GET":
            limit = _int(query.get("limit", ["50"])[0], "limit")
            watch_id = query.get("watch", [None])[0]
            if watch_id:
                watch_id = watches.find(self.store, watch_id).id
            looks = self.store.looks(watch_id, limit=min(limit, 500))
            return 200, {"looks": [look.as_dict() for look in looks]}
        if parts == ["watches"]:
            if method == "GET":
                return 200, {"watches": [watches.card(w, self.store)
                                         for w in self.store.watches()]}
            if method == "POST":
                return 201, watches.card(self._create(body), self.store)
        if len(parts) >= 2 and parts[0] == "watches":
            watch = watches.find(self.store, parts[1])
            action = parts[2] if len(parts) == 3 else None
            if len(parts) == 2 and method == "GET":
                return 200, watches.card(watch, self.store)
            if len(parts) == 2 and method == "DELETE":
                watches.remove(self.store, watch.id)
                return 200, {"removed": watch.id}
            if len(parts) == 2 and method == "PATCH":
                return 200, watches.card(watches.update(self.store, watch.id, **body),
                                         self.store)
            if method == "POST" and action == "pause":
                return 200, watches.card(watches.pause(self.store, watch.id), self.store)
            if method == "POST" and action == "resume":
                return 200, watches.card(watches.resume(self.store, watch.id), self.store)
            if method == "POST" and action == "look":
                try:
                    self.clock.start_now(watch.id)
                except RuntimeError as exc:
                    raise ApiError(409, str(exc)) from None
                return 202, {"looking": watch.id}
        raise ApiError(404, f"no such endpoint: {method} /api/{'/'.join(parts)}")

    def _create(self, body: dict):
        allow = body.get("allow_tools") or []
        if isinstance(allow, str):
            allow = [g.strip() for g in allow.split(",") if g.strip()]
        runner = str(body.get("runner") or "direct")
        return watches.create(
            self.store, name=str(body.get("name") or ""), check=body.get("check"),
            listen=str(body.get("listen") or ""), pick=body.get("pick"),
            when=body.get("when"), every=str(body.get("every") or ""),
            wake=str(body.get("wake") or ""), renew=body.get("renew"),
            then=str(body.get("then") or ""), asked=str(body.get("asked") or ""),
            thing=str(body.get("thing") or ""), owner=str(body.get("as")
                                                        or watches.LOCAL_OWNER),
            runner=runner, agent=str(body.get("agent") or ""), allow_tools=allow,
            max_per_day=_int(body.get("max_per_day") or watches.DEFAULT_MAX_PER_DAY,
                             "max_per_day"),
            created_via="page", dvara=self.dvara if runner == "dvara" else None)

    def event(self, word: str, raw: bytes, kind: str,
              owners: set[str] | None = None) -> tuple[int, dict]:
        """Something sent to the inlet, for ``owners``' watches."""
        if not _WORD.match(word):
            raise ApiError(404, "the inlet's address ends in one lowercase word, "
                                "like /inlet/whatsapp")
        heard = self.clock.hear(word, _event_body(raw, kind), owners)
        return 202, {"heard_by": heard}


def hashlib_key(key: str) -> str:
    """A key as the limit counts it: never kept as itself."""
    import hashlib
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _event_body(raw: bytes, kind: str) -> dict:
    text = raw.decode("utf-8", errors="replace")
    if "json" in kind or text.lstrip().startswith("{"):
        try:
            data = json.loads(text or "{}")
        except json.JSONDecodeError:
            return {"text": text}
        if not isinstance(data, dict):
            return {"text": text}
        return _unwrapped(data)
    if "form" in kind:
        return {k: v[-1] for k, v in parse_qs(text).items()}
    return {"text": text}


def _unwrapped(data: dict) -> dict:
    """A Pub/Sub push's envelope taken off: ``message.data`` (base64) is
    the event, ``message.messageId`` its id. Anything else, as it came."""
    message = data.get("message")
    if not (isinstance(message, dict) and "subscription" in data
            and isinstance(message.get("data"), str)):
        return data
    try:
        inner = base64.b64decode(message["data"], validate=False).decode("utf-8", "replace")
    except (binascii.Error, ValueError):
        return data
    try:
        event = json.loads(inner)
    except json.JSONDecodeError:
        event = None
    event = event if isinstance(event, dict) else {"text": inner}
    if message.get("messageId") and "id" not in event:
        event["id"] = str(message["messageId"])
    return event


def _int(value, name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ApiError(400, f"{name} must be a whole number") from None


def public_address(raw: str | None, env: str = "PRAHARI_PUBLIC_URL") -> str | None:
    raw = (raw if raw is not None else os.environ.get(env, "")).strip()
    if not raw:
        return None
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(f"the page's public address must look like http://host:port/ "
                         f"-- got {raw!r}")
    return raw.rstrip("/") + "/"


def public_inlet() -> str:
    """Where the internet reaches the inlet (``$PRAHARI_INLET_PUBLIC_URL``),
    ending in /, or ""."""
    raw = os.environ.get("PRAHARI_INLET_PUBLIC_URL", "").strip()
    return raw.rstrip("/") + "/" if raw else ""


def page() -> bytes:
    return files("prahari").joinpath("static/index.html").read_bytes()


def favicon() -> bytes:
    return files("prahari").joinpath("static/favicon.svg").read_bytes()


class PrahariServer:
    """The API, the page and the inlet, on a thread beside the watch --
    or, ``inlet_only``, the inlet and nothing else (the public road)."""

    def __init__(self, api: Api, token: str, inlet_key: str, *, host: str = "127.0.0.1",
                 port: int = DEFAULT_PORT, public_url: str | None = None,
                 inlet_only: bool = False) -> None:
        self.api = api
        self.token = token
        self.inlet_key = inlet_key
        self.inlet_only = inlet_only
        self.public_url = (public_address(public_url, "PRAHARI_INLET_PUBLIC_URL")
                           if inlet_only else public_address(public_url))
        self.httpd = ThreadingHTTPServer((host, port), _handler(self))
        self.httpd.daemon_threads = True
        self._thread: threading.Thread | None = None
        if inlet_only:
            api.inlet_public = self.url + "inlet/" if self.public_url else ""
        else:
            api.inlet_url = self.url + "inlet/"
            api.inlet_key = inlet_key

    @property
    def url(self) -> str:
        if self.public_url:
            return self.public_url
        host, port = self.httpd.server_address[:2]
        if host in ("0.0.0.0", "::"):
            host = "127.0.0.1"
        return f"http://{host}:{port}/"

    @property
    def page_url(self) -> str:
        return f"{self.url}#token={self.token}"

    def start(self) -> None:
        self._thread = threading.Thread(target=self.httpd.serve_forever,
                                        name="prahari-http", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        if self._thread is not None:
            self._thread.join()


def _handler(server: PrahariServer):
    class Handler(BaseHTTPRequestHandler):
        server_version = "prahari"

        def log_message(self, *args):
            pass

        def _send(self, status: int, body: bytes, kind: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, data: dict) -> None:
            self._send(status, json.dumps(data).encode(), "application/json")

        def _bearer(self) -> str:
            offered = self.headers.get("Authorization", "")
            return offered[7:].strip() if offered.startswith("Bearer ") else ""

        def _same(self, offered: str, want: str) -> bool:
            return bool(offered) and hmac.compare_digest(offered.encode(), want.encode())

        def _dispatch(self, method: str) -> None:
            url = urlparse(self.path)
            if server.inlet_only:
                if url.path.startswith("/inlet/"):
                    return self._inlet(method, url)
                return self._json(404, {"detail": "not found"})
            if method == "GET" and url.path in ("/", "/index.html"):
                return self._send(200, page(), "text/html; charset=utf-8")
            if method == "GET" and url.path == "/favicon.svg":
                return self._send(200, favicon(), "image/svg+xml")
            if url.path.startswith("/inlet/"):
                return self._inlet(method, url)
            if not url.path.startswith("/api/"):
                return self._json(404, {"detail": "not found"})
            if not self._same(self._bearer(), server.token):
                return self._json(401, {"detail": "missing or wrong token"})
            body: dict = {}
            if method in ("POST", "PATCH"):
                size = int(self.headers.get("Content-Length") or 0)
                if size > MAX_BODY:
                    return self._json(413, {"detail": "request too large"})
                raw = self.rfile.read(size) if size else b""
                try:
                    body = json.loads(raw or b"{}")
                except json.JSONDecodeError:
                    return self._json(400, {"detail": "the body is not JSON"})
                if not isinstance(body, dict):
                    return self._json(400, {"detail": "the body is a JSON object"})
            try:
                status, data = server.api.handle(method, url.path, parse_qs(url.query),
                                                 body)
            except ApiError as exc:
                return self._json(exc.status, {"detail": exc.detail})
            except Exception as exc:
                return self._json(500, {"detail": f"{type(exc).__name__}: {exc}"})
            self._json(status, data)

        def _inlet(self, method: str, url) -> None:
            if method != "POST":
                return self._json(405, {"detail": "the inlet hears POST only"})
            key = self._bearer() or (parse_qs(url.query).get("key") or [""])[0]
            owners = server.api.owners_of(key)
            if owners is None:
                return self._json(401, {"detail": "missing or wrong inlet key"})
            if not server.api.may_knock(key):
                return self._json(429, {"detail": f"too many knocks: "
                                                  f"{KNOCKS_PER_MINUTE} a minute at most"})
            size = int(self.headers.get("Content-Length") or 0)
            if size > MAX_EVENT:
                return self._json(413, {"detail": "an event is 16 KB at most"})
            raw = self.rfile.read(size) if size else b""
            word = url.path[len("/inlet/"):].strip("/")
            try:
                status, data = server.api.event(
                    word, raw, self.headers.get("Content-Type", "").lower(), owners)
            except ApiError as exc:
                return self._json(exc.status, {"detail": exc.detail})
            except Exception as exc:
                return self._json(500, {"detail": f"{type(exc).__name__}: {exc}"})
            self._json(status, data)

        def do_GET(self):
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")

        def do_PATCH(self):
            self._dispatch("PATCH")

        def do_DELETE(self):
            self._dispatch("DELETE")

    return Handler
