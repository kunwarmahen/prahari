"""Making, changing and showing indriyas -- Prahari's shared readings.

An indriya (इन्द्रिय, "a sense": the faculty that takes in the world, as
eye, ear and touch do) is the looking half of a watch, on its own: one
tool call that reads, a pick, how often. It keeps the value it last took,
with a time on it, and a short history. It never decides anything and
never tells anyone anything; watches that ``sense`` it do that.

WHY IT IS SEPARATE. Two watches on one number -- heat the guestroom below
60, cool it above 70 -- each called the weather service on their own:
twice the calls, twice the chance of being refused, and for a moment two
answers that disagree. With one indriya there is one call, one value, and
every watch, agent or page that wants the outside temperature reads that.

ONE NAME PER PERSON. An indriya is called by one short word
(``outside-temp``), because an agent asks for it by name and a person
types it. A person's own indriya wins over a house one of the same name.

SHARING SHARES THE VALUE, NOT THE ACCOUNTS. An indriya looks with its
owner's accounts, on its owner's road. ``share = "house"`` lets anyone's
watches and agents read what it read; it never lets them call anything
as the owner. It starts as ``mine``: outside temperature is fine to share,
unread mail from the bank is a choice somebody makes on purpose.

A SENSING WATCH IS HANDED THE WHOLE ANSWER, so it may pick something else
out of it (the humidity from the same weather call); with no pick of its
own it takes the indriya's.

AN INDRIYA IN USE IS NOT REMOVED. ``remove`` says which watches sense it:
pulling a reading out from under a watch would leave it quiet for ever,
which looks exactly like "nothing happened".

ONE CALL IS ONE READING, BY ITSELF. A watch made on exactly the call an
indriya already makes senses it instead (``reader_for``, used by
``watches.create``), and says so; one asked to look more often speeds up
the person's own indriya to its pace -- never someone else's, whose
reading is theirs to set, and never below the five-minute floor (or the
site's own, floors.py). Watches
made before the indriya are moved onto it only on the person's word
(``prahari edit ID --sense NAME``, or ``indriya add --from ID --move``),
because a watch they agreed to is theirs.

FRESH ON ASKING, NOT ON EVERY ASK. A reader may say how old is too old
(``fresh``, ``max_age``): an older value is read again then and there --
but not sooner than ``FRESH_FLOOR`` after the last reading, whoever made
it, so a chat asking in a loop cannot turn a fifteen-minute reading into
a call a second. A fresh read only reads: it is not handed to the
watches (a watch that fires might start a turn, and a reader's question
would wait minutes on it), is not counted against the indriya, and does
not move its clock. The next reading on the clock decides as always.

PUSHED IN, WHEN THE THING CAN SAY ITSELF. A Home Assistant thermometer
knows the guestroom's temperature better than any page Prahari could
read. A ``pushed`` indriya makes no call: its value is sent to
``POST /inlet/indriya/NAME`` with the person's own inlet key, picked
(``{"value": ...}`` by default), kept, and handed to its watches as a
reading the clock took would be. A KNOCK REACHES ONLY ITS OWN: the name
is found among the indriyas of the key's person, as a knock is heard
only by their watches. AND SILENCE IS SAID: its ``every`` is how often a
value is expected at least; nothing by then is a failed reading, said on
each watch and counted, three in a row pause it and tell its owner. An
automation that broke must not look like a temperature that never moved.

AND SLOWS BACK DOWN WHEN THE NEED GOES. Each watch that sped a reading
up keeps how often it asked (``wants_every``), and the reading keeps how
often its owner set it (``own_every``). When such a watch is removed,
ends, or goes back to looking itself, the reading comes back to the
slowest pace that still serves everyone left: the owner's own, or the
fastest wish still standing (``settle``). The owner's ``--every`` is the
last word: wishes faster than it are lowered to it. A reading made
before its owner's pace was kept is not slowed, since nobody knows what
that pace was; its first speed-up remembers it.

A SITE MAY ASK FOR MORE THAN FIVE MINUTES. A floor kept for the site
(floors.py) holds a reading's pace, its speed-ups and its fresh reads.

MADE FROM A REVIEW TAKEN BACK, IT STOPS. A reading made from a
marketplace template keeps that text's sha256; when Vidhi believes a
take-back of its review, the clock pauses it (``TAKEN_BACK`` heads the
reason) and tells its owner. ``resume`` refuses it; mending its call or
pick makes it the owner's own reading, and it runs again.

UNUSED, IT STOPS. Every reading a watch decides on, and every reader
that asks for the value, marks it used (``used_at``). Thirty days with
neither and the clock pauses it and tells its owner, as a watch with no
end asks once a month: a call every fifteen minutes with someone's
accounts, for nothing, should not run for ever unnoticed.
"""

from __future__ import annotations

import os
import re
from datetime import timedelta

from prahari import recipe
from prahari.store import (INDRIYA_SHARES, RUNNERS, Indriya, Store, Watch, from_iso, iso,
                           now_utc)
from prahari.watches import LOCAL_OWNER, WatchError, _call

_NAME = re.compile(r"^[a-z][a-z0-9-]{1,39}$")

#: How often an indriya reads when nobody says (it is a shared thing, so a
#: little more often than a watch's hour).
DEFAULT_EVERY = "15m"
#: How often a pushed indriya expects a value, when nobody says.
DEFAULT_PUSHED_EVERY = "1h"
#: What a pushed value is picked by, when nobody says: {"value": ...}.
DEFAULT_PUSHED_PICK = {"json": "value"}
#: A fresh read is not made sooner than this after the last reading.
FRESH_FLOOR = recipe.MIN_EVERY
#: Unused this long (no watch decided on it, nobody asked), it pauses.
UNUSED = timedelta(days=30)
#: How a pause for a review taken back begins (resume refuses it).
TAKEN_BACK = "review taken back"



def max_indriyas() -> int:
    try:
        return max(1, int(os.environ.get("PRAHARI_MAX_INDRIYAS", "30")))
    except ValueError:
        return 30


def checked(*, name: str, check=None, pick=None, every: str = "", thing: str = "",
            share: str = "mine", pushed: bool = False) -> dict:
    """An indriya's parts, checked together; WatchError in words."""
    name = (name or "").strip().lower()
    if not _NAME.match(name):
        raise WatchError(f"an indriya's name is one short lowercase word, letters, "
                         f"digits and dashes (outside-temp, btc-price), not {name!r}")
    if pushed:
        if check:
            raise WatchError("a pushed indriya makes no call: its value is sent in "
                             "(POST /inlet/indriya/NAME); leave out the check")
        check = {}
        pick = pick or DEFAULT_PUSHED_PICK
        every = every or DEFAULT_PUSHED_EVERY
    else:
        check = _call(check, "check")
        if not check:
            raise WatchError("an indriya needs a check -- {\"tool\": NAME, \"args\": "
                             "{...}} -- the one call it reads with, or pushed: its value "
                             "sent in")
    try:
        pick = recipe.check_pick(pick)
        recipe.every(every or DEFAULT_EVERY)
    except recipe.RecipeError as exc:
        raise WatchError(str(exc)) from None
    thing = " ".join((thing or "").split())
    if len(thing) > 40:
        raise WatchError("thing is what it reads, in a few words: \"the outside "
                         "temperature\" (40 letters at most)")
    share = (share or "mine").strip().lower()
    if share not in INDRIYA_SHARES:
        raise WatchError(f"share is mine or house, not {share!r}")
    return {"name": name, "check": check, "pick": pick,
            "every": (every or DEFAULT_EVERY).strip(), "thing": thing, "share": share}


def create(store: Store, *, name: str, check=None, pick=None, every: str = "",
           thing: str = "", share: str = "mine", owner: str = LOCAL_OWNER,
           runner: str = "direct", agent: str = "", created_via: str = "cli",
           dvara=None, pushed: bool = False, template_sha256: str = "") -> Indriya:
    parts = checked(name=name, check=check, pick=pick, every=every, thing=thing,
                    share=share, pushed=pushed)
    if any(i.name == parts["name"] for i in store.indriyas(owner=owner)):
        raise WatchError(f"{owner} already has an indriya called {parts['name']}; "
                         "mend that one, or choose another name")
    twin = next((i for i in store.indriyas(owner=owner)
                 if not pushed and i.check == parts["check"]), None)
    if twin is not None:
        raise WatchError(f"{owner}'s indriya {twin.name} already reads with exactly this "
                         f"call; sense that one (and pick from its answer) instead of "
                         "calling twice")
    if runner not in RUNNERS:
        raise WatchError(f"runner is direct or dvara, not {runner!r}")
    if runner == "dvara" and not pushed:
        if not agent:
            raise WatchError("the Dvara road names the agent that reads: --agent NAME")
        if dvara is None:
            raise WatchError("the Dvara road needs PRAHARI_DVARA_URL and "
                             "PRAHARI_DVARA_TOKEN")
        if not dvara.actor_for(Watch(id="", owner=owner, name="")):
            raise WatchError("nobody to read as: add --as ACTOR, or set "
                             "PRAHARI_DVARA_ACTOR")
    if len(store.indriyas(owner=owner)) >= max_indriyas():
        raise WatchError(f"{owner} has {max_indriyas()} indriyas already; remove one first")
    # a pushed one's first deadline is one every from now; a read one reads now
    if not pushed:
        from prahari import floors
        floors.check_pace(store, parts["check"], parts["every"], parts["name"])
    first = (now_utc() + recipe.every(parts["every"])) if pushed else now_utc()
    made = Indriya(id="", owner=owner, runner="direct" if pushed else runner,
                   agent=agent, created_via=created_via, next_at=iso(first),
                   pushed=pushed, own_every=parts["every"],
                   template_sha256=template_sha256, **parts)
    return store.add_indriya(made)


def visible(store: Store, person: str | None, home: set[str] | None = None) -> list[Indriya]:
    """The indriyas a person may read: their own, then the house's. None: all."""
    if person is None:
        return store.indriyas()
    names = {person} | (set(home or ()) if person in (home or ()) else set())
    own = [i for i in store.indriyas() if i.owner in names]
    house = [i for i in store.indriyas() if i.owner not in names and i.share == "house"]
    return own + house


def find(store: Store, wanted: str, person: str | None = None,
         home: set[str] | None = None, own_only: bool = False) -> Indriya:
    """An indriya by its name, its id, or the first letters of its id --
    among those ``person`` may read (``own_only``: may change)."""
    wanted = (wanted or "").strip()
    if not wanted:
        raise WatchError("which indriya? give its name")
    pool = visible(store, person, home)
    if own_only and person is not None:
        names = {person} | (set(home or ()) if person in (home or ()) else set())
        pool = [i for i in pool if i.owner in names]
    by_name = [i for i in pool if i.name == wanted.lower()]
    if by_name:
        return by_name[0]           # own first: visible() lists them first
    by_id = [i for i in pool if i.id.startswith(wanted)]
    if not by_id:
        raise WatchError(f"no indriya {wanted}")
    if len(by_id) > 1:
        raise WatchError(f"{wanted} could be {', '.join(i.id for i in by_id)}: give "
                         "its name")
    return by_id[0]


def update(store: Store, indriya_id: str, **changes) -> Indriya:
    """Mend an indriya: its call, pick, how often, what it reads, who sees it.

    A NEW CALL OR PICK STARTS ITS SENSING WATCHES OVER, as a mended watch
    does: what they remembered was picked from the old answer."""
    current = store.get_indriya(indriya_id)
    if current is None:
        raise WatchError(f"no indriya {indriya_id}")
    allowed = {"check", "pick", "every", "thing", "share"}
    unknown = [k for k in changes if k not in allowed]
    if unknown:
        raise WatchError(f"can't change {', '.join(unknown)}; can change: "
                         f"{', '.join(sorted(allowed))}")
    given = {k: v for k, v in changes.items() if v is not None}
    if current.pushed and given.get("check"):
        raise WatchError(f"{current.name} is pushed in: it has no call to change")
    parts = checked(name=current.name, check=given.get("check", current.check),
                    pick=given.get("pick", current.pick),
                    every=given.get("every", current.every),
                    thing=given.get("thing", current.thing),
                    share=given.get("share", current.share), pushed=current.pushed)
    fields = {k: parts[k] for k in ("check", "pick", "every", "thing", "share")}
    if not current.pushed and {"check", "every"} & set(given):
        from prahari import floors
        floors.check_pace(store, parts["check"], parts["every"], current.name)
    if "every" in given:
        # THE OWNER'S WORD IS THE LAST: it is the pace to come back to, and
        # a watch's wish faster than it is lowered to it
        fields["own_every"] = parts["every"]
        new = recipe.every(parts["every"])
        for watch in store.watches(sense=current.id):
            if watch.wants_every and recipe.every(watch.wants_every) < new:
                store.update(watch.id, wants_every=parts["every"])
    if {"check", "pick"} & set(given):
        fields.update(value="", stored="", read_at=None, trouble=0,
                      next_at=iso(now_utc() + recipe.every(parts["every"])
                                  if current.pushed else now_utc()))
        if current.state == "paused" and current.paused_because.startswith(
                ("broken", "failed", TAKEN_BACK)):
            fields.update(state="active", paused_because="")
        # mended, it is no longer the reviewed text: the owner's own
        fields["template_sha256"] = ""
        for watch in store.watches(sense=current.id):
            store.update(watch.id, looked=False, last_value="", armed=True, trouble=0)
            store.forget_seen(watch.id)
    elif "every" in given:
        soon = now_utc() + recipe.every(parts["every"])
        due = from_iso(current.next_at)
        fields["next_at"] = iso(min(due, soon) if due else soon)
    if parts["share"] == "mine" and current.share == "house":
        others = [w for w in store.watches(sense=current.id) if w.owner != current.owner]
        if others:
            raise WatchError(f"{current.name} is sensed by other people's watches "
                             f"({', '.join(w.id for w in others)}); they'd go quiet. "
                             "Ask them to remove those first")
    store.update_indriya(current.id, **fields)
    return store.get_indriya(current.id)


def from_watch(store: Store, watch: Watch, *, name: str, share: str = "mine",
               every: str = "", move: bool = False, home: set[str] | None = None,
               created_via: str = "cli", dvara=None,
               thing: str = "") -> tuple[Indriya, list[Watch], list[Watch]]:
    """An indriya made from a watch's own call: its check, pick, thing,
    road and how often (or ``every``). Returns it, the watches moved onto
    it (``move``: every watch of this person's that makes the very same
    call), and those that could be (not ``move``) -- the person decides."""
    from prahari import watches as watches_module

    if not watch.check:
        raise WatchError(f"{watch.id} makes no call of its own (it "
                         + ("senses an indriya" if watch.sense else "listens")
                         + "), so there is nothing to make a reading from")
    # ADDED AGAIN WITH --move IS THE MOVE. The first add listed the watches
    # and said to add again with --move; the reading it made is the one,
    # when it makes the same call -- not "already has one called that".
    kept = next((i for i in store.indriyas(owner=watch.owner)
                 if i.name == (name or "").strip().lower()), None)
    if kept is not None and kept.check == watch.check and move:
        made = kept
    else:
        made = create(store, name=name, check=watch.check, pick=watch.pick,
                      every=every or watch.every or DEFAULT_EVERY,
                      thing=thing or watch.thing, share=share, owner=watch.owner,
                      runner=watch.runner, agent=watch.agent, created_via=created_via,
                      dvara=dvara)
    same = [w for w in store.watches(owner=watch.owner)
            if w.check == watch.check and w.state != "ended"]
    if not move:
        return made, [], same
    moved = [watches_module.update(store, w.id, sense=made.id, home=home) for w in same]
    return store.get_indriya(made.id) or made, moved, []


def for_knock(store: Store, name: str, people: set[str] | None) -> Indriya:
    """The pushed indriya a knock on ``/inlet/indriya/NAME`` is for: among
    the key's people only, so another person's name answers the same as
    one that doesn't exist."""
    wanted = (name or "").strip().lower()
    for indriya in store.indriyas():
        if indriya.name == wanted and (people is None or indriya.owner in people):
            if not indriya.pushed:
                raise WatchError(f"{indriya.name} reads on its own; nothing is pushed "
                                 "to it (make one with --pushed)")
            return indriya
    raise WatchError(f"no indriya {wanted} to push to, for this key")


def reader_for(store: Store, owner: str, check: dict,
               home: set[str] | None = None) -> Indriya | None:
    """The indriya that already makes exactly this call, among those this
    person may read: their own first, then the house's."""
    for indriya in visible(store, owner, home):
        if indriya.check == check:
            return indriya
    return None


def is_own(indriya: Indriya, person: str, home: set[str] | None = None) -> bool:
    names = {person} | (set(home or ()) if person in (home or ()) else set())
    return indriya.owner in names


def keep_up(store: Store, indriya: Indriya, every: str) -> str:
    """The FASTEST NEED: a watch asked to look every ``every`` now goes by
    this indriya, so it reads at least that often -- but not faster than
    its site's floor. Returns what changed, in words ("" for nothing)."""
    from prahari import floors

    asked = recipe.every(every)
    every = floors.at_floor(store, indriya.check, every.strip())
    wanted, now = recipe.every(every), recipe.every(indriya.every)
    capped = ""
    if wanted > asked:
        _, floor = floors.floor_for(store, indriya.check)
        capped = (f"{indriya.name} reads no more often than every "
                  f"{recipe.duration_words(wanted)}, not every "
                  f"{recipe.duration_words(asked)}: {floors.words(floor)}")
    if not indriya.own_every:
        # the pace to come back to, remembered before it is first changed
        store.update_indriya(indriya.id, own_every=indriya.every)
    if wanted >= now:
        return capped
    store.update_indriya(indriya.id, every=every)
    due = from_iso(indriya.next_at)
    soon = now_utc() + wanted
    if due is None or due > soon:
        store.update_indriya(indriya.id, next_at=iso(soon))
    said = (f"{indriya.name} now reads every {recipe.duration_words(wanted)} (it read "
            f"every {recipe.duration_words(now)}), as often as this watch asked")
    return f"{said}; {capped}" if capped else said


def settle(store: Store, indriya: Indriya) -> str:
    """SLOWER WHEN THE NEED GOES. The slowest pace that still serves
    everyone: the owner's own, or the fastest wish of a watch still on it
    (removed and ended watches don't count; paused ones do, since they
    come back). Only ever slows; speeding up is ``keep_up``'s. Returns what
    changed, in words ("" for nothing)."""
    from prahari import floors

    current = store.get_indriya(indriya.id)
    if current is None or current.pushed or not current.own_every:
        return ""
    wishes = [w.wants_every for w in store.watches(sense=current.id)
              if w.state != "ended" and w.wants_every]
    target = min([current.own_every, *wishes], key=recipe.every)
    target = floors.at_floor(store, current.check, target)
    before = recipe.every(current.every)
    if recipe.every(target) <= before:
        return ""
    store.update_indriya(current.id, every=target)
    why = ("as you set it" if target == current.own_every
           else "as often as the fastest watch still on it asks")
    return (f"{current.name} now reads every "
            f"{recipe.duration_words(recipe.every(target))} (it read every "
            f"{recipe.duration_words(before)}), {why}")


def used(store: Store, indriya: Indriya) -> None:
    """A reader asked for its value: it is in use."""
    store.update_indriya(indriya.id, used_at=iso(now_utc()))


def unused_for(indriya: Indriya, now) -> timedelta:
    since = from_iso(indriya.used_at) or from_iso(indriya.created_at) or now
    return now - since


def max_age(raw) -> timedelta | None:
    """How old is too old, as a reader says it: "5m", "1h", "0" (always
    fresh, up to the floor). None for not said."""
    if raw is None or str(raw).strip() == "":
        return None
    text = str(raw).strip().lower()
    if text in ("0", "0m", "now"):
        return timedelta(0)
    match = re.match(r"^(\d{1,4})\s*(m|min|minutes?|h|hours?|d|days?)$", text)
    if not match:
        raise WatchError(f"max_age is how old is too old, like 5m, 1h or 0 -- not {raw!r}")
    count, unit = int(match.group(1)), match.group(2)[0]
    return timedelta(**{"m": {"minutes": count}, "h": {"hours": count},
                        "d": {"days": count}}[unit])


def fresh(store: Store, caller, indriya: Indriya, too_old: timedelta | None) -> tuple[Indriya, str]:
    """Its value, read again first when it is older than ``too_old`` --
    and the floor allows. Returns the indriya as it is now and a line
    saying what happened ("" when the kept value was fresh enough)."""
    from prahari.clock import take

    used(store, indriya)
    if too_old is None:
        return store.get_indriya(indriya.id) or indriya, ""
    now = now_utc()
    read = from_iso(indriya.read_at)
    if read is not None and now - read <= too_old:
        return indriya, ""
    if indriya.pushed:
        return indriya, (f"not read again: {indriya.name} is pushed in by its sender, "
                         "so this is the latest value that came")
    if indriya.state != "active":
        return indriya, (f"not read again: {indriya.name} is paused "
                         f"({indriya.paused_because or 'by hand'})")
    from prahari import floors

    last = store.readings(indriya.id, limit=1)
    tried = from_iso(last[0].at) if last else None
    floor, site = floors.floor_for(store, indriya.check)
    floor = max(floor, FRESH_FLOOR)
    if tried is not None and now - tried < floor:
        return indriya, (f"not read again: it was read {age_words(last[0].at)}, and a "
                         f"reading is not made again within {_span(floor)}"
                         + (f" ({floors.words(site)})" if site else ""))
    reading, _ = take(caller, indriya, now)
    reading.why = f"Asked for fresh by a reader. {reading.why}"
    reading.came_by = "asked"
    store.add_reading(reading)
    if reading.outcome != "read":
        return indriya, (f"read again, but it did not read ({reading.outcome}: "
                         f"{reading.detail or reading.why}); the value below is the kept one")
    store.update_indriya(indriya.id, value=reading.value, stored=reading.stored,
                         read_at=reading.at)
    return store.get_indriya(indriya.id) or indriya, "read again just now, as asked"


def _span(step: timedelta) -> str:
    """"5 minutes", "an hour": a span after "within"."""
    words = recipe.duration_words(step)
    return words if words[0].isdigit() else ("an " if words == "hour" else "a ") + words


def pause(store: Store, indriya: Indriya, because: str = "paused by you") -> Indriya:
    store.update_indriya(indriya.id, state="paused", paused_because=because)
    return store.get_indriya(indriya.id)


def resume(store: Store, indriya: Indriya) -> Indriya:
    if indriya.state == "paused" and indriya.paused_because.startswith(TAKEN_BACK):
        raise WatchError(f"{indriya.name} is paused: {indriya.paused_because}. It stays "
                         f"paused as it was; mend it (prahari indriya edit {indriya.name}) "
                         "to make it your own, or remove it")
    # used from now: a reading paused as unused gets its month again
    store.update_indriya(indriya.id, state="active", paused_because="", trouble=0,
                         next_at=iso(now_utc()), used_at=iso(now_utc()))
    return store.get_indriya(indriya.id)


def remove(store: Store, indriya: Indriya) -> Indriya:
    using = store.watches(sense=indriya.id)
    if using:
        raise WatchError(f"{indriya.name} is sensed by "
                         + ", ".join(f"{w.id} ({w.name})" for w in using)
                         + ": remove those watches first, or they would go quiet for "
                         "ever")
    store.delete_indriya(indriya.id)
    return indriya


def age_words(stamp: str | None) -> str:
    """How long ago, in a person's words: "4 min ago", "2 h ago"."""
    when = from_iso(stamp)
    if when is None:
        return "not read yet"
    gone = max(timedelta(0), now_utc() - when)
    minutes = int(gone.total_seconds() // 60)
    if minutes < 1:
        return "just now"
    if minutes < 120:
        return f"{minutes} min ago"
    if minutes < 48 * 60:
        return f"{minutes // 60} h ago"
    return f"{minutes // 1440} days ago"


def sentence(indriya: Indriya) -> str:
    """The indriya in words: what it reads, where, and how often."""
    if indriya.pushed:
        thing = recipe.thing_words(indriya.pick, indriya.thing)
        return (f"keeps {thing}, pushed in to the inlet as {indriya.name} (a value "
                f"expected at least every "
                f"{recipe.duration_words(recipe.every(indriya.every))})"
                + ("; shared with the house" if indriya.share == "house" else ""))
    where = recipe.where_words(indriya.check)
    tool = indriya.check.get("tool", "?")
    look = (f"looks with {where}" if where.startswith(tool)
            else f"looks at {where} (with {tool})")
    thing = recipe.thing_words(indriya.pick, indriya.thing)
    return (f"reads {thing} every {recipe.duration_words(recipe.every(indriya.every))}: "
            f"{look}" + ("; shared with the house" if indriya.share == "house" else ""))


def reading_line(indriya: Indriya) -> str:
    """Its value now, in a line: "outside-temp: 58 (4 min ago)"."""
    if indriya.state != "active":
        state = f" [{indriya.state}: {indriya.paused_because}]"
    else:
        state = ""
    if not indriya.read_at:
        return f"{indriya.name}: not read yet{state}"
    return f"{indriya.name}: {indriya.value} ({age_words(indriya.read_at)}){state}"


def card(indriya: Indriya, store: Store | None = None) -> dict:
    """An indriya as a page or a program reads it."""
    data = indriya.as_dict()
    data["sentence"] = sentence(indriya)
    data["age"] = age_words(indriya.read_at)
    if store is not None:
        data["sensed_by"] = [{"id": w.id, "name": w.name, "owner": w.owner}
                             for w in store.watches(sense=indriya.id)]
        last = store.readings(indriya.id, limit=1)
        data["last_reading"] = last[0].as_dict() if last else None
    return data


#: A look made before looks said which reading they judged is matched to
#: the reading just before it, no further back than this. A reading's
#: looks start when its call is done -- a minute or more through Dvara --
#: and one indriya never reads twice at once, so the reading just before
#: a look is the one it judged.
MATCH_WINDOW = timedelta(minutes=15)

#: How a reading came, in words.
CAME_WORDS = {"clock": "on its clock", "now": "read now, by hand",
              "asked": "asked for fresh by a reader", "pushed": "sent in",
              "silence": "nothing came in time"}


def history(store: Store, indriya: Indriya, limit: int = 20,
            people: set[str] | None = None) -> list[dict]:
    """Its readings, newest first, each with what every watch decided on
    it -- the indriya's answer to "what happened?", as a watch's looks
    are for a watch.

    ANOTHER PERSON'S WATCHES ARE COUNTED, NOT SHOWN. A house reading is
    sensed by other people's watches too; ``people`` (None: anyone's, for
    the computer's own page) sees its own by name and the rest as a
    number, since what someone else watches for is theirs."""
    found = store.readings(indriya.id, limit=max(1, min(int(limit), 500)))
    decided = store.decided_on([r.id for r in found])
    names = {w.id: w for w in store.watches(sense=indriya.id)}
    guessed = _matched_by_time(store, found, decided, list(names))
    out = []
    for reading in found:
        row = reading.as_dict()
        row["came_words"] = CAME_WORDS.get(reading.came_by, reading.came_by)
        mine, others = [], 0
        by_time = guessed.get(reading.id, [])
        row["matched_by_time"] = bool(by_time)
        for look in decided.get(reading.id, []) or by_time:
            watch = names.get(look.watch) or store.get(look.watch)
            if watch is not None and people is not None and watch.owner not in people:
                others += 1
                continue
            mine.append({"watch": look.watch, "name": watch.name if watch else look.watch,
                         "outcome": look.outcome, "why": look.why, "value": look.value,
                         "found": look.found, "turn": look.turn,
                         "notified": look.notified, "matched_by_time": bool(by_time)})
        row["decided"] = mine
        row["others"] = others
        out.append(row)
    return out


def _matched_by_time(store: Store, found: list, decided: dict,
                     watch_ids: list[str]) -> dict[str, list]:
    """READINGS MADE BEFORE LOOKS SAID WHICH ONE THEY JUDGED. A look that a
    reading was handed to starts within seconds of it, marked as made on
    an indriya; one with no reading named is matched to the reading just
    before it, no more than ``MATCH_WINDOW`` back. Only for the history:
    nothing is written, and each one is shown as matched by time."""
    bare = [r for r in found if not decided.get(r.id) and r.came_by != "asked"]
    if not bare or not watch_ids:
        return {}
    stamps = sorted((from_iso(r.at), r) for r in bare)
    until = iso(stamps[-1][0] + MATCH_WINDOW)
    out: dict[str, list] = {}
    for look in store.unmarked_looks(watch_ids, iso(stamps[0][0]), until):
        started = from_iso(look.started_at)
        best = None
        for at, reading in stamps:
            if at <= started and started - at <= MATCH_WINDOW:
                best = reading
        if best is not None:
            out.setdefault(best.id, []).append(look)
    return out


def history_lines(rows: list[dict], *, full: bool = False, when=None) -> list[str]:
    """A history in lines, for a terminal or a chat. ``when``: how a time
    is said (default: as stored)."""
    lines = []
    for row in rows:
        value = f" {row['value']}" if row.get("value") else ""
        at = when(row["at"]) if when else row["at"]
        measured = ""
        if row.get("measured_at") and row["measured_at"] != row["at"]:
            measured = f", measured {when(row['measured_at']) if when else row['measured_at']}"
        lines.append(f"{at}  {row['outcome']}{value}  ({row['came_words']}{measured})")
        if row["outcome"] != "read" or full:
            lines.append(f"    why: {row.get('why') or ''}")
            if row.get("detail"):
                lines.append(f"    {row['detail']}")
        if full and row.get("said"):
            lines.append(f"    came in: {' '.join(row['said'].split())[:300]}")
        for look in row["decided"]:
            told = " -- told you" if look.get("notified") else ""
            matched = " (matched by time)" if look.get("matched_by_time") else ""
            lines.append(f"    → {look['name']}: {look['outcome']}{told}{matched}")
            if full and look.get("why"):
                lines.append(f"        {look['why']}")
        if row.get("others"):
            lines.append(f"    → and {row['others']} of other people's watches")
        if not row["decided"] and not row.get("others") and row["came_by"] == "asked":
            lines.append("    (read on asking: no watch decides on these)")
    return lines


def probe(indriya: Indriya) -> Watch:
    """A watch-shaped view of an indriya, for the roads that make a look
    (``looking.Roads``) and the notifier: they need its id, owner, road,
    agent and call, and nothing a watch decides with."""
    return Watch(id=indriya.id, owner=indriya.owner, name=f"indriya {indriya.name}",
                 check=indriya.check, pick=indriya.pick, runner=indriya.runner,
                 agent=indriya.agent, thing=indriya.thing)
