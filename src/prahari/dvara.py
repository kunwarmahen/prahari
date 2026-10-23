"""The Dvara road: telling the person, and a then-turn run AS the person.

A watch that fires has news for somebody, and the channels people are
reached on -- Telegram, Dvara's web chat, Sarathi's home page -- live in
Dvara. So, as for Samay:

* ``POST /notify`` puts a message on the person's channels. Prahari
  decides WHETHER to tell; Dvara only sends;
* ``POST /message`` runs the then-turn as that person, unattended:
  their daily allowance pays, the owner's rules apply, and a question
  that can reach them still does, with two buttons. The turn is named
  as Prahari's (``came_by``), so Dvara's page labels it;
* ``POST /call`` makes the LOOK as that person: one tool, no model, their
  agent built with their own Setu folder (Dvara's notes/56). A watch made
  by somebody else in the house reads their mail, never the owner's --
  which is what lets Dvara offer watches to everyone.

A FRESH CONVERSATION EVERY FIRE. Each then-turn is its own thread,
``prahari-<watch>-<time>``: what the watch found is in the prompt, and a
watch that has fired forty times does not drag forty answers along.

STANDARD LIBRARY ONLY, as everywhere in Prahari.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from prahari.looking import CALL_FORMAT, LOOK_LIMIT, Called, TurnResult, grant_for
from prahari.store import Watch

#: How long a call that is not a turn may take.
QUICK = 30.0


class DvaraError(RuntimeError):
    """Dvara could not be reached, or said no -- in Dvara's own words."""


@dataclass(frozen=True)
class Dvara:
    url: str
    token: str
    #: Who a watch made here ("local") is for.
    actor: str = ""

    @classmethod
    def from_env(cls) -> Dvara | None:
        """``$PRAHARI_DVARA_URL``, ``$PRAHARI_DVARA_TOKEN`` (Dvara's own
        ``$DVARA_TOKEN``) and ``$PRAHARI_DVARA_ACTOR``; None with no URL."""
        url = os.environ.get("PRAHARI_DVARA_URL", "").strip().rstrip("/")
        if not url:
            return None
        token = os.environ.get("PRAHARI_DVARA_TOKEN", "").strip()
        if not token:
            raise DvaraError("PRAHARI_DVARA_URL is set but PRAHARI_DVARA_TOKEN is "
                             "not: Dvara refuses a caller without its token")
        return cls(url=url, token=token,
                   actor=os.environ.get("PRAHARI_DVARA_ACTOR", "").strip())

    def actor_for(self, watch: Watch) -> str:
        if watch.owner and watch.owner != "local":
            return watch.owner
        return self.actor

    def call(self, method: str, path: str, body: dict | None = None,
             timeout: float = QUICK) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            self.url + path, data=data, method=method,
            headers={"Authorization": f"Bearer {self.token}",
                     "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as exc:
            try:
                said = json.loads(exc.read() or b"{}").get("detail")
            except (json.JSONDecodeError, AttributeError):
                said = None
            raise DvaraError(f"dvara said {exc.code}: {said or exc.reason}") from None
        except TimeoutError:
            raise
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise TimeoutError(str(exc.reason)) from None
            raise DvaraError(f"cannot reach dvara at {self.url}: {exc.reason}") from None

    def agents(self) -> list[str]:
        return list(self.call("GET", "/agents").get("agents") or [])

    def notify(self, actor: str, text: str) -> dict:
        return self.call("POST", "/notify", {"actor": actor, "text": text})


class DvaraCaller:
    """A look through Dvara, as the watch's person, with their accounts."""

    def __init__(self, dvara: Dvara, limit: int = LOOK_LIMIT) -> None:
        self.dvara = dvara
        self.limit = limit

    def call(self, watch: Watch, *, granted: bool = True) -> Called:
        actor = self.dvara.actor_for(watch)
        if not actor or not watch.agent:
            return Called(ok=False, detail=(
                "a look through Dvara names its person and its agent; this watch has "
                + ("no agent" if actor else "nobody")))
        tool, args = str(watch.check.get("tool") or ""), watch.check.get("args") or {}
        grant = grant_for(tool, args) if granted else None
        body = {"actor": actor, "agent": watch.agent, "tool": tool, "args": args,
                "allow_tools": [grant] if grant else []}
        try:
            data = self.dvara.call("POST", "/call", body, timeout=self.limit)
        except TimeoutError:
            return Called(ok=False, detail=f"the look took longer than {self.limit}s")
        except DvaraError as exc:
            return Called(ok=False, detail=str(exc))
        if data.get("format") != CALL_FORMAT:
            return Called(ok=False, detail=(
                f"dvara answered in a format this Prahari does not know "
                f"({data.get('format')!r}; want {CALL_FORMAT}): it may be older than "
                "POST /call"))
        return Called(ok=bool(data.get("ok")), text=str(data.get("text") or ""),
                      detail=str(data.get("detail") or ""),
                      needs=[str(n) for n in data.get("needs_person") or []],
                      busy=[str(b) for b in data.get("busy") or []])


class DvaraRunner:
    """A then-turn through Dvara, as the watch's person."""

    def __init__(self, dvara: Dvara) -> None:
        self.dvara = dvara

    def run(self, watch: Watch, prompt: str) -> TurnResult:
        actor = self.dvara.actor_for(watch)
        if not actor:
            return TurnResult(ok=False, stop_reason="error", detail=(
                "this watch names nobody Dvara knows: add it with --as ACTOR, or "
                "set PRAHARI_DVARA_ACTOR"))
        body = {"actor": actor, "agent": watch.agent,
                "thread": f"prahari-{watch.id}-{int(time.time())}",
                "text": prompt, "unattended": True, "came_by": "prahari",
                "allow_tools": list(watch.allow_tools), "wait": watch.wait * 60}
        try:
            reply = self.dvara.call("POST", "/message", body, timeout=watch.time_limit
                                    + watch.wait * 60)
        except TimeoutError:
            return TurnResult(ok=False, timed_out=True, stop_reason="timed_out", detail=(
                "no answer from dvara in time; the turn may still finish there "
                "(dvara runs)"))
        except DvaraError as exc:
            return TurnResult(ok=False, stop_reason="error", detail=str(exc))
        return TurnResult(
            ok=bool(reply.get("ok")), text=str(reply.get("text") or ""),
            stop_reason=str(reply.get("stop_reason") or ""),
            detail=str(reply.get("detail") or ""),
            cost_usd=float(reply.get("cost_usd") or 0.0),
            needs=[str(n) for n in reply.get("needs_person") or []],
            refused=[str(r) for r in reply.get("refused") or []],
            held=bool(reply.get("held")), dvara_run_id=str(reply.get("run_id") or ""))


class DvaraNotifier:
    """Tell a watch's person something, on their own channels."""

    def __init__(self, dvara: Dvara) -> None:
        self.dvara = dvara

    def send(self, watch: Watch, text: str) -> bool:
        actor = self.dvara.actor_for(watch)
        if not actor:
            return False
        try:
            sent = self.dvara.notify(actor, text)
        except (DvaraError, TimeoutError):
            return False
        return bool(sent.get("sent") or sent.get("kept"))
