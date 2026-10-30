"""`prahari`: tell your agent when something happens.

    prahari preview --check web_fetch --args '{"url": "..."}' --pick number --when 'below 50'
    prahari add "ALAB under $50" --check tradingview_open --args '{"symbol": "ALAB"}' \\
          --pick 'number:Last\\s*([\\d.,]+)' --when 'below 50' --every 3h
    prahari add "Mail from the bank" --check mcp__gmail__search_threads \\
          --args '{"account": "personal", "query": "from:bank@example.com newer_than:2d"}' \\
          --pick 'items:thread (\\w+)' --when new --every 30m
    prahari add "Mum on WhatsApp" --listen whatsapp --pick json:title --when 'contains Mum' \\
          --then "Read me what Mum said, and draft a reply I can send."
    prahari list | show ID | looks [ID] | look ID | pause ID | resume ID | rm ID
    prahari edit ID --pick ... --when ... --every ...     mend a watch
    prahari allow ID TOOL...                    let its then-turn use more tools unasked
    prahari add "Mail from the bank" ... --every 6h --wake work-mail
                                                looks at once when work-mail knocks
    prahari mailbox add work-mail --account mail:work
                                                a mail folder kept open (IMAP IDLE), its
                                                login in Setu (setu connect mail)
    prahari mailbox list | rm NAME
    prahari hear WORD JSON [--for WHO]          try the inlet without the network
    prahari serve [--port 8782] [--inlet-port 8783]
                                                the watch, its page and the inlet (and
                                                the inlet alone, for the public road)
    prahari inlet [--for WHO] [--new-key]       the inlet's address and key, for a sender
    prahari mcp --for WHO [--agent A]           the tools an agent uses (MCP, stdio)
    prahari status [--json]                     is it watching, and where
    prahari keeps [--json]                      where the watches are kept, for a backup
    prahari unit [--install]                    keep it running (systemd)

``--pick`` and ``--when`` take a short form (``number``, ``items:REGEX``,
``json:a.b``; ``below 50``, ``new``, ``contains Mum``) or the JSON an
agent sends. ``prahari serve`` has to run for anything to be looked at;
the other commands read and change the file, so they work either way.

State lives in ``~/.prahari`` (``--state`` or ``$PRAHARI_STATE``). Which
Yantra looks and works: ``$PRAHARI_YANTRA`` (the command) and
``$PRAHARI_YANTRA_HOME`` (where it starts, for its ``.env``).
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import threading
from pathlib import Path

from prahari import __version__, mailbox, mcp, recipe, version, watches
from prahari.clock import Clock
from prahari.dvara import Dvara, DvaraCaller, DvaraError, DvaraNotifier, DvaraRunner
from prahari.http import (DEFAULT_PORT, Api, PrahariServer, inlet_token, public_inlet,
                          serve_token)
from prahari.looking import Asker, Caller, DirectRunner, Roads
from prahari.status import hold_watch, prahari_command, report, serving
from prahari.store import Look, Store, Watch, from_iso


def state_dir(flag: str | None) -> Path:
    raw = flag or os.environ.get("PRAHARI_STATE", "").strip() or "~/.prahari"
    return Path(raw).expanduser()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="prahari", description="Watch for what you are waiting for, and tell "
                                    "your agent when it happens.")
    parser.add_argument("--state", metavar="DIR",
                        help="where watches and looks are kept "
                             "(default: $PRAHARI_STATE or ~/.prahari)")
    parser.add_argument("--version", action=version.Show)
    sub = parser.add_subparsers(dest="command", required=True)

    def recipe_flags(p, *, needed: bool) -> None:
        p.add_argument("--check", metavar="TOOL", default=None,
                       help="the tool to look with (it must read, or be this exact call)")
        p.add_argument("--args", metavar="JSON", default=None, dest="check_args",
                       help="its arguments, one JSON object")
        p.add_argument("--pick", default=None,
                       help="number[:REGEX], text:REGEX, json:PATH, items:REGEX, "
                            "items_json:PATH:KEY, or JSON (default: all of it)")
        p.add_argument("--when", required=needed, default=None,
                       help="below N, above N, at_most N, at_least N, equals X, "
                            "contains X, lacks X, matches REGEX, changed, new, any, "
                            "ask QUESTION, or JSON")
        p.add_argument("--every", default=None,
                       help="how often to look: 30m, 3h, 1d (default 1h)")
        p.add_argument("--wake", default=None, metavar="WORD",
                       help="look at once when WORD knocks at the inlet (a mailbox, "
                            "Gmail's push), not only every --every")
        p.add_argument("--renew", default=None, metavar="TOOL",
                       help="a call that keeps WORD's sender knocking, made at the "
                            "start and once a day (Gmail's watch_mailbox)")
        p.add_argument("--renew-args", default=None, metavar="JSON", dest="renew_args",
                       help="its arguments, one JSON object")

    p = sub.add_parser("preview", help="try a recipe once, and say what it sees")
    recipe_flags(p, needed=True)
    p.add_argument("--listen", default="", metavar="WORD")
    p.add_argument("--sample", default=None, metavar="JSON",
                   help="an event to try a --listen watch on")
    p.add_argument("--agent", default="", metavar="DIR|NAME")
    p.add_argument("--runner", choices=("direct", "dvara"), default="direct")
    p.add_argument("--as", dest="as_actor", default="", metavar="ACTOR")
    p.add_argument("--json", action="store_true", dest="json_out")

    p = sub.add_parser("add", help="add a watch")
    p.add_argument("name", help="a few words you will know it by")
    p.add_argument("--asked", default="", metavar="WORDS",
                   help="what it is for, in your own words (shown with it, and in its "
                        "messages)")
    p.add_argument("--thing", default="", metavar="WORDS",
                   help="what the pick takes: 'the fare', 'the temperature'")
    recipe_flags(p, needed=True)
    p.add_argument("--listen", default="", metavar="WORD",
                   help="hear this word at the inlet instead of looking")
    p.add_argument("--then", default="", metavar="PROMPT",
                   help="what the agent is asked when it fires (default: just tell you)")
    p.add_argument("--agent", default="", metavar="DIR|NAME",
                   help="the agent package that looks and works (Dvara road: its name)")
    p.add_argument("--runner", choices=("direct", "dvara"), default="direct")
    p.add_argument("--as", dest="as_actor", default="", metavar="ACTOR",
                   help="the person on Dvara's actors file it is for")
    p.add_argument("--allow-tools", action="append", default=[], dest="allow_tools",
                   metavar="GRANT", help="a tool the then-turn may use unasked (repeatable)")
    p.add_argument("--max-per-day", type=int, default=watches.DEFAULT_MAX_PER_DAY,
                   dest="max_per_day")
    p.add_argument("--wait", type=int, default=watches.DEFAULT_WAIT, metavar="MINUTES")
    p.add_argument("--time-limit", type=int, default=watches.DEFAULT_TIME_LIMIT,
                   dest="time_limit", metavar="SECONDS")
    p.add_argument("--json", action="store_true", dest="json_out")

    p = sub.add_parser("edit", help="mend a watch: its check, pick, test, how often, then")
    p.add_argument("id")
    recipe_flags(p, needed=False)
    p.add_argument("--name", default=None)
    p.add_argument("--asked", default=None, metavar="WORDS")
    p.add_argument("--thing", default=None, metavar="WORDS")
    p.add_argument("--then", default=None)
    p.add_argument("--max-per-day", type=int, default=None, dest="max_per_day")
    p.add_argument("--json", action="store_true", dest="json_out")

    p = sub.add_parser("list", help="every watch")
    p.add_argument("--json", action="store_true", dest="json_out")

    for name, text in (("show", "one watch in full"), ("pause", "stop looking, keep it"),
                       ("resume", "look again, from now"),
                       ("rm", "remove it, its looks and what it saw"),
                       ("look", "look once, now, and wait")):
        p = sub.add_parser(name, help=text)
        p.add_argument("id")
        p.add_argument("--json", action="store_true", dest="json_out")

    p = sub.add_parser("allow", help="let a watch's then-turn use more tools unasked")
    p.add_argument("id")
    p.add_argument("tools", nargs="+", metavar="TOOL")
    p.add_argument("--json", action="store_true", dest="json_out")

    p = sub.add_parser("looks", help="what was seen, newest first")
    p.add_argument("id", nargs="?")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--json", action="store_true", dest="json_out")

    p = sub.add_parser("hear", help="send the inlet something, here, and wait for it")
    p.add_argument("word")
    p.add_argument("body", help="a JSON object, or plain text")
    p.add_argument("--for", dest="person", default="", metavar="WHO",
                   help="as that person's knock (default: this computer's person)")
    p.add_argument("--json", action="store_true", dest="json_out")

    p = sub.add_parser("serve", help="the watch, its page and the inlet, until stopped")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=DEFAULT_PORT,
                   help=f"the page, its API and the inlet (default {DEFAULT_PORT}; 0 "
                        "for none)")
    p.add_argument("--public-url", default=None, metavar="URL")
    p.add_argument("--inlet-port", type=int, default=None, dest="inlet_port",
                   help="also the inlet ALONE on this port -- no page, no API -- for "
                        "the public road (default $PRAHARI_INLET_PORT, else 0: none)")
    p.add_argument("--inlet-host", default="127.0.0.1", dest="inlet_host")
    p.add_argument("--inlet-public-url", default=None, metavar="URL",
                   dest="inlet_public_url",
                   help="where the internet reaches it (Tailscale Funnel's address; "
                        "also $PRAHARI_INLET_PUBLIC_URL)")

    p = sub.add_parser("inlet", help="the inlet's address and key, for a sender")
    p.add_argument("--for", dest="person", default="", metavar="WHO",
                   help="that person's own key (made the first time)")
    p.add_argument("--new-key", action="store_true", dest="new_key",
                   help="a fresh key for that person; the old one stops working")
    p.add_argument("--json", action="store_true", dest="json_out")

    p = sub.add_parser("mailbox", help="mail folders kept open, knocking when mail "
                                       "comes (IMAP IDLE)")
    msub = p.add_subparsers(dest="mailbox_command", required=True)
    m = msub.add_parser("add", help="keep a Setu mail account's folder open")
    m.add_argument("name", help="the word it knocks on at the inlet (work-mail)")
    m.add_argument("--account", required=True, metavar="mail:NAME",
                   help="the Setu mail account it opens; add one first with: setu connect "
                        "mail --as NAME --mail-server HOST --user ADDRESS")
    m.add_argument("--for", dest="person", default="", metavar="WHO",
                   help="whose mailbox it is (default: this computer's person); their "
                        "account is in their own Setu folder, reached through Dvara")
    m.add_argument("--json", action="store_true", dest="json_out")
    m = msub.add_parser("list", help="every mailbox, and how it is doing")
    m.add_argument("--json", action="store_true", dest="json_out")
    m = msub.add_parser("rm", help="stop keeping it, and forget its password")
    m.add_argument("name")
    m.add_argument("--for", dest="person", default="", metavar="WHO")
    m.add_argument("--json", action="store_true", dest="json_out")

    p = sub.add_parser("mcp", help="the tools an agent uses to make watches (stdio)")
    p.add_argument("--for", dest="person", required=True, metavar="WHO")
    p.add_argument("--agent", default="", metavar="DIR|NAME")
    p.add_argument("--runner", choices=("direct", "dvara"), default=None)

    p = sub.add_parser("unit", help="a systemd user unit that keeps prahari serve "
                                    "running; prints it, or --install")
    p.add_argument("--install", action="store_true")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)

    p = sub.add_parser("status", help="is it watching, and where")
    p.add_argument("--json", action="store_true", dest="json_out")

    p = sub.add_parser("keeps", help="where the watches are kept, for a backup")
    p.add_argument("--json", action="store_true", dest="json_out")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    state = state_dir(args.state)
    if args.command == "keeps":
        # before the store is opened: asking where never makes the file
        from prahari.keeps import report as keeps
        said = keeps(state)
        if args.json_out:
            print(json.dumps(said))
        else:
            for place in said["keeps"]:
                print(f"{place['id']}  {place['path']}"
                      + ("" if place["exists"] else "  (not there yet)"))
                print(f"       {place['what']}")
        return 0
    try:
        store = Store(state / "prahari.sqlite3")
    except OSError as exc:
        print(f"error: cannot open {state}: {exc}", file=sys.stderr)
        return 2
    try:
        return _dispatch(args, store, state)
    except (watches.WatchError, recipe.RecipeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _recipe(args, pick_default=None) -> dict:
    """--check/--args/--pick/--when/--every as the recipe's parts."""
    check = None
    if args.check:
        try:
            given = json.loads(args.check_args) if args.check_args else {}
        except json.JSONDecodeError as exc:
            raise watches.WatchError(f"--args is not JSON: {exc}") from None
        check = {"tool": args.check, "args": given}
    elif args.check_args:
        raise watches.WatchError("--args goes with --check TOOL")
    pick = recipe.pick_from_text(args.pick) if args.pick is not None else pick_default
    when = (recipe.when_from_text(args.when, pick or {}) if args.when is not None
            else None)
    renew = None
    if args.renew:
        try:
            renew = {"tool": args.renew,
                     "args": json.loads(args.renew_args) if args.renew_args else {}}
        except json.JSONDecodeError as exc:
            raise watches.WatchError(f"--renew-args is not JSON: {exc}") from None
    elif args.renew_args:
        raise watches.WatchError("--renew-args goes with --renew TOOL")
    return {"check": check, "pick": pick, "when": when, "every": args.every,
            "wake": args.wake, "renew": renew}


def _dispatch(args, store: Store, state: Path) -> int:
    cmd = args.command
    if cmd == "preview":
        parts = _recipe(args, {})
        sample = None
        if args.sample:
            try:
                sample = json.loads(args.sample)
            except json.JSONDecodeError:
                sample = {"text": args.sample}
        said = watches.preview(_caller(state), check=parts["check"], listen=args.listen,
                               pick=parts["pick"], when=parts["when"],
                               every=parts["every"] or ("" if args.listen else "1h"),
                               sample=sample, agent=args.agent, runner=args.runner,
                               owner=args.as_actor or watches.LOCAL_OWNER,
                               wake=parts["wake"] or "", renew=parts["renew"],
                               store=store)
        if args.json_out:
            print(json.dumps(said))
        else:
            print(said["sentence"])
            print(said.get("said", ""))
            for item in said.get("items") or []:
                print(f"  {item}")
            if said.get("result") and not said.get("found", True):
                print("\nwhat the tool said:\n" + said["result"])
        return 0
    if cmd == "add":
        parts = _recipe(args, {})
        watch = watches.create(
            store, name=args.name, check=parts["check"], listen=args.listen,
            pick=parts["pick"], when=parts["when"],
            every=parts["every"] or ("" if args.listen else "1h"),
            wake=parts["wake"] or "", renew=parts["renew"], then=args.then,
            asked=args.asked, thing=args.thing,
            owner=args.as_actor or watches.LOCAL_OWNER, runner=args.runner,
            agent=args.agent, allow_tools=args.allow_tools, max_per_day=args.max_per_day,
            wait=args.wait, time_limit=args.time_limit,
            dvara=_dvara() if args.runner == "dvara" else None)
        if args.json_out:
            print(json.dumps(watches.card(watch)))
        else:
            print(f"added {watch.id}: {watch.name} -- {watches.sentence(watch)}")
            if serving(state) is None:
                print("prahari serve is not running: nothing is looked at until it is")
        return 0
    if cmd == "list":
        found = store.watches()
        if args.json_out:
            print(json.dumps([watches.card(w, store) for w in found]))
            return 0
        if not found:
            print("no watches (prahari add NAME --check TOOL --args JSON --when ...)")
        for watch in found:
            _print_watch(watch, store)
        return 0
    if cmd == "looks":
        watch_id = watches.find(store, args.id).id if args.id else None
        looks = store.looks(watch_id, limit=args.limit)
        if args.json_out:
            print(json.dumps([look.as_dict() for look in looks]))
            return 0
        if not looks:
            print("no looks yet")
        for look in looks:
            _print_look(look, with_watch=not args.id)
        return 0
    if cmd == "hear":
        try:
            body = json.loads(args.body)
        except json.JSONDecodeError:
            body = {"text": args.body}
        if not isinstance(body, dict):
            body = {"text": args.body}
        clock = _clock(state, store)
        owners = {args.person} if args.person else {watches.LOCAL_OWNER}
        whose = clock.people(owners)
        try:
            fired = clock.event(args.word, body, owners)
            for watch in store.watches(state="active", wake=args.word):
                if watch.owner in whose:
                    clock.wake(watch.id)
        finally:
            clock.close()                  # waits for a then-turn it started
        heard = [w for w in store.watches(state="active", listen=args.word)
                 if w.owner in whose]
        if args.json_out:
            print(json.dumps({"heard_by": len(heard), "fired": fired}))
        else:
            print(f"{len(heard)} watch(es) listen for {args.word!r}; fired: "
                  f"{', '.join(fired) or 'none'}")
            for watch_id in fired:
                for look in store.looks(watch_id, limit=1):
                    _print_look(look, with_watch=True)
        return 0
    if cmd == "serve":
        inlet_port = args.inlet_port
        if inlet_port is None:
            try:
                inlet_port = int(os.environ.get("PRAHARI_INLET_PORT", "0") or 0)
            except ValueError:
                raise watches.WatchError("PRAHARI_INLET_PORT is a port number") from None
        return _serve(store, state, host=args.host, port=args.port,
                      public_url=args.public_url, inlet_port=inlet_port,
                      inlet_host=args.inlet_host, inlet_public_url=args.inlet_public_url)
    if cmd == "inlet":
        return _inlet(args, store, state)
    if cmd == "mailbox":
        return _mailbox(args, store, state)
    if cmd == "mcp":
        tools = mcp.Tools(store, state, _caller(state), person=args.person,
                          agent=args.agent, runner=args.runner, dvara=_dvara(),
                          home=_home())
        mcp.serve(tools)
        return 0
    if cmd == "unit":
        from prahari import unit
        command = prahari_command()
        if not args.install:
            print(unit.unit_text(command, state.resolve(), args.port), end="")
            return 0
        written, env, names = unit.install(command, state.resolve(), args.port,
                                           dict(os.environ))
        print(f"wrote {written}")
        print(f"wrote {env} (yours alone): PATH" + (", " + ", ".join(names) if names else ""))
        print("nothing is started; to start it now and at every login:")
        for line in unit.NEXT:
            print(f"  {line}")
        return 0
    if cmd == "status":
        said = report(state, store)
        if args.json_out:
            print(json.dumps(said))
        else:
            counts = said["watches"]
            print(f"prahari {said['version']}: "
                  + (f"watching, page at {said['url']}" if said["serving"]
                     else "not running (prahari serve)"))
            print(f"  {counts['active']} active ({counts['listening']} listening at the "
                  f"inlet), {counts['paused']} paused; state in {said['state']}")
            print("  news goes to " + (said["dvara"] or "nobody (no Dvara set)"))
        return 0

    watch = watches.find(store, args.id)
    if cmd == "show":
        if args.json_out:
            print(json.dumps(watches.card(watch, store)))
        else:
            _print_watch(watch, store, full=True)
        return 0
    if cmd == "edit":
        parts = _recipe(args)
        changes = {k: v for k, v in parts.items() if v is not None}
        for key in ("name", "asked", "thing", "then", "max_per_day"):
            if getattr(args, key) is not None:
                changes[key] = getattr(args, key)
        if args.wake == "":
            changes["wake"], changes["renew"] = "", {}
        watch = watches.update(store, watch.id, **changes)
        print(json.dumps(watches.card(watch)) if args.json_out
              else f"updated {watch.id}: {watch.name} -- {watches.sentence(watch)}")
        return 0
    if cmd == "pause":
        watch = watches.pause(store, watch.id)
        print(json.dumps(watches.card(watch)) if args.json_out else f"paused {watch.id}")
        return 0
    if cmd == "resume":
        watch = watches.resume(store, watch.id)
        print(json.dumps(watches.card(watch)) if args.json_out
              else f"resumed {watch.id}: {watches.sentence(watch)}")
        return 0
    if cmd == "allow":
        watch = watches.allow(store, watch.id, args.tools)
        print(json.dumps(watches.card(watch)) if args.json_out
              else f"{watch.id}'s then-turn may now use without asking: "
                   f"{', '.join(watch.allow_tools)}")
        return 0
    if cmd == "rm":
        watches.remove(store, watch.id)
        print(json.dumps({"removed": watch.id}) if args.json_out else f"removed {watch.id}")
        return 0
    if cmd == "look":
        clock = _clock(state, store)
        try:
            look = clock.look_now(watch.id)
        except RuntimeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        finally:
            clock.close()
        look = next(iter(store.looks(watch.id, limit=1)), look)
        if args.json_out:
            print(json.dumps(look.as_dict()))
        else:
            _print_look(look, with_watch=False)
            if look.reply:
                print()
                print(look.reply)
        return 0 if look.outcome not in ("failed", "broken", "needs_person") else 1
    raise AssertionError(cmd)


# -- wiring ------------------------------------------------------------------------


def _dvara() -> Dvara | None:
    try:
        return Dvara.from_env()
    except DvaraError as exc:
        raise watches.WatchError(str(exc)) from None


def _caller(state: Path) -> Roads:
    """Each watch's look on its own road: here, or through Dvara as its person."""
    dvara = _dvara()
    return Roads(Caller(state / "work"), DvaraCaller(dvara) if dvara is not None else None)


def _home() -> set[str]:
    """The names this computer's person goes by: local, and Dvara's for them."""
    dvara = _dvara()
    return {watches.LOCAL_OWNER, *([dvara.actor] if dvara and dvara.actor else [])}


def _logins() -> mailbox.Logins:
    """A mailbox's login: this computer's person's from Setu, anyone else's
    through Dvara, as them."""
    return mailbox.Logins(home=_home(), dvara=_dvara())


def _clock(state: Path, store: Store, on_record=None) -> Clock:
    dvara = _dvara()
    runners: dict = {"direct": DirectRunner(state / "work", ask=dvara)}
    if dvara is not None:
        runners["dvara"] = DvaraRunner(dvara)
    return Clock(store, _caller(state), runners, asker=Asker(state / "work"),
                 notifier=DvaraNotifier(dvara) if dvara is not None else None,
                 on_record=on_record, home=_home())


def _inlet(args, store: Store, state: Path) -> int:
    """The inlet's address and a key, for a sender: this computer's
    person's, or with --for, that person's own."""
    served = serving(state) or {}
    url = served.get("url")
    public = served.get("inlet_public") or public_inlet()
    person = args.person.strip()
    if person and person in _home():
        person = ""
    if person:
        key = store.new_inlet_key(person) if args.new_key else store.inlet_key(person)
    elif args.new_key:
        raise watches.WatchError("this computer's own key is the one in "
                                 f"{state}/inlet.token (or $PRAHARI_INLET_TOKEN): delete "
                                 "the file and restart prahari serve for a new one")
    else:
        key = inlet_token(state)
    whose = {person} if person else _home()
    words = sorted({w.listen or w.wake for w in store.watches()
                    if (w.listen or w.wake) and w.owner in whose})
    if args.json_out:
        print(json.dumps({"url": f"{url}inlet/" if url else None,
                          "public_url": f"{public}inlet/" if public else None,
                          "key": key, "for": person or watches.LOCAL_OWNER,
                          "words": words}))
        return 0
    where = f"{url}inlet/WORD" if url else "http://<this computer>:8782/inlet/WORD"
    print(f"for:       {person or 'this computer (' + ', '.join(sorted(_home())) + ')'}")
    print(f"send to:   POST {where}")
    if public:
        print(f"   or:     POST {public}inlet/WORD   (from anywhere: the public road)")
    print(f"with:      Authorization: Bearer {key}")
    print(f"   or:     {where}?key={key}")
    print("hears:     " + (", ".join(words) or "nothing yet (prahari add NAME "
                                                "--listen WORD ...)"))
    if not url:
        print("prahari serve is not running: nothing is heard until it is")
    return 0


def _mailbox(args, store: Store, state: Path) -> int:
    which = args.mailbox_command
    owner = (getattr(args, "person", "") or "").strip() or watches.LOCAL_OWNER
    try:
        if which == "add":
            box, said = mailbox.add(store, name=args.name, owner=owner,
                                    account=args.account, logins=_logins())
            if args.json_out:
                print(json.dumps(box.as_dict()))
            else:
                print(f"{said}; kept as {box.name} for {box.owner}")
                print(f"  a new mail knocks on '{box.name}': use --listen {box.name} "
                      f"(read who and what) or --wake {box.name} (look at once)")
                if serving(state) is not None:
                    print("  prahari serve is running: restart it to start listening")
                else:
                    print("  listening starts with prahari serve")
            return 0
        if which == "list":
            boxes = store.mailboxes()
            if args.json_out:
                print(json.dumps([b.as_dict() for b in boxes]))
                return 0
            if not boxes:
                print("no mailboxes (setu connect mail --as work ..., then prahari mailbox "
                      "add work-mail --account mail:work)")
            for box in boxes:
                print(f"{box.name:<12} {box.owner:<10} {box.account}: {box.user} on "
                      f"{box.server} {box.folder}  [{box.state}]")
                if box.said:
                    print(f"             {box.said} ({_short(box.said_at)})")
            return 0
        if which == "rm":
            box = mailbox.remove(store, owner, args.name)
            print(json.dumps({"removed": box.name}) if args.json_out
                  else f"removed {box.name}; its account stays in Setu ({box.account})")
            return 0
    except mailbox.MailboxError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    raise AssertionError(which)


def _serve(store: Store, state: Path, *, host: str, port: int,
           public_url: str | None = None, inlet_port: int = 0,
           inlet_host: str = "127.0.0.1", inlet_public_url: str | None = None) -> int:
    held = hold_watch(state)
    if held is None:
        print(f"error: prahari serve is already running for {state}", file=sys.stderr)
        return 2
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    server = None

    def log(watch: Watch, look: Look) -> None:
        _print_look(look, with_watch=True)
        sys.stdout.flush()

    def started(interrupted: int) -> None:
        active = store.watches(state="active")
        dvara = _dvara()
        print(f"prahari {__version__}: {len(active)} active watch(es), state in {state}")
        if server is not None:
            print(f"page: {server.page_url}")
            print(f"inlet: {server.url}inlet/WORD  (key: prahari inlet)")
        if alone is not None:
            print(f"inlet alone: {alone.url}inlet/WORD"
                  + ("" if alone.public_url else
                     f" on {inlet_host}:{alone.httpd.server_address[1]}, no public "
                     "address set (--inlet-public-url)"))
        for keeper in keepers:
            print(f"mailbox {keeper.box.name} ({keeper.box.owner}): "
                  f"{keeper.box.user} on {keeper.box.server}")
        print(f"news goes to: {dvara.url} (/notify)" if dvara else
              "news goes nowhere: set PRAHARI_DVARA_URL to send it to people's "
              "channels; until then it is only kept")
        if interrupted:
            print(f"{interrupted} look(s) were going when Prahari last stopped; marked "
                  "interrupted")
        sys.stdout.flush()

    clock = _clock(state, store, on_record=log)
    api = Api(store, clock, state, _dvara(), inlet_key=inlet_token(state))
    alone = None
    if port:
        try:
            server = PrahariServer(api, serve_token(state), inlet_token(state), host=host,
                                   port=port, public_url=public_url)
        except (OSError, ValueError) as exc:
            clock.close()
            print(f"error: cannot serve the page on {host}:{port}: {exc}", file=sys.stderr)
            return 2
        server.start()
    if inlet_port:
        try:
            alone = PrahariServer(api, serve_token(state), inlet_token(state),
                                  host=inlet_host, port=inlet_port,
                                  public_url=inlet_public_url, inlet_only=True)
        except (OSError, ValueError) as exc:
            if server is not None:
                server.stop()
            clock.close()
            print(f"error: cannot serve the inlet on {inlet_host}:{inlet_port}: {exc}",
                  file=sys.stderr)
            return 2
        alone.start()

    def said(line: str) -> None:
        print(line)
        sys.stdout.flush()

    logins = _logins()
    keepers = [mailbox.Keeper(store, box, clock.hear, logins, log=said)
               for box in store.mailboxes()]
    for keeper in keepers:
        keeper.start()
    told = _dvara()
    (state / "serve.json").write_text(json.dumps(
        {"pid": os.getpid(), "url": server.url if server else None,
         "inlet_public": alone.url if alone and alone.public_url else None,
         "dvara": told.url if told else None, "local_to": told.actor if told else ""}))
    try:
        clock.serve(stop, on_start=started)
    finally:
        for keeper in keepers:
            keeper.close()
        for listening in (server, alone):
            if listening is not None:
                listening.stop()
        clock.close()
        (state / "serve.json").unlink(missing_ok=True)
    print("stopped")
    return 0


# -- printing ------------------------------------------------------------------------


def _short(moment: str | None) -> str:
    when = from_iso(moment)
    return "-" if when is None else f"{when.astimezone():%a %-d %b %H:%M}"


def _print_watch(watch: Watch, store: Store, full: bool = False) -> None:
    print(f"{watch.id}  {watch.state:<7} {watch.name}")
    if watch.asked:
        print(f"          asked: \"{watch.asked}\"")
    print(f"          {watches.sentence(watch)}")
    print(f"          then: {watch.then if watch.then else 'tells you what it saw'}"
          if full or watch.then else "          then: tells you what it saw")
    if watch.paused_because:
        print(f"          paused: {watch.paused_because}")
    last = store.looks(watch.id, limit=1)
    if last:
        look = last[0]
        print(f"          last: {look.outcome}  {_short(look.started_at)}"
              + (f"  {look.value}" if look.value else ""))
    if full:
        if watch.check:
            print(f"          check: {watch.check['tool']} {json.dumps(watch.check['args'])}")
        print(f"          pick: {json.dumps(watch.pick) if watch.pick else 'all'}"
              f"   when: {json.dumps(watch.when)}   most a day: {watch.max_per_day}")
        if watch.next_at and not watch.listen:
            print(f"          next look: {_short(watch.next_at)}")
        if watch.renew:
            print(f"          renew: {watch.renew['tool']} {json.dumps(watch.renew['args'])}"
                  f"   next: {_short(watch.renew_at)}")
        if watch.agent:
            print(f"          agent: {watch.agent}   runner: {watch.runner}")
        if watch.allow_tools:
            print(f"          then may use: {', '.join(watch.allow_tools)}")
        print(f"          made {_short(watch.created_at)} (by {watch.created_via}), "
              f"for {watch.owner}")


def _print_look(look: Look, with_watch: bool) -> None:
    head = f"{look.watch}  " if with_watch else ""
    turn = f"  then: {look.turn}" if look.turn else ""
    sent = "  sent" if look.notified else ""
    cost = f"  ${look.cost_usd:.4f}" if look.cost_usd else ""
    value = f"  {look.value}" if look.value else ""
    print(f"{head}{_short(look.started_at)}  {look.outcome:<9}{value}{turn}{sent}{cost}")
    pad = " " * len(head)
    for line in look.found[:5]:
        print(f"{pad}    • {line}")
    if look.detail and look.outcome not in ("quiet", "fired"):
        print(f"{pad}    {look.detail}")


if __name__ == "__main__":
    raise SystemExit(main())
