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
    prahari indriya add outside-temp --check weather_now --args '{"place": "Cary"}' \\
          --pick number --every 15m --thing "the outside temperature" [--share house]
                                                a shared reading: one call, any number
                                                of watches and agents read it
    prahari add "Heat the guestroom" --sense outside-temp --when 'below 60'
                                                a watch that decides on its readings
    prahari indriya templates [--market]        readings ready to install, with blanks
    prahari indriya install outside-temp --input latitude=35.79 --input longitude=-78.78
                                                one, filled in: your own indriya
    prahari indriya list | get NAME | readings NAME | look NAME
    prahari indriya edit NAME --every 30m | pause NAME | resume NAME | rm NAME
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

from prahari import (__version__, floors, indriyas, mailbox, mcp, recipe, templates, version,
                     watches)
from prahari.clock import Clock
from prahari.dvara import Dvara, DvaraCaller, DvaraError, DvaraNotifier, DvaraRunner
from prahari.http import (DEFAULT_PORT, Api, PrahariServer, inlet_token, public_inlet,
                          serve_token)
from prahari.looking import Asker, Caller, DirectRunner, Roads
from prahari.status import hold_watch, prahari_command, report, serving
from prahari.store import Indriya, Look, Reading, Store, Watch, from_iso


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
        p.add_argument("--from", default=None, dest="starts", metavar="WHEN",
                       help="start looking then: 2026-10-31T07:00 (this computer's "
                            "clock) or with an offset ('' for now)")
        p.add_argument("--until", default=None, dest="ends", metavar="WHEN",
                       help="end by itself then ('' for never)")
        p.add_argument("--stop", default=None, metavar="TEST",
                       help="end once what it sees passes this test: 'contains Landed', "
                            "'below 100' (same words as --when)")

    p = sub.add_parser("preview", help="try a recipe once, and say what it sees")
    recipe_flags(p, needed=True)
    p.add_argument("--listen", default="", metavar="WORD")
    p.add_argument("--sense", default="", metavar="INDRIYA",
                   help="decide on an indriya's readings instead of looking")
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
    p.add_argument("--sense", default="", metavar="INDRIYA",
                   help="decide on an indriya's readings instead of looking (it has "
                        "no --check or --every of its own)")
    p.add_argument("--look-itself", action="store_true", dest="look_itself",
                   help="make its own call even when an indriya already makes it "
                        "(by default it senses that indriya instead)")
    p.add_argument("--then", default="", metavar="PROMPT",
                   help="what the agent is asked when it fires (default: just tell you)")
    p.add_argument("--routine", default="", metavar="NAME",
                   help="instead of --then: start this routine (Vidhi) when it fires, "
                        "with what it saw as the routine's input found")
    p.add_argument("--input", action="append", default=[], metavar="NAME=VALUE",
                   dest="inputs",
                   help="with --routine: this watch's own value for one of the "
                        "routine's blanks (repeatable): --input city=Cary")
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
    p.add_argument("--routine", default=None, metavar="NAME",
                   help="start this routine (Vidhi) when it fires ('' for none)")
    p.add_argument("--input", action="append", default=None, metavar="NAME=VALUE",
                   dest="inputs",
                   help="change one of its routine's blanks (repeatable); NAME= "
                        "drops it")
    p.add_argument("--keep", action="store_true", default=None,
                   help="keep it going: an ended watch looks again, and an open-ended "
                        "one stops asking for 30 days")
    p.add_argument("--max-per-day", type=int, default=None, dest="max_per_day")
    p.add_argument("--sense", default=None, metavar="INDRIYA",
                   help="stop looking and decide on this indriya's readings instead "
                        "(what it remembered is kept when the indriya makes the same "
                        "call)")
    p.add_argument("--look-itself", action="store_true", default=None, dest="look_itself",
                   help="stop sensing its indriya and make the indriya's call itself "
                        "again (what it remembered is kept; the indriya may slow down)")
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

    p = sub.add_parser("looks", help="what was seen, newest first, and why each look "
                                     "was quiet, told you, or failed")
    p.add_argument("id", nargs="?")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--full", action="store_true",
                   help="also what the check answered, and the agent's reply")
    p.add_argument("--json", action="store_true", dest="json_out")

    p = sub.add_parser("indriya", help="shared readings: one call, read by any number "
                                       "of watches and agents")
    isub = p.add_subparsers(dest="indriya_command", required=True)
    i = isub.add_parser("add", help="a reading kept up to date")
    i.add_argument("name", help="one short word it is called by (outside-temp)")
    i.add_argument("--check", metavar="TOOL", default=None,
                   help="the tool it reads with (it must read, or be this exact call)")
    i.add_argument("--from-watch", metavar="ID", default=None, dest="from_watch",
                   help="take the call, pick, thing and how often from this watch")
    i.add_argument("--pushed", action="store_true",
                   help="no call: its value is sent in (POST /inlet/indriya/NAME, "
                        "Home Assistant), and --every is how often one is expected")
    i.add_argument("--move", action="store_true",
                   help="with --from-watch: move every watch of yours on that same call "
                        "onto it (otherwise they are listed)")
    i.add_argument("--args", metavar="JSON", default=None, dest="check_args")
    i.add_argument("--pick", default=None,
                   help="what it keeps out of the answer: number[:REGEX], text:REGEX, "
                        "json:PATH ... (default: all of it)")
    i.add_argument("--every", default=None,
                   help=f"how often it reads (default {indriyas.DEFAULT_EVERY}, or the "
                        "watch's with --from-watch)")
    i.add_argument("--thing", default="", metavar="WORDS",
                   help="what it reads: 'the outside temperature'")
    i.add_argument("--share", choices=("mine", "house"), default="mine",
                   help="house: anyone's watches and agents may read its value (never "
                        "call as you)")
    i.add_argument("--agent", default="", metavar="DIR|NAME")
    i.add_argument("--runner", choices=("direct", "dvara"), default="direct")
    i.add_argument("--as", dest="as_actor", default="", metavar="ACTOR")
    i.add_argument("--json", action="store_true", dest="json_out")
    i = isub.add_parser("templates", help="readings ready to install, with blanks")
    i.add_argument("--market", action="store_true",
                   help="also what the marketplace (Vidhi's VIDHI_MARKET) lists")
    i.add_argument("--json", action="store_true", dest="json_out")
    i = isub.add_parser("install", help="a template, filled in: an indriya of your own")
    i.add_argument("template", help="its name (prahari indriya templates)")
    i.add_argument("--from-market", action="store_true", dest="from_market",
                   help="fetch it from the marketplace, signed by a reviewer you trust "
                        "(vidhi market trust)")
    i.add_argument("--input", action="append", default=[], metavar="NAME=VALUE",
                   dest="inputs", help="one of its blanks (repeatable)")
    i.add_argument("--name", default="", help="call it this instead of the template's name")
    i.add_argument("--every", default="", help="how often it reads, instead of the "
                                               "template's")
    i.add_argument("--share", choices=("mine", "house"), default="")
    i.add_argument("--agent", default="", metavar="DIR|NAME")
    i.add_argument("--runner", choices=("direct", "dvara"), default="direct")
    i.add_argument("--as", dest="as_actor", default="", metavar="ACTOR")
    i.add_argument("--json", action="store_true", dest="json_out")
    i = isub.add_parser("edit", help="mend one: its call, pick, how often, who sees it")
    i.add_argument("name")
    i.add_argument("--check", metavar="TOOL", default=None)
    i.add_argument("--args", metavar="JSON", default=None, dest="check_args")
    i.add_argument("--pick", default=None)
    i.add_argument("--every", default=None)
    i.add_argument("--thing", default=None, metavar="WORDS")
    i.add_argument("--share", choices=("mine", "house"), default=None)
    i.add_argument("--json", action="store_true", dest="json_out")
    as_help = ("as that person sees them: their own, then the house's (default: "
               "this computer's person)")
    i = isub.add_parser("list", help="every indriya and what it read last")
    i.add_argument("--as", dest="as_actor", default="", metavar="ACTOR", help=as_help)
    i.add_argument("--json", action="store_true", dest="json_out")
    for name, text in (("get", "its value now, with how old it is"),
                       ("readings", "what it read, newest first")):
        i = isub.add_parser(name, help=text)
        i.add_argument("name")
        if name == "readings":
            i.add_argument("--limit", type=int, default=20)
            i.add_argument("--full", action="store_true",
                           help="each reading's why and what came in, and each "
                                "watch's why")
        else:
            i.add_argument("--max-age", default=None, dest="max_age", metavar="AGE",
                           help="read it again first if its value is older than this "
                                "(5m, 1h; not within 5 minutes of the last reading, or the "
                                "site's floor)")
        i.add_argument("--as", dest="as_actor", default="", metavar="ACTOR", help=as_help)
        i.add_argument("--json", action="store_true", dest="json_out")
    i = isub.add_parser("push", help="send a pushed indriya a value, here (as its "
                                     "sender would), and wait for its watches")
    i.add_argument("name")
    i.add_argument("value", help="a number or words, or a JSON object")
    i.add_argument("--at", default=None, metavar="TIME",
                   help="when it was measured (ISO 8601 with a zone), if not now")
    i.add_argument("--as", dest="as_actor", default="", metavar="ACTOR")
    i.add_argument("--json", action="store_true", dest="json_out")
    for name, text in (("look", "read once, now, and wait"),
                       ("pause", "stop reading, keep it"), ("resume", "read again, from now"),
                       ("rm", "remove it and its readings (not while a watch senses it)")):
        i = isub.add_parser(name, help=text)
        i.add_argument("name")
        i.add_argument("--json", action="store_true", dest="json_out")

    p = sub.add_parser("floor", help="the least time between two calls to one site")
    fsub = p.add_subparsers(dest="floor_command", required=True)
    f = fsub.add_parser("list", help="every site's floor")
    f.add_argument("--json", action="store_true", dest="json_out")
    f = fsub.add_parser("set", help="call this site no more often than this (slows "
                                    "what already calls it faster)")
    f.add_argument("site", help="a host (api.open-meteo.com, its subdomains too) or a "
                                "tool's name")
    f.add_argument("every", help="15m, 1h ...")
    f.add_argument("--why", default="", metavar="WORDS", help="what the site asks, in a "
                                                              "few words")
    f.add_argument("--json", action="store_true", dest="json_out")
    f = fsub.add_parser("rm", help="back to the five-minute floor for this site")
    f.add_argument("site")
    f.add_argument("--json", action="store_true", dest="json_out")

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
    p.add_argument("--zone", default="", metavar="ZONE",
                   help="the person's own time zone (Europe/London): days and times "
                        "on their clock")

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


def _recipe(args, pick_default=None, pick_now=None) -> dict:
    """--check/--args/--pick/--when/--every as the recipe's parts.
    ``pick_now``: the watch's own pick, which a mended --when or --stop is
    read against when no new --pick is given (it is not a change itself)."""
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
    reads = pick if pick is not None else (pick_now or {})
    when = (recipe.when_from_text(args.when, reads) if args.when is not None
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
    stop = (recipe.when_from_text(args.stop, reads) if args.stop else
            ({} if args.stop == "" else None))
    return {"check": check, "pick": pick, "when": when, "every": args.every,
            "wake": args.wake, "renew": renew, "starts": args.starts, "ends": args.ends,
            "stop": stop}


def _dispatch(args, store: Store, state: Path) -> int:
    cmd = args.command
    if cmd == "preview":
        sensed = indriyas.find(store, args.sense, watches.LOCAL_OWNER, _home()) \
            if args.sense else None
        parts = _recipe(args, sensed.pick if sensed else {})
        sample = None
        if args.sample:
            try:
                sample = json.loads(args.sample)
            except json.JSONDecodeError:
                sample = {"text": args.sample}
        said = watches.preview(_caller(state), check=parts["check"], listen=args.listen,
                               pick=parts["pick"], when=parts["when"],
                               every=parts["every"] or ("" if args.listen or sensed
                                                        else "1h"),
                               sample=sample, agent=args.agent, runner=args.runner,
                               owner=args.as_actor or watches.LOCAL_OWNER,
                               wake=parts["wake"] or "", renew=parts["renew"],
                               starts=parts["starts"], ends=parts["ends"],
                               stop=parts["stop"], store=store,
                               sense=sensed.id if sensed else "", home=_home())
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
        owner = args.as_actor or watches.LOCAL_OWNER
        sensed = indriyas.find(store, args.sense, owner, _home()) if args.sense else None
        parts = _recipe(args, sensed.pick if sensed else {})
        watch = watches.create(
            store, name=args.name, check=parts["check"], listen=args.listen,
            sense=sensed.id if sensed else "", home=_home(),
            pick=parts["pick"], when=parts["when"],
            every=parts["every"] or ("" if args.listen or sensed else "1h"),
            wake=parts["wake"] or "", renew=parts["renew"], then=args.then,
            routine=args.routine, routine_inputs=_pairs(args.inputs),
            asked=args.asked, thing=args.thing, starts=parts["starts"], ends=parts["ends"],
            stop=parts["stop"], owner=args.as_actor or watches.LOCAL_OWNER, runner=args.runner,
            agent=args.agent, allow_tools=args.allow_tools, max_per_day=args.max_per_day,
            wait=args.wait, time_limit=args.time_limit,
            dvara=_dvara() if args.runner == "dvara" else None,
            look_itself=args.look_itself, notes=(notes := []))
        if args.json_out:
            print(json.dumps({**watches.card(watch), "notes": notes}))
        else:
            print(f"added {watch.id}: {watch.name} -- {watches.sentence(watch, store)}")
            for note in notes:
                print(f"  {note}")
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
            _print_look(look, with_watch=not args.id, full=args.full)
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
    if cmd == "indriya":
        return _indriya(args, store, state)
    if cmd == "floor":
        return _floor(args, store)
    if cmd == "mcp":
        tools = mcp.Tools(store, state, _caller(state), person=args.person,
                          agent=args.agent, runner=args.runner, dvara=_dvara(),
                          home=_home(), zone=args.zone)
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
        parts = _recipe(args, pick_now=watch.pick)
        changes = {k: v for k, v in parts.items() if v is not None}
        for key in ("name", "asked", "thing", "then", "max_per_day", "keep", "routine"):
            if getattr(args, key) is not None:
                changes[key] = getattr(args, key)
        if args.inputs is not None:
            merged = dict(watch.routine_inputs or {})
            for name, value in _pairs(args.inputs, drops=True).items():
                if value == "":
                    merged.pop(name, None)
                else:
                    merged[name] = value
            changes["routine_inputs"] = merged
        if args.wake == "":
            changes["wake"], changes["renew"] = "", {}
        if args.sense or args.look_itself:
            changes = {k: v for k, v in changes.items()
                       if k in ("name", "asked", "thing", "then")}
            changes.update(home=_home())
            if args.sense:
                changes["sense"] = args.sense
            if args.look_itself:
                changes["look_itself"] = True
        notes: list[str] = []
        watch = watches.update(store, watch.id, notes=notes, **changes)
        if args.json_out:
            print(json.dumps({**watches.card(watch), "notes": notes}))
            return 0
        print(f"updated {watch.id}: {watch.name} -- {watches.sentence(watch, store)}")
        for line in notes:
            print(f"  {line}")
        return 0
    if cmd == "pause":
        watch = watches.pause(store, watch.id)
        print(json.dumps(watches.card(watch)) if args.json_out else f"paused {watch.id}")
        return 0
    if cmd == "resume":
        watch = watches.resume(store, watch.id)
        print(json.dumps(watches.card(watch)) if args.json_out
              else f"resumed {watch.id}: {watches.sentence(watch, store)}")
        return 0
    if cmd == "allow":
        watch = watches.allow(store, watch.id, args.tools)
        print(json.dumps(watches.card(watch)) if args.json_out
              else f"{watch.id}'s then-turn may now use without asking: "
                   f"{', '.join(watch.allow_tools)}")
        return 0
    if cmd == "rm":
        notes = []
        watches.remove(store, watch.id, notes=notes)
        if args.json_out:
            print(json.dumps({"removed": watch.id, "notes": notes}))
            return 0
        print(f"removed {watch.id}")
        for line in notes:
            print(f"  {line}")
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


def _clock(state: Path, store: Store, on_record=None, on_reading=None) -> Clock:
    dvara = _dvara()
    runners: dict = {"direct": DirectRunner(state / "work", ask=dvara)}
    if dvara is not None:
        runners["dvara"] = DvaraRunner(dvara)
    return Clock(store, _caller(state), runners, asker=Asker(state / "work"),
                 notifier=DvaraNotifier(dvara) if dvara is not None else None,
                 on_record=on_record, home=_home(), on_reading=on_reading)


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


def _indriya(args, store: Store, state: Path) -> int:
    """``prahari indriya ...``: this computer's person's readings, and the
    house's (read-only, unless they are this person's)."""
    sub = args.indriya_command
    home = _home()
    if sub == "templates":
        found = [t.card() for t in templates.bundled()]
        listed = templates.market() if args.market else []
        if args.json_out:
            print(json.dumps({"templates": found, "market": listed}))
            return 0
        for card in found:
            print(f"{card['name']:<14} {card['title']}")
            print(f"{'':<14} {'' if card['pushed'] else 'calls '}{card['calls']}")
            if card["inputs"]:
                print(f"{'':<14} fill: " + ", ".join(
                    f"{i['name']} ({i['label']}"
                    + (f", default {i['default']}" if "default" in i else "") + ")"
                    for i in card["inputs"]))
        for item in listed:
            print(f"{item['name']:<14} {item['title']}  (marketplace, reviewed by "
                  f"{item.get('reviewer')}: --from-market)")
        print("install one: prahari indriya install NAME --input NAME=VALUE ...")
        return 0
    if sub == "install":
        template = (templates.fetch(args.template) if args.from_market
                    else templates.find(args.template))
        made = templates.install(
            store, template, _pairs(args.inputs), name=args.name, every=args.every,
            share=args.share, owner=args.as_actor or watches.LOCAL_OWNER,
            runner=args.runner, agent=args.agent,
            dvara=_dvara() if args.runner == "dvara" else None)
        if args.json_out:
            print(json.dumps(indriyas.card(made, store)))
            return 0
        print(f"added indriya {made.name} from {template.name}"
              + (f" (signed by {template.signed_by})" if template.signed_by else "")
              + f": {indriyas.sentence(made)}")
        if made.pushed:
            print(f"send it values: POST <prahari>/inlet/indriya/{made.name} with "
                  '{"value": 68.2}; the key: prahari inlet')
        print(f"watches decide on it with: prahari add NAME --sense {made.name} --when ...")
        if serving(state) is None:
            print("prahari serve is not running: nothing is read until it is")
        return 0
    if sub == "add" and args.from_watch:
        if args.check or args.check_args or args.pick is not None:
            raise watches.WatchError("--from-watch takes the call and pick from the watch; "
                             "leave out --check, --args and --pick")
        # at the terminal any watch is the person's to name, as for `edit`:
        # one made from a chat is filed under their Dvara name, not local
        source = watches.find(store, args.from_watch, owner=args.as_actor or None)
        there = any(i.name == args.name.strip().lower()
                    for i in store.indriyas(owner=source.owner))
        made, moved, could = indriyas.from_watch(
            store, source, name=args.name, share=args.share, every=args.every or "",
            move=args.move, home=home,
            dvara=_dvara() if source.runner == "dvara" else None, thing=args.thing)
        if args.json_out:
            print(json.dumps({**indriyas.card(made, store),
                              "moved": [w.id for w in moved],
                              "could_move": [w.id for w in could]}))
            return 0
        print(f"{'moved onto' if args.move and there else 'added'} "
              f"indriya {made.name}: {indriyas.sentence(made)}")
        for watch in moved:
            print(f"  moved {watch.id} ({watch.name}) onto it: it no longer calls itself")
        if could:
            print("watches of yours on this same call (each still calls itself):")
            for watch in could:
                print(f"  {watch.id}  {watch.name}")
            print(f"move them with: prahari edit ID --sense {made.name}   (or this same "
                  "command again, with --move)")
        if serving(state) is None:
            print("prahari serve is not running: nothing is read until it is")
        return 0
    if sub == "add" and args.pushed:
        if args.check or args.check_args:
            raise watches.WatchError("a pushed indriya makes no call: leave out --check "
                                     "and --args")
        made = indriyas.create(
            store, name=args.name, pushed=True,
            pick=recipe.pick_from_text(args.pick) if args.pick is not None else None,
            every=args.every or "", thing=args.thing, share=args.share,
            owner=args.as_actor or watches.LOCAL_OWNER, created_via="cli")
        if args.json_out:
            print(json.dumps(indriyas.card(made, store)))
            return 0
        served = serving(state) or {}
        where = served.get("url") or "http://<this computer>:8782/"
        print(f"added indriya {made.name}: {indriyas.sentence(made)}")
        print(f"send it values: POST {where}inlet/indriya/{made.name}   with "
              '{"value": 68.2} (or the number alone)')
        print("               the key: prahari inlet"
              + (f" --for {args.as_actor}" if args.as_actor else "")
              + f"   try it here: prahari indriya push {made.name} 68.2")
        print(f"watches decide on it with: prahari add NAME --sense {made.name} --when ...")
        return 0
    if sub == "push":
        whose = {args.as_actor} if args.as_actor else home
        indriya = indriyas.for_knock(store, args.name, whose)
        if indriya.state != "active":
            raise watches.WatchError(f"{indriya.name} is paused ({indriya.paused_because});"
                                     f" prahari indriya resume {indriya.name}")
        try:
            body = json.loads(args.value)
        except json.JSONDecodeError:
            body = None
        sent = body if isinstance(body, dict) else {"value": args.value}
        if args.at:
            sent = {**sent, "at": args.at}
        text = json.dumps(sent, sort_keys=True, ensure_ascii=False)
        clock = _clock(state, store)
        try:
            reading = clock.push(indriya, text)
        finally:
            clock.close()
        if args.json_out:
            print(json.dumps(reading.as_dict()))
            return 0
        _print_reading(reading)
        for watch in store.watches(sense=indriya.id):
            for look in store.looks(watch.id, limit=1):
                _print_look(look, with_watch=True)
        return 0 if reading.outcome in ("read", "late") else 1
    if sub == "add":
        if not args.check:
            raise watches.WatchError("an indriya needs --check TOOL (or --from-watch ID, "
                                     "or --pushed)")
        given = _json_args(args.check_args)
        made = indriyas.create(
            store, name=args.name, check={"tool": args.check, "args": given},
            pick=recipe.pick_from_text(args.pick) if args.pick is not None else {},
            every=args.every or "", thing=args.thing, share=args.share,
            owner=args.as_actor or watches.LOCAL_OWNER, runner=args.runner,
            agent=args.agent, dvara=_dvara() if args.runner == "dvara" else None)
        if args.json_out:
            print(json.dumps(indriyas.card(made, store)))
        else:
            print(f"added indriya {made.name}: {indriyas.sentence(made)}")
            print(f"watches decide on it with: prahari add NAME --sense {made.name} "
                  "--when ...")
            if serving(state) is None:
                print("prahari serve is not running: nothing is read until it is")
        return 0
    # Reading is anyone's who may see it (--as: Dvara asks for its person);
    # changing one is only ever this computer's person's own.
    reader = getattr(args, "as_actor", "") or watches.LOCAL_OWNER
    if sub == "list":
        found = indriyas.visible(store, reader, home)
        if args.json_out:
            print(json.dumps([indriyas.card(i, store) for i in found]))
            return 0
        if not found:
            print("no indriyas (prahari indriya add NAME --check TOOL --args JSON "
                  "--pick ... --every 15m)")
        for indriya in found:
            _print_indriya(indriya, store)
        return 0
    indriya = indriyas.find(store, args.name, reader, home,
                            own_only=sub in ("edit", "pause", "resume", "rm", "look"))
    if sub == "get":
        indriya, said = indriyas.fresh(store, _caller(state), indriya,
                                       indriyas.max_age(args.max_age))
        if args.json_out:
            print(json.dumps({**indriyas.card(indriya, store), "fresh": said}))
        else:
            _print_indriya(indriya, store, full=True)
            if said:
                print(f"  ({said})")
        return 0
    if sub == "readings":
        # at the computer every watch is shown; --as, as that person sees it
        people = None
        if getattr(args, "as_actor", ""):
            people = {args.as_actor} | (home if args.as_actor in home else set())
        rows = indriyas.history(store, indriya, args.limit, people)
        if args.json_out:
            print(json.dumps(rows))
            return 0
        if not rows:
            print("no readings yet")
        for line in indriyas.history_lines(rows, full=args.full, when=_short):
            print(line)
        return 0
    if sub == "edit":
        changes = {"pick": recipe.pick_from_text(args.pick) if args.pick is not None
                   else None, "every": args.every, "thing": args.thing,
                   "share": args.share}
        if args.check:
            changes["check"] = {"tool": args.check, "args": _json_args(args.check_args)}
        elif args.check_args:
            changes["check"] = {"tool": indriya.check["tool"],
                                "args": _json_args(args.check_args)}
        indriya = indriyas.update(store, indriya.id, **changes)
        print(json.dumps(indriyas.card(indriya, store)) if args.json_out
              else f"updated indriya {indriya.name}: {indriyas.sentence(indriya)}")
        return 0
    if sub == "pause":
        indriya = indriyas.pause(store, indriya)
        print(json.dumps(indriyas.card(indriya)) if args.json_out
              else f"paused indriya {indriya.name}")
        return 0
    if sub == "resume":
        indriya = indriyas.resume(store, indriya)
        print(json.dumps(indriyas.card(indriya)) if args.json_out
              else f"resumed indriya {indriya.name}: {indriyas.sentence(indriya)}")
        return 0
    if sub == "rm":
        indriyas.remove(store, indriya)
        print(json.dumps({"removed": indriya.id}) if args.json_out
              else f"removed indriya {indriya.name}")
        return 0
    if sub == "look":
        clock = _clock(state, store)
        try:
            reading = clock.read_now(indriya.id)
        except RuntimeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        finally:
            clock.close()
        if args.json_out:
            print(json.dumps(reading.as_dict()))
        else:
            _print_reading(reading)
            for watch in store.watches(sense=indriya.id):
                for look in store.looks(watch.id, limit=1):
                    _print_look(look, with_watch=True)
        return 0 if reading.outcome == "read" else 1
    raise AssertionError(sub)


def _json_args(raw: str | None) -> dict:
    try:
        given = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        raise watches.WatchError(f"--args is not JSON: {exc}") from None
    if not isinstance(given, dict):
        raise watches.WatchError("--args is one JSON object")
    return given


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

    def read(indriya: Indriya, reading: Reading) -> None:
        print(f"indriya {indriya.name}  ", end="")
        _print_reading(reading)
        sys.stdout.flush()

    def started(interrupted: int) -> None:
        active = store.watches(state="active")
        dvara = _dvara()
        senses = store.indriyas(state="active")
        print(f"prahari {__version__}: {len(active)} active watch(es)"
              + (f", {len(senses)} indriya(s)" if senses else "") + f", state in {state}")
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

    clock = _clock(state, store, on_record=log, on_reading=read)
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


def _pairs(raw: list[str] | None, *, drops: bool = False) -> dict:
    """``["city=Cary"]`` as ``{"city": "Cary"}``; ``city=`` kept as "" to
    drop it, when ``drops``."""
    out = {}
    for pair in raw or []:
        name, eq, value = pair.partition("=")
        if not eq or not name.strip() or (not value.strip() and not drops):
            raise watches.WatchError(f"--input is NAME=VALUE (city=Cary), not {pair!r}")
        out[name.strip()] = value.strip()
    return out


def _print_watch(watch: Watch, store: Store, full: bool = False) -> None:
    print(f"{watch.id}  {watch.state:<7} {watch.name}")
    if watch.asked:
        print(f"          asked: \"{watch.asked}\"")
    print(f"          {watches.sentence(watch, store)}"
          + (f"  (times on {watch.zone})" if watch.zone else ""))
    if watch.routine:
        print(f"          then: starts the routine {watch.routine}"
              f"{watches.inputs_words(watch)} (Vidhi)")
    else:
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
        if watch.next_at and watch.check:
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


def _print_indriya(indriya: Indriya, store: Store, full: bool = False) -> None:
    print(f"{indriya.id}  {indriya.state:<7} {indriyas.reading_line(indriya)}")
    print(f"          {indriyas.sentence(indriya)}")
    if indriya.owner != watches.LOCAL_OWNER:
        print(f"          {indriya.owner}'s")
    using = store.watches(sense=indriya.id)
    if using:
        print("          sensed by: " + ", ".join(f"{w.id} ({w.name})" for w in using))
    if full:
        if indriya.pushed:
            print("          check: none, its value is sent in")
        else:
            print(f"          check: {indriya.check['tool']} "
                  f"{json.dumps(indriya.check.get('args') or {})}")
        print(f"          pick: {json.dumps(indriya.pick) if indriya.pick else 'all'}"
              f"   {'a value due by' if indriya.pushed else 'next reading'}: "
              f"{_short(indriya.next_at)}")
        if indriya.own_every and indriya.own_every != indriya.every:
            print(f"          you set every {indriya.own_every}; a watch on it asked for "
                  f"{indriya.every}, and it comes back when they go")
        if indriya.agent:
            print(f"          agent: {indriya.agent}   runner: {indriya.runner}")
        print(f"          made {_short(indriya.created_at)} (by {indriya.created_via}), "
              f"for {indriya.owner}")


def _floor(args, store: Store) -> int:
    """``prahari floor ...``: how often a site may be called, at least apart."""
    sub = args.floor_command
    if sub == "list":
        found = store.floors()
        if args.json_out:
            print(json.dumps([f.as_dict() for f in found]))
            return 0
        if not found:
            print(f"no floors: every site is called at most every "
                  f"{recipe.duration_words(recipe.MIN_EVERY)} "
                  "(prahari floor set SITE 15m --why ...)")
        for floor in found:
            print(f"{floor.site:<30} every {floor.every}"
                  + (f"  ({floor.why})" if floor.why else ""))
        return 0
    if sub == "set":
        floor, slowed = floors.put(store, args.site, args.every, args.why)
        if args.json_out:
            print(json.dumps({**floor.as_dict(), "slowed": slowed}))
            return 0
        print(f"{floors.words(floor)}")
        for line in slowed:
            print(f"  {line}")
        return 0
    if sub == "rm":
        gone = floors.remove(store, args.site)
        if args.json_out:
            print(json.dumps({"removed": args.site if gone else None}))
            return 0 if gone else 1
        print(f"{args.site} is back to the floor every call has: once every "
              f"{recipe.duration_words(recipe.MIN_EVERY)} at most"
              if gone else f"no floor for {args.site}")
        return 0 if gone else 1
    raise AssertionError(sub)


def _print_reading(reading: Reading) -> None:
    value = f"  {reading.value}" if reading.value else ""
    measured = (f"  (measured {_short(reading.measured_at)})"
                if reading.measured_at and reading.measured_at != reading.at else "")
    print(f"{_short(reading.at)}  {reading.outcome:<9}{value}{measured}")
    if reading.outcome != "read":
        if reading.why:
            print(f"    why: {reading.why}")
        if reading.detail:
            print(f"    {reading.detail}")


def _print_look(look: Look, with_watch: bool, full: bool = False) -> None:
    head = f"{look.watch}  " if with_watch else ""
    turn = f"  then: {look.turn}" if look.turn else ""
    sent = "  sent" if look.notified else ""
    cost = f"  ${look.cost_usd:.4f}" if look.cost_usd else ""
    value = f"  {look.value}" if look.value else ""
    print(f"{head}{_short(look.started_at)}  {look.outcome:<9}{value}{turn}{sent}{cost}")
    pad = " " * len(head)
    for line in look.found[:5]:
        print(f"{pad}    • {line}")
    if look.why:
        print(f"{pad}    why: {look.why}")
    if look.detail and look.outcome not in ("quiet", "fired", "learned"):
        print(f"{pad}    {look.detail}")
    if full:
        came = f"came by: {look.came_by}"
        run = f"   Dvara run: {look.dvara_run_id}" if look.dvara_run_id else ""
        print(f"{pad}    {came}{run}")
        if look.said:
            print(f"{pad}    the check answered:")
            for line in look.said.splitlines()[:40]:
                print(f"{pad}      {line}")
        if look.reply:
            print(f"{pad}    the agent said:")
            for line in look.reply.splitlines()[:40]:
                print(f"{pad}      {line}")


if __name__ == "__main__":
    raise SystemExit(main())
