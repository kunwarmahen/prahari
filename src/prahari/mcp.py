"""The tools an agent uses to offer "I'll tell you when that happens".

    prahari mcp --for mahen [--agent DIR|NAME] [--runner direct|dvara]

An MCP server on stdin/stdout -- newline-delimited JSON-RPC, by hand,
like Samay's -- with nine tools:

    preview_watch     read    try a recipe once; what it sees, in words
    list_watches      read    this person's watches
    watch_looks       read    what one of them saw lately
    create_watch      write   save one
    update_watch      write   mend one: its check, pick, test, how often, then
    pause_watch       write
    resume_watch      write
    allow_for_watch   write   let its then-turn use a tool without asking
    delete_watch      write

THE AGENT WRITES THE RECIPE; THE PERSON ACCEPTS IT. The three reads say
``readOnlyHint: true`` and the rest do not, so a harness that honours the
hint (Yantra does) puts every create and change in front of the person.
``preview_watch`` comes first: it LOOKS ONCE, with a tool that only
reads (nothing is granted before the yes), and answers with the start of
what the tool said, what the pick found in it, and the sentence the
person will be asked to accept. A model whose pick finds nothing sees
why, and writes a better one, before anybody is asked anything.

A BROKEN WATCH IS MENDED, NOT REMADE. When a site moves its price, the
watch pauses and says so; the agent previews a new pick against today's
page and calls ``update_watch``. The watch keeps its id, its history and
its person.

ONE PERSON PER SERVER. ``--for`` is the harness's; every tool sees and
changes only that person's watches, and the model has no argument with
which to name anyone else. ``--agent`` and ``--runner`` are the
harness's too: a watch made while talking to your mail agent looks with,
and wakes, your mail agent.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, TextIO

from prahari import __version__, watches
from prahari.status import serving
from prahari.store import Store

VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")

_CHECK = {"type": "object", "description": (
    "One call of a tool you have that READS, exactly as you would call it: "
    '{"tool": "mcp__gmail__search_threads", "args": {"account": "personal", '
    '"query": "from:bank@example.com newer_than:1d"}}. Use the exact tool name. '
    "Prahari repeats this call with no model; put everything that narrows it "
    "(the sender, the address) in the args.")}
_PICK = {"type": "object", "description": (
    'What to take out of the tool\'s answer, ONE of: {"number": ""} the first '
    'number, or {"number": "\\\\$([\\\\d.,]+)"} the one a pattern finds (group 1); '
    '{"text": "REGEX"}; {"json": "a.b[0].c"}; {"items": "thread (\\\\w+)"} every '
    'match an item, group 1 its key; {"items_json": "messages[*]", "key": "id"}; '
    "{} the whole answer. Call preview_watch to see the answer you are picking from.")}
_WHEN = {"type": "object", "description": (
    'When it matters, ONE of: {"below": 50} {"above": 50} {"at_most": N} '
    '{"at_least": N} (numbers; fires when it becomes true, once until it is false '
    'again); {"contains": "text"} {"lacks": "text"} {"equals": X} {"matches": '
    '"REGEX"}; {"changed": true}; {"new": true} (items not seen before); {"any": '
    'true}; {"ask": "a yes/no question"} (a model is asked only about what changed '
    "or is new).")}
_EVERY = {"type": "string", "description": (
    'How often to look: "30m", "3h", "1d" (5 minutes at the least, 7 days at '
    "most). Match how fast the thing changes: mail 15m-1h, a price 1h-6h, a page "
    "a day.")}

TOOLS: list[dict] = [
    {"name": "preview_watch",
     "description": (
         "Try a watch ONCE before making it: looks with the check (only a tool that "
         "reads can be tried before the person agrees), applies the pick, and says "
         "what it sees now, with the start of the tool's answer so you can fix the "
         "pick. Call this first, then tell the person the sentence and what it sees; "
         "create the watch only if they say yes. For a watch that listens at the "
         "inlet, give a sample event instead of a check."),
     "inputSchema": {"type": "object", "properties": {
         "check": _CHECK, "pick": _PICK, "when": _WHEN, "every": _EVERY,
         "listen": {"type": "string", "description": "for an inlet watch instead "
                    "of a check: the one word a sender posts to (whatsapp)"},
         "sample": {"type": "object", "description": "an event like the sender's, "
                    "to try an inlet watch on"}}},
     "annotations": {"readOnlyHint": True}},
    {"name": "list_watches",
     "description": "The person's watches: what each looks at, when it tells them, "
                    "and how its last look went.",
     "inputSchema": {"type": "object", "properties": {}},
     "annotations": {"readOnlyHint": True}},
    {"name": "watch_looks",
     "description": "What one watch saw on its recent looks, newest first.",
     "inputSchema": {"type": "object", "properties": {
         "id": {"type": "string"},
         "limit": {"type": "integer", "minimum": 1, "maximum": 50}},
         "required": ["id"]},
     "annotations": {"readOnlyHint": True}},
    {"name": "create_watch",
     "description": (
         "Save a watch, after the person agreed to what preview_watch said. "
         "`then`: what you are asked when it fires, with NOBODY watching -- a complete "
         "instruction to yourself; leave it out to just tell the person what was "
         "seen (no model is used at all then). allow_tools: tools that `then` needs "
         "to run without asking; anything that changes something fixed to its "
         "arguments, as tool(key=value)."),
     "inputSchema": {"type": "object", "properties": {
         "name": {"type": "string", "description": "a few words the person will "
                  "know it by: \"ALAB under $50\""},
         "check": _CHECK, "pick": _PICK, "when": _WHEN, "every": _EVERY,
         "listen": {"type": "string"},
         "then": {"type": "string"},
         "allow_tools": {"type": "array", "items": {"type": "string"}},
         "max_per_day": {"type": "integer", "minimum": 1, "maximum": 200,
                         "description": "the most times it may fire in a day "
                         "(default 10)"}},
         "required": ["name", "when"]},
     "annotations": {"readOnlyHint": False, "destructiveHint": False}},
    {"name": "update_watch",
     "description": (
         "Mend one of the person's watches -- most often after it paused because its "
         "pick found nothing (a site changed): preview a new pick first. Changing the "
         "check, pick, when or every starts its memory over (the next look learns)."),
     "inputSchema": {"type": "object", "properties": {
         "id": {"type": "string"}, "name": {"type": "string"},
         "check": _CHECK, "pick": _PICK, "when": _WHEN, "every": _EVERY,
         "then": {"type": "string"},
         "max_per_day": {"type": "integer", "minimum": 1, "maximum": 200}},
         "required": ["id"]},
     "annotations": {"readOnlyHint": False, "destructiveHint": False}},
    {"name": "pause_watch",
     "description": "Stop a watch looking, keeping it to resume later.",
     "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}},
                     "required": ["id"]},
     "annotations": {"readOnlyHint": False, "destructiveHint": False}},
    {"name": "resume_watch",
     "description": "Start a paused watch again; it looks soon.",
     "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}},
                     "required": ["id"]},
     "annotations": {"readOnlyHint": False, "destructiveHint": False}},
    {"name": "allow_for_watch",
     "description": "Let a watch's then-turn use more tools without asking, from its "
                    "next fire -- when one was refused and the person says to allow it.",
     "inputSchema": {"type": "object", "properties": {
         "id": {"type": "string"},
         "allow_tools": {"type": "array", "items": {"type": "string"}}},
         "required": ["id", "allow_tools"]},
     "annotations": {"readOnlyHint": False, "destructiveHint": False}},
    {"name": "delete_watch",
     "description": "Remove a watch, its looks and what it remembered, for good.",
     "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}},
                     "required": ["id"]},
     "annotations": {"readOnlyHint": False, "destructiveHint": True}},
]


class ToolFailed(Exception):
    """A call the model can read about and fix."""


class Tools:
    def __init__(self, store: Store, state: Path, caller, *, person: str,
                 agent: str = "", runner: str | None = None, dvara=None) -> None:
        self.store = store
        self.state = state
        self.caller = caller
        self.person = person
        self.agent = agent
        self.dvara = dvara
        if runner is None:
            runner = ("dvara" if dvara is not None and person != watches.LOCAL_OWNER
                      else "direct")
        self.runner = runner

    def call(self, name: str, args: dict) -> str:
        handler: Callable[[dict], str] | None = getattr(self, f"_{name}", None)
        if handler is None or name not in {t["name"] for t in TOOLS}:
            raise ToolFailed(f"no tool {name!r}")
        try:
            return handler(args)
        except watches.WatchError as exc:
            raise ToolFailed(str(exc)) from None

    def _preview_watch(self, args: dict) -> str:
        said = watches.preview(self.caller, check=args.get("check"),
                               listen=str(args.get("listen") or ""),
                               pick=args.get("pick"), when=args.get("when"),
                               every=str(args.get("every") or ""),
                               sample=args.get("sample"),
                               agent=self.agent if self.runner == "direct" else "")
        lines = [f"The watch, in words: {said['sentence']}.", said.get("said", "")]
        if said.get("items"):
            lines += ["Items it sees now (first few):", *[f"  {i}" for i in said["items"]]]
        if said.get("result") and not said.get("found", True):
            lines += ["The tool's answer it picked from:", said["result"]]
        return "\n".join(line for line in lines if line)

    def _list_watches(self, args: dict) -> str:
        mine = self.store.watches(owner=self.person)
        if not mine:
            return "No watches yet."
        lines = []
        for watch in mine:
            card = watches.card(watch, self.store)
            last = card["last_look"]
            lines.append(
                f"{watch.id} [{watch.state}] {watch.name}: {card['sentence']}. "
                f"{card['does']}.\n"
                + (f"  paused: {watch.paused_because}\n" if watch.paused_because else "")
                + (f"  last look: {last['outcome']} {last['value']}".rstrip()
                   if last else "  not looked yet"))
        return "\n".join(lines)

    def _watch_looks(self, args: dict) -> str:
        watch = self._mine(args)
        limit = max(1, min(int(args.get("limit") or 5), 50))
        looks = self.store.looks(watch.id, limit=limit)
        if not looks:
            return f"{watch.id} has not looked yet."
        return "\n".join(
            f"{look.started_at} {look.outcome}"
            + (f" {look.value}" if look.value else "")
            + (f" -- {look.detail}" if look.detail else "")
            + (f"\n  found: {'; '.join(look.found[:3])}" if look.found else "")
            for look in looks)

    def _create_watch(self, args: dict) -> str:
        allow = args.get("allow_tools") or []
        if not isinstance(allow, list):
            raise ToolFailed("allow_tools is a list of tool names")
        made = watches.create(
            self.store, name=str(args.get("name") or ""), check=args.get("check"),
            listen=str(args.get("listen") or ""), pick=args.get("pick"),
            when=args.get("when"), every=str(args.get("every") or ""),
            then=str(args.get("then") or ""), owner=self.person, runner=self.runner,
            agent=self.agent, allow_tools=[str(g) for g in allow],
            max_per_day=int(args.get("max_per_day") or watches.DEFAULT_MAX_PER_DAY),
            created_via="agent", dvara=self.dvara if self.runner == "dvara" else None)
        said = f"Saved {made.id}: {made.name} -- {watches.sentence(made)}."
        if serving(self.state) is None:
            said += (" Note: Prahari is not running on this machine, so it will not "
                     "look until `prahari serve` is started -- tell the person.")
        return said

    def _update_watch(self, args: dict) -> str:
        changes = {k: args[k] for k in ("name", "check", "pick", "when", "every", "then",
                                        "max_per_day") if k in args}
        watch = watches.update(self.store, self._mine(args).id, owner=self.person,
                               **changes)
        return f"Updated {watch.id}: {watch.name} -- {watches.sentence(watch)}."

    def _pause_watch(self, args: dict) -> str:
        return f"Paused {watches.pause(self.store, self._mine(args).id).id}."

    def _resume_watch(self, args: dict) -> str:
        watch = watches.resume(self.store, self._mine(args).id)
        return f"Resumed {watch.id}: {watches.sentence(watch)}."

    def _allow_for_watch(self, args: dict) -> str:
        allow = args.get("allow_tools") or []
        if not isinstance(allow, list):
            raise ToolFailed("allow_tools is a list of tool names")
        watch = watches.allow(self.store, self._mine(args).id, [str(g) for g in allow])
        return f"{watch.id} may now use without asking: {', '.join(watch.allow_tools)}."

    def _delete_watch(self, args: dict) -> str:
        watch = watches.remove(self.store, self._mine(args).id)
        return f"Deleted {watch.id} ({watch.name})."

    def _mine(self, args: dict):
        wanted = str(args.get("id") or "").strip()
        if not wanted:
            raise ToolFailed("missing: id")
        return watches.find(self.store, wanted, owner=self.person)


def answer(tools: Tools, message: dict) -> dict | None:
    method, ident = message.get("method"), message.get("id")
    if ident is None:
        return None
    if method == "initialize":
        asked = (message.get("params") or {}).get("protocolVersion")
        return _ok(ident, {
            "protocolVersion": asked if asked in VERSIONS else VERSIONS[0],
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "prahari", "version": __version__},
            "instructions": ("Watches for this person: preview first, say what it "
                             "sees and the sentence, create only after they agree.")})
    if method == "ping":
        return _ok(ident, {})
    if method == "tools/list":
        return _ok(ident, {"tools": TOOLS})
    if method == "tools/call":
        params = message.get("params") or {}
        try:
            text = tools.call(str(params.get("name")), params.get("arguments") or {})
            return _ok(ident, {"content": [{"type": "text", "text": text}],
                               "isError": False})
        except ToolFailed as exc:
            return _ok(ident, {"content": [{"type": "text", "text": str(exc)}],
                               "isError": True})
    return {"jsonrpc": "2.0", "id": ident,
            "error": {"code": -32601, "message": f"no method {method!r}"}}


def _ok(ident: Any, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": ident, "result": result}


def serve(tools: Tools, stdin: TextIO = sys.stdin, stdout: TextIO = sys.stdout) -> None:
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            reply = {"jsonrpc": "2.0", "id": None,
                     "error": {"code": -32700, "message": "not JSON"}}
        else:
            reply = answer(tools, message) if isinstance(message, dict) else None
        if reply is not None:
            stdout.write(json.dumps(reply) + "\n")
            stdout.flush()
