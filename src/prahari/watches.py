"""Making, changing and showing watches -- what the CLI, the page and the
agent's tools all call, so the three cannot disagree about what a watch
is allowed to be.

A WATCH IS CHECKED WHOLE BEFORE ANYTHING IS SAVED. Its check names one
tool and its arguments, or its listen names one word at the inlet --
never both, never neither; its pick and its test are read by recipe.py,
which refuses an unknown key by name; a watch that looks has an
``every`` and one that listens has none. A mistake is said in words, so
a model that proposed it can fix it.

ONE PERSON'S WATCHES ARE THAT PERSON'S. ``find`` with an ``owner``
treats someone else's watch as no watch at all: the agent's tools are
started for one person, and the id of another's is not a door into it.

A KNOCK CAN WAKE A WATCH THAT LOOKS (``wake``). Mail that a mailbox or
Gmail pushes needs no recipe of its own: the watch keeps its check, and a
knock on its word at the inlet makes it look now rather than at its next
``every`` -- which stays, as the look that happens anyway if a push is
lost. ``renew`` is the call that keeps such a sender knocking (Gmail's
push lasts seven days): checked like a check, granted word for word
because the person accepted it on the same card.

A CAP PER PERSON (``$PRAHARI_MAX_WATCHES``, default 30). A watch looks on
its own, forever, and every look starts a program; a loop in a model's
reasoning should not be able to leave hundreds behind.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from prahari import recipe
from prahari.store import RUNNERS, Store, Watch, from_iso, iso, now_utc

#: The person at this computer -- Samay's word for it too.
LOCAL_OWNER = "local"

DEFAULT_MAX_PER_DAY = 10
DEFAULT_WAIT = 30
DEFAULT_TIME_LIMIT = 600

_TOOL = re.compile(r"^[A-Za-z_][A-Za-z0-9_.:-]{0,127}$")
_WORD = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")


class WatchError(ValueError):
    """A watch that cannot be made or changed, said in words."""


def place(zone: str = ""):
    """``zone`` ("Europe/London") as a tzinfo; None for this computer's
    clock. A name nobody knows is a WatchError, never a silent UTC."""
    zone = (zone or "").strip()
    if not zone:
        return None
    try:
        return ZoneInfo(zone)
    except (ZoneInfoNotFoundError, ValueError):
        raise WatchError(f"zone is a time zone like Europe/London, not {zone!r}") from None


def moment(raw, what: str, zone: str = "") -> str | None:
    """A start or an end, as ISO in UTC; None for none. ISO 8601 with the
    person's offset ("2026-10-31T23:59-04:00"); without one, it is on the
    person's clock (``zone``), or with none this computer's own (the
    house's, for a time typed here)."""
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        when = datetime.fromisoformat(text)
    except ValueError:
        raise WatchError(f"{what} is a date and time like 2026-10-31T23:59-04:00 "
                         f"(with the person's offset), not {text!r}") from None
    if when.tzinfo is None:
        tz = place(zone)
        when = when.replace(tzinfo=tz) if tz is not None else when.astimezone()
    return iso(when)


def shown_at(stamp: str | None, zone: str = "") -> str:
    """A start or end the way a person reads it: on their clock (``zone``),
    or with none on this computer's."""
    when = from_iso(stamp)
    if when is None:
        return ""
    try:
        tz = place(zone)
    except WatchError:
        tz = None
    return f"{when.astimezone(tz):%a %-d %b %H:%M}"


def max_watches() -> int:
    try:
        return max(1, int(os.environ.get("PRAHARI_MAX_WATCHES", "30")))
    except ValueError:
        return 30


def _call(raw, what: str) -> dict:
    """``{"tool": NAME, "args": {...}}``, checked; WatchError in words."""
    call = recipe._form(raw, what)
    if not call:
        return {}
    unknown = [k for k in call if k not in ("tool", "args")]
    if unknown:
        raise WatchError(f"unknown key(s) {', '.join(unknown)} in {what}; known: "
                         "tool, args")
    tool = str(call.get("tool") or "")
    if not _TOOL.match(tool):
        raise WatchError(f"{what} tool is a tool's exact name, not {tool!r}")
    args = call.get("args") or {}
    if not isinstance(args, dict):
        raise WatchError(f"{what} args is an object of the tool's arguments")
    return {"tool": tool, "args": args}


def checked(*, name: str = "", check=None, listen: str = "", pick=None, when=None,
            every: str = "", wake: str = "", renew=None, asked: str = "",
            thing: str = "", starts=None, ends=None, stop=None, zone: str = "") -> dict:
    """The recipe's parts, checked together; WatchError in words."""
    try:
        check = recipe._form(check, "check")
        listen = (listen or "").strip().lower()
        if check and listen:
            raise WatchError("a watch either looks (check) or listens (listen), not both")
        if not check and not listen:
            raise WatchError("a watch needs a check -- {\"tool\": NAME, \"args\": {...}} "
                             "-- or a listen word for the inlet")
        wake = (wake or "").strip().lower()
        renew = _call(renew, "renew")
        if check:
            check = _call(check, "check")
            recipe.every(every)
            if wake and not _WORD.match(wake):
                raise WatchError(f"wake is one short lowercase word at the inlet "
                                 f"(gmail, mail-work), not {wake!r}")
            if renew and not wake:
                raise WatchError("renew keeps a sender knocking, so it goes with wake: "
                                 "the word that sender knocks on")
        else:
            if not _WORD.match(listen):
                raise WatchError(f"listen is one short lowercase word (whatsapp, "
                                 f"doorbell), not {listen!r}")
            if every:
                raise WatchError("a watch that listens has no every: it hears when "
                                 "something is sent")
            if wake or renew:
                raise WatchError("wake and renew are for a watch that looks; one that "
                                 "listens hears its word already")
        pick = recipe.check_pick(pick)
        when = recipe.check_when((when or {"any": True}) if listen else when, pick)
        stop = recipe.check_when(stop, pick) if stop else {}
        if stop and recipe.test_of(stop) not in recipe.EDGED:
            raise WatchError("stop is a test on what it sees now -- below, above, "
                             "contains, equals ... -- like {\"contains\": \"Landed\"}")
    except recipe.RecipeError as exc:
        raise WatchError(str(exc)) from None
    name = " ".join((name or "").split())
    if len(name) > 80:
        raise WatchError("a watch's name is a few words (80 letters at most)")
    asked = " ".join((asked or "").split())
    if len(asked) > 300:
        raise WatchError("asked is what the person said, in a sentence or two "
                         "(300 letters at most)")
    thing = " ".join((thing or "").split())
    if len(thing) > 40:
        raise WatchError("thing is what the pick takes, in a few words: \"the fare\", "
                         "\"the temperature\" (40 letters at most)")
    if not name:
        # The person knows a watch by what it looks at and when it tells
        # them, not by the tool it looks with.
        name = (f"{recipe.where_words(check)}: {recipe.thing_words(pick, thing)} "
                f"{recipe.when_words(when)}" if check else f"{listen} at the inlet")
        name = name if len(name) <= 80 else name[:79] + "…"
    place(zone)
    starts, ends = moment(starts, "starts", zone), moment(ends, "ends", zone)
    if starts and ends and from_iso(ends) <= from_iso(starts):
        raise WatchError("ends comes after starts")
    return {"name": name, "asked": asked, "thing": thing, "starts": starts, "ends": ends,
            "stop": stop, "zone": (zone or "").strip(),
            "check": check, "listen": listen, "pick": pick, "when": when,
            "every": every.strip() if check else "", "wake": wake, "renew": renew}


def create(store: Store, *, name: str = "", check=None, listen: str = "", pick=None,
           when=None, every: str = "", wake: str = "", renew=None, then: str = "",
           asked: str = "", thing: str = "", starts=None, ends=None, stop=None,
           zone: str = "", owner: str = LOCAL_OWNER,
           runner: str = "direct", agent: str = "", allow_tools: list[str] | None = None,
           wait: int = DEFAULT_WAIT, time_limit: int = DEFAULT_TIME_LIMIT,
           max_per_day: int = DEFAULT_MAX_PER_DAY, created_via: str = "cli",
           dvara=None) -> Watch:
    parts = checked(name=name, check=check, listen=listen, pick=pick, when=when,
                    every=every, wake=wake, renew=renew, asked=asked, thing=thing,
                    starts=starts, ends=ends, stop=stop, zone=zone)
    if parts["ends"] and from_iso(parts["ends"]) <= now_utc():
        raise WatchError(f"ends ({shown_at(parts['ends'], zone)}) has already passed")
    twin = same_as(store, owner, parts)
    if twin is not None:
        raise WatchError(
            f"{owner} already has a watch on exactly this: {twin.id} ({twin.name}) -- "
            f"{sentence(twin)}. Mend that one (its test, how often) instead of making "
            "a second; ask the person first")
    if runner not in RUNNERS:
        raise WatchError(f"runner is direct or dvara, not {runner!r}")
    if runner == "dvara":
        if not agent:
            raise WatchError("the Dvara road names the agent that looks and works: "
                             "--agent NAME, from Dvara's roster")
        if dvara is None:
            raise WatchError("the Dvara road needs PRAHARI_DVARA_URL and "
                             "PRAHARI_DVARA_TOKEN")
        if not dvara.actor_for(Watch(id="", owner=owner, name="")):
            raise WatchError("nobody to run as: add --as ACTOR, or set "
                             "PRAHARI_DVARA_ACTOR")
        if agent and agent not in dvara.agents():
            raise WatchError(f"dvara offers no agent {agent!r}")
    if not 1 <= int(max_per_day) <= 200:
        raise WatchError("max_per_day is between 1 and 200")
    if not 1 <= int(wait) <= 240:
        raise WatchError("wait is minutes, between 1 and 240")
    if not 30 <= int(time_limit) <= 7200:
        raise WatchError("time_limit is seconds, between 30 and 7200")
    grants = [str(g).strip() for g in allow_tools or [] if str(g).strip()]
    if len(store.watches(owner=owner)) >= max_watches():
        raise WatchError(f"{owner} has {max_watches()} watches already; delete one first")
    watch = Watch(id="", owner=owner, then=(then or "").strip(), runner=runner,
                  agent=agent, allow_tools=grants, wait=int(wait),
                  time_limit=int(time_limit), max_per_day=int(max_per_day),
                  created_via=created_via, **parts)
    if parts["listen"]:
        # An event is news by being sent: there is nothing to learn first.
        watch.looked = True
    else:
        # the first look, soon (it learns) -- or when it starts
        watch.next_at = parts["starts"] or iso(now_utc())
    if parts["renew"]:
        watch.renew_at = iso(now_utc())     # the sender is asked to start knocking
    return store.add(watch)


def _passed(stamp: str | None) -> bool:
    when = from_iso(stamp)
    return when is not None and when <= now_utc()


def span_words(watch: Watch) -> str:
    """When it looks, and when it stops by itself, in words."""
    said = ""
    start = from_iso(watch.starts)
    if start is not None and start > now_utc():
        said += f"; from {shown_at(watch.starts, watch.zone)}"
    if watch.ends:
        said += f"; until {shown_at(watch.ends, watch.zone)}"
    if watch.stop:
        said += (f"; stops once {recipe.thing_words(watch.pick, watch.thing)} "
                 f"{recipe.when_words(watch.stop)}")
    if watch.state == "ended":
        said += f"; ended {shown_at(watch.ended_at, watch.zone)}"
    return said


def same_as(store: Store, owner: str, parts: dict) -> Watch | None:
    """A watch of this person's that already looks at the same thing the
    same way: the same call and pick (or the same word at the inlet, heard
    the same way). ONE THING, ONE WATCH: two watches on one fare, told by
    two names nobody chose, is how a person stops knowing which is which."""
    for watch in store.watches(owner=owner):
        if watch.state == "ended":
            continue
        if parts["listen"]:
            if watch.listen == parts["listen"] and watch.pick == parts["pick"] \
                    and watch.when == parts["when"]:
                return watch
        elif watch.check == parts["check"] and watch.pick == parts["pick"]:
            return watch
    return None


def update(store: Store, watch_id: str, *, owner: str | None = None, **changes) -> Watch:
    """Mend a watch: its check, pick, test, how often, or what it does.

    A CHANGED RECIPE STARTS OVER. What the old one remembered -- its last
    value, what it had seen -- was picked by the old pick, so the next
    look learns again instead of comparing apples with what came before.

    HOW OFTEN IS NOT THE RECIPE. ``every`` alone changes when it looks, not
    what it looks for: what it remembered stays, and the next look comes
    at the sooner of the one already due and now plus the new step.

    KEEP IS ONE WORD FOR GOING ON. ``keep`` stops the 30-day question for
    another 30 days, and brings an ended watch back (its old end, passed,
    is dropped); so does a new ``ends`` or ``starts`` for an ended one.
    """
    watch = find(store, watch_id, owner=owner)
    allowed = {"name", "asked", "thing", "check", "pick", "when", "every", "then",
               "allow_tools", "max_per_day", "wake", "renew", "starts", "ends", "stop",
               "keep"}
    unknown = [k for k in changes if k not in allowed]
    if unknown:
        raise WatchError(f"can't change {', '.join(unknown)}; can change: "
                         f"{', '.join(sorted(allowed))}")
    given = {k: v for k, v in changes.items() if v is not None}
    recipe_keys = {"check", "pick", "when"} | ({"every"} if {"check", "pick", "when"}
                                                & set(given) else set())
    parts = checked(
        name=given.get("name", watch.name),
        check=given.get("check", watch.check) if not watch.listen else None,
        listen=watch.listen, pick=given.get("pick", watch.pick),
        when=given.get("when", watch.when), every=given.get("every", watch.every),
        wake=given.get("wake", watch.wake), renew=given.get("renew", watch.renew),
        asked=given.get("asked", watch.asked), thing=given.get("thing", watch.thing),
        starts=given.get("starts", watch.starts),
        ends=given.get("ends", watch.ends) if not (given.get("keep") and "ends" not in given
                                                   and _passed(watch.ends)) else None,
        stop=given.get("stop", watch.stop), zone=watch.zone)
    if "ends" in given and _passed(parts["ends"]):
        raise WatchError(f"ends ({shown_at(parts['ends'], watch.zone)}) has already passed")
    fields: dict = {"name": parts["name"], "asked": parts["asked"], "thing": parts["thing"],
                    "wake": parts["wake"], "renew": parts["renew"], "starts": parts["starts"],
                    "ends": parts["ends"], "stop": parts["stop"]}
    if given.get("keep"):
        fields.update(kept_at=iso(now_utc()), still_asked_at=None)
    if watch.state == "ended" and {"keep", "ends", "starts"} & set(given):
        fields.update(state="active", ended_at=None, paused_because="",
                      kept_at=iso(now_utc()), still_asked_at=None)
        if not watch.listen:
            fields["next_at"] = iso(now_utc())
    if "renew" in given:
        fields["renew_at"] = iso(now_utc()) if parts["renew"] else None
    if recipe_keys & set(given):
        fields.update(check=parts["check"], pick=parts["pick"], when=parts["when"],
                      every=parts["every"], armed=True, last_value="", trouble=0,
                      looked=bool(watch.listen))
        if not watch.listen:
            fields["next_at"] = iso(now_utc())
        if watch.state == "paused" and watch.paused_because.startswith(("broken", "failed")):
            fields.update(state="active", paused_because="")
    if "every" in given and not recipe_keys & set(given) and not watch.listen:
        fields["every"] = parts["every"]
        soon = now_utc() + recipe.every(parts["every"])
        due = from_iso(watch.next_at)
        fields["next_at"] = iso(min(due, soon) if due else soon)
    if "then" in given:
        fields["then"] = str(given["then"]).strip()
    if "allow_tools" in given:
        grants = given["allow_tools"]
        if not isinstance(grants, list):
            raise WatchError("allow_tools is a list of tool names or grants")
        fields["allow_tools"] = [str(g).strip() for g in grants if str(g).strip()]
    if "max_per_day" in given:
        if not 1 <= int(given["max_per_day"]) <= 200:
            raise WatchError("max_per_day is between 1 and 200")
        fields["max_per_day"] = int(given["max_per_day"])
    if "starts" in given and not watch.listen and fields.get("state", watch.state) == "active":
        fields.setdefault("next_at", iso(now_utc()))
    start = from_iso(parts["starts"])
    if start is not None and start > now_utc() and "next_at" in fields:
        fields["next_at"] = parts["starts"]     # nothing is looked at before it starts
    store.update(watch.id, **fields)
    if recipe_keys & set(given):
        store.forget_seen(watch.id)
    return store.get(watch.id)


def pause(store: Store, watch_id: str, owner: str | None = None,
          because: str = "paused by you") -> Watch:
    watch = find(store, watch_id, owner=owner)
    store.update(watch.id, state="paused", paused_because=because)
    return store.get(watch.id)


def resume(store: Store, watch_id: str, owner: str | None = None) -> Watch:
    watch = find(store, watch_id, owner=owner)
    if watch.state == "ended":
        return update(store, watch.id, owner=owner, keep=True)
    store.update(watch.id, state="active", paused_because="", trouble=0,
                 next_at=None if watch.listen else iso(now_utc()))
    return store.get(watch.id)


def allow(store: Store, watch_id: str, grants: list[str],
          owner: str | None = None) -> Watch:
    watch = find(store, watch_id, owner=owner)
    more = [str(g).strip() for g in grants if str(g).strip()]
    if not more:
        raise WatchError("name the tool to allow")
    store.update(watch.id, allow_tools=list(dict.fromkeys([*watch.allow_tools, *more])))
    return store.get(watch.id)


def remove(store: Store, watch_id: str, owner: str | None = None) -> Watch:
    watch = find(store, watch_id, owner=owner)
    store.delete(watch.id)
    return watch


def find(store: Store, watch_id: str, owner: str | None = None) -> Watch:
    """A watch by its id or the first letters of one."""
    wanted = (watch_id or "").strip()
    if not wanted:
        raise WatchError("which watch? give its id")
    found = [w for w in store.watches(owner=owner) if w.id.startswith(wanted)]
    if not found:
        raise WatchError(f"no watch {wanted}")
    if len(found) > 1:
        raise WatchError(f"{wanted} could be {', '.join(w.id for w in found)}: give "
                         "more of the id")
    return found[0]


def sentence(watch: Watch) -> str:
    said = recipe.sentence(watch.check, watch.listen, watch.pick, watch.when, watch.every,
                           watch.thing)
    return said + push_words(watch.wake, watch.renew) + span_words(watch)


def push_words(wake: str, renew: dict | None) -> str:
    """What a knock does to a watch that looks, in words."""
    if not wake:
        return ""
    said = f"; and at once whenever {wake} knocks at the inlet"
    if renew:
        said += f" (kept knocking by {renew.get('tool', '?')}, once a day)"
    return said


def card(watch: Watch, store: Store | None = None) -> dict:
    """A watch as a page or a program reads it: itself, in words, and its
    last look."""
    data = watch.as_dict()
    data["sentence"] = sentence(watch)
    data["does"] = (f"Then it asks the agent: {watch.then}" if watch.then
                    else "You get a line saying what it saw; no model is asked")
    if store is not None:
        last = store.looks(watch.id, limit=1)
        data["last_look"] = last[0].as_dict() if last else None
        day = now_utc() - timedelta(days=1)
        data["fired_today"] = store.fired_since(watch.id, day)
    return data


#: How much of what the tool said a preview shows, to write a pick against.
RESULT_SHOWN = 1500


def preview(caller, *, check=None, listen: str = "", pick=None, when=None,
            every: str = "", sample=None, agent: str = "", runner: str = "direct",
            owner: str = LOCAL_OWNER, wake: str = "", renew=None, thing: str = "",
            starts=None, ends=None, stop=None, store: Store | None = None,
            zone: str = "") -> dict:
    """Try a recipe ONCE, before anybody said yes: look (only with a tool
    that reads -- nothing is granted yet), pick, and say what it saw.

    WRITTEN FOR THE ONE WRITING THE PICK. The answer carries the start of
    what the tool said, so a model whose pick found nothing can see why
    and write a better one, and the sentence the person will be asked to
    accept. A watch that listens is tried on ``sample``, an event like
    the one the sender will send."""
    import json as _json

    parts = checked(check=check, listen=listen, pick=pick, when=when, every=every,
                    wake=wake, renew=renew, thing=thing, starts=starts, ends=ends, stop=stop,
                    zone=zone)
    span = Watch(id="", owner=owner, name="", pick=parts["pick"], thing=parts["thing"],
                 starts=parts["starts"], ends=parts["ends"], stop=parts["stop"],
                 zone=parts["zone"])
    out: dict = {"sentence": recipe.sentence(parts["check"], parts["listen"],
                                             parts["pick"], parts["when"], parts["every"],
                                             parts["thing"])
                 + push_words(parts["wake"], parts["renew"]) + span_words(span),
                 "looked": False}
    twin = same_as(store, owner, parts) if store is not None else None
    if twin is not None:
        # Said before anything is looked at: the person is asked about the
        # watch they have, not a second one.
        out["twin"] = twin.id
        out["said"] = (f"{owner} already has a watch on exactly this: {twin.id} "
                       f"({twin.name}) -- {sentence(twin)}. Offer to mend that one "
                       "instead of making a second.")
        return out
    if parts["listen"]:
        if sample is None:
            out["said"] = ("Nothing to try it on yet: give a sample of what the sender "
                           "will send (a JSON object), or send one to the inlet.")
            return out
        text = _json.dumps(sample if isinstance(sample, dict) else {"text": str(sample)},
                           sort_keys=True, ensure_ascii=False)
    else:
        probe = Watch(id="", owner=owner, name="", check=parts["check"], agent=agent,
                      runner=runner)
        called = caller.call(probe, granted=False)
        if not called.ok:
            out["said"] = (f"The look didn't work: {called.detail}"
                           if "not read-only" not in called.detail else
                           f"{parts['check']['tool']} isn't a tool that only reads, so it "
                           "can't be tried before the person accepts it; every look will "
                           "run exactly this call once they do.")
            out["result"] = ""
            return out
        text = called.text
        out["looked"] = True
    out["result"] = text[:RESULT_SHOWN] + ("…" if len(text) > RESULT_SHOWN else "")
    picked = recipe.apply(parts["pick"], text)
    out["found"] = picked.found
    if not picked.found:
        out["said"] = ("The pick found nothing in what the tool said (see result): "
                       "change the pick before making this watch.")
        return out
    out["value"] = picked.shown()
    out["items"] = [i.line for i in picked.items[:5]]
    test = recipe.test_of(parts["when"])
    if test in recipe.EDGED:
        now_true = bool(recipe.holds(parts["when"], picked))
        out["holds"] = now_true
        out["said"] = (f"It sees {picked.shown()} now: that already matches, so the "
                       "person would hear at once." if now_true else
                       f"It sees {picked.shown()} now: no match yet.")
    elif picked.items or recipe.pick_kind(parts["pick"]) in ("items", "items_json"):
        out["said"] = (f"It sees {len(picked.items)} item(s) now; the first look "
                       "remembers them, and only ones after that are news.")
    else:
        out["said"] = (f"It sees {picked.shown()!r} now; the first look remembers it, "
                       "and a change after that is news.")
    return out
