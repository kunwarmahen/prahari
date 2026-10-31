"""The tools an agent uses to offer "I'll tell you when that happens".

    prahari mcp --for mahen [--agent DIR|NAME] [--runner direct|dvara]

An MCP server on stdin/stdout -- newline-delimited JSON-RPC, by hand,
like Samay's -- with ten tools:

    preview_watch     read    try a recipe once; what it sees, in words
    list_watches      read    this person's watches
    watch_looks       read    what one of them saw lately
    inlet_address     read    where this person's phone or webhook sends, and
                              their own key
    create_watch      write   save one
    update_watch      write   mend one: its check, pick, test, how often, then
    pause_watch       write
    resume_watch      write
    allow_for_watch   write   let its then-turn use a tool without asking
    delete_watch      write

THE AGENT WRITES THE RECIPE; THE PERSON ACCEPTS IT. The four reads say
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
_WAKE = {"type": "string", "description": (
    "For mail pushed to Prahari: the word at the inlet that makes this watch look AT "
    "ONCE, as well as every `every` -- a mailbox's name (the person keeps one with "
    "`prahari mailbox add`), or the word Gmail's push knocks on. Leave out otherwise.")}
_RENEW = {"type": "object", "description": (
    "With wake, for Gmail's push: the call that keeps Gmail knocking, made now and "
    'once a day: {"tool": "mcp__gmail__watch_mailbox", "args": {"account": '
    '"personal", "topic": "projects/<project>/topics/<name>"}}. Only when the person '
    "has set up that topic.")}

_STARTS = {"type": "string", "description": (
    "When it starts looking, if not now: ISO 8601 with the person's offset "
    "(\"2026-10-31T07:00-04:00\"). \"Keep an eye on my flight tomorrow\" starts "
    "tomorrow morning.")}
_ENDS = {"type": "string", "description": (
    "When it ends by itself, if the thing has a day after which it no longer "
    "matters: ISO 8601 with the person's offset. A fare for Saturday's flight ends "
    "after Saturday. It stops looking and tells the person; nobody is asked.")}
_STOP = {"type": "object", "description": (
    "Ends it once what it sees passes this test, same form as when: "
    "{\"contains\": \"Landed\"} for a flight's status. Leave out otherwise.")}
_ASKED = {"type": "string", "description": (
    "The person's own message that asked for this watch, COPIED WORD FOR WORD, "
    "never reworded or tidied (\"tell me if it goes under 200 thousand dollars\" "
    "stays exactly that -- not \"notify me when Bitcoin falls below $200,000\"). "
    "The message where they asked, not their yes. Shown first wherever the watch "
    "is, and in every message it sends, as \"You asked: ...\" -- so words they "
    "never said read as a lie.")}
_THING = {"type": "string", "description": (
    "What the pick takes, in a few words: \"the fare\", \"the temperature\", "
    "\"BTC's price\". Messages say \"the fare is now 58\" instead of \"the "
    "number\".")}

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
         "check": _CHECK, "pick": _PICK, "when": _WHEN, "every": _EVERY, "thing": _THING,
         "asked": _ASKED, "starts": _STARTS, "ends": _ENDS, "stop": _STOP,
         "listen": {"type": "string", "description": "for an inlet watch instead "
                    "of a check: the one word a sender posts to (whatsapp)"},
         "wake": _WAKE,
         "sample": {"type": "object", "description": "an event like the sender's, "
                    "to try an inlet watch on"}}},
     "annotations": {"readOnlyHint": True}},
    {"name": "list_watches",
     "description": "The person's watches: what each looks at, when it tells them, "
                    "and how its last look went.",
     "inputSchema": {"type": "object", "properties": {}},
     "annotations": {"readOnlyHint": True}},
    {"name": "inlet_address",
     "description": (
         "Where something that can tell Prahari itself -- the person's Android phone "
         "(MacroDroid, Tasker), Home Assistant, a webhook -- sends, with THIS person's "
         "own key: knocks with it reach only their watches. Give it to the person to "
         "put in that app; the key can only knock, never read."),
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
                  "know it by -- what is watched and the line: \"ALAB under $50\", "
                  "never the tool's name"},
         "asked": _ASKED, "thing": _THING,
         "starts": _STARTS, "ends": _ENDS, "stop": _STOP,
         "check": _CHECK, "pick": _PICK, "when": _WHEN, "every": _EVERY,
         "listen": {"type": "string"},
         "wake": _WAKE, "renew": _RENEW,
         "then": {"type": "string"},
         "allow_tools": {"type": "array", "items": {"type": "string"}},
         "max_per_day": {"type": "integer", "minimum": 1, "maximum": 200,
                         "description": "the most times it may fire in a day "
                         "(default 10)"}},
         "required": ["name", "asked", "when"]},
     "annotations": {"readOnlyHint": False, "destructiveHint": False}},
    {"name": "update_watch",
     "description": (
         "Mend one of the person's watches -- most often after it paused because its "
         "pick found nothing (a site changed): preview a new pick first. Changing the "
         "check, pick, when or every starts its memory over (the next look learns). "
         "When the person says to keep a watch that ended or asked whether it's still "
         "wanted, give keep: true (and a new ends, if they say one)."),
     "inputSchema": {"type": "object", "properties": {
         "id": {"type": "string"}, "name": {"type": "string"},
         "asked": _ASKED, "thing": _THING,
         "starts": _STARTS, "ends": _ENDS, "stop": _STOP,
         "keep": {"type": "boolean", "description": (
             "true when the person says to keep it: an ended watch looks again, and "
             "one with no end stops asking whether it's wanted for 30 days")},
         "check": _CHECK, "pick": _PICK, "when": _WHEN, "every": _EVERY,
         "wake": _WAKE, "renew": _RENEW,
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
                 agent: str = "", runner: str | None = None, dvara=None,
                 home: set[str] | None = None) -> None:
        self.store = store
        #: The names this computer's own person goes by (their key is the
        #: one kept in the state folder).
        self.home = set(home or {watches.LOCAL_OWNER})
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
                               sample=args.get("sample"), agent=self.agent,
                               runner=self.runner, owner=self.person,
                               wake=str(args.get("wake") or ""), renew=args.get("renew"),
                               thing=str(args.get("thing") or ""),
                               starts=args.get("starts"), ends=args.get("ends"),
                               stop=args.get("stop"), store=self.store)
        lines = [f"The watch, in words: {said['sentence']}.", said.get("said", "")]
        asked = str(args.get("asked") or "").strip()
        if asked:
            # read back to the person before their yes: a reworded one is
            # caught here, not in the first message the watch sends
            lines.append(f'Its messages will begin: You asked: "{asked}" -- tell the '
                         "person that too; those must be their own words.")
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
                f"{watch.id} [{watch.state}] {watch.name}"
                + (f" (asked: \"{watch.asked}\")" if watch.asked else "")
                + f": {card['sentence']}. "
                f"{card['does']}.\n"
                + (f"  paused: {watch.paused_because}\n" if watch.paused_because else "")
                + (f"  last look: {last['outcome']} {last['value']}".rstrip()
                   if last else "  not looked yet"))
        return "\n".join(lines)

    def _inlet_address(self, args: dict) -> str:
        from prahari.http import inlet_token, public_inlet

        served = serving(self.state) or {}
        url = served.get("url") or "http://<this computer>:8782/"
        public = served.get("inlet_public") or public_inlet()
        key = (inlet_token(self.state) if self.person in self.home
               else self.store.inlet_key(self.person))
        lines = [f"POST {url}inlet/WORD?key={key}   (at home, on the house's network)"]
        if public:
            lines.append(f"POST {public}inlet/WORD?key={key}   (from anywhere)")
        lines += ["WORD is one lowercase word the watch listens for (whatsapp); the body "
                  "is a small JSON object, e.g. MacroDroid's {\"title\": "
                  "\"[notification_title]\", \"text\": \"[notification]\"}.",
                  "The key is this person's alone and can only knock: what is sent "
                  "reaches only their watches."]
        if not served:
            lines.append("Prahari is not running on this machine: nothing is heard until "
                         "it is.")
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
        # A WATCH AN AGENT MAKES SAYS WHAT IT IS FOR. The person was not
        # watching it being written, and later has only these to go by.
        missing = [k for k in ("name", "asked") if not str(args.get(k) or "").strip()]
        if missing:
            raise ToolFailed(
                f"give {' and '.join(missing)}: name is a few words the person will know "
                "it by (\"Phoenix nonstop under $571\"), never the tool's name; asked is "
                "what the person asked for, in their own words")
        made = watches.create(
            self.store, name=str(args.get("name") or ""), check=args.get("check"),
            asked=str(args.get("asked") or ""), thing=str(args.get("thing") or ""),
            starts=args.get("starts"), ends=args.get("ends"), stop=args.get("stop"),
            listen=str(args.get("listen") or ""), pick=args.get("pick"),
            when=args.get("when"), every=str(args.get("every") or ""),
            wake=str(args.get("wake") or ""), renew=args.get("renew"),
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
        changes = {k: args[k] for k in ("name", "asked", "thing", "check", "pick", "when",
                                        "every", "then", "max_per_day", "wake", "renew",
                                        "starts", "ends", "stop", "keep")
                   if k in args}
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
