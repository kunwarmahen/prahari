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
reading is theirs to set, and never below the five-minute floor. Watches
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
#: A fresh read is not made sooner than this after the last reading.
FRESH_FLOOR = recipe.MIN_EVERY
#: Unused this long (no watch decided on it, nobody asked), it pauses.
UNUSED = timedelta(days=30)


def max_indriyas() -> int:
    try:
        return max(1, int(os.environ.get("PRAHARI_MAX_INDRIYAS", "30")))
    except ValueError:
        return 30


def checked(*, name: str, check=None, pick=None, every: str = "", thing: str = "",
            share: str = "mine") -> dict:
    """An indriya's parts, checked together; WatchError in words."""
    name = (name or "").strip().lower()
    if not _NAME.match(name):
        raise WatchError(f"an indriya's name is one short lowercase word, letters, "
                         f"digits and dashes (outside-temp, btc-price), not {name!r}")
    check = _call(check, "check")
    if not check:
        raise WatchError("an indriya needs a check -- {\"tool\": NAME, \"args\": {...}} "
                         "-- the one call it reads with")
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
           dvara=None) -> Indriya:
    parts = checked(name=name, check=check, pick=pick, every=every, thing=thing,
                    share=share)
    if any(i.name == parts["name"] for i in store.indriyas(owner=owner)):
        raise WatchError(f"{owner} already has an indriya called {parts['name']}; "
                         "mend that one, or choose another name")
    twin = next((i for i in store.indriyas(owner=owner)
                 if i.check == parts["check"]), None)
    if twin is not None:
        raise WatchError(f"{owner}'s indriya {twin.name} already reads with exactly this "
                         f"call; sense that one (and pick from its answer) instead of "
                         "calling twice")
    if runner not in RUNNERS:
        raise WatchError(f"runner is direct or dvara, not {runner!r}")
    if runner == "dvara":
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
    made = Indriya(id="", owner=owner, runner=runner, agent=agent,
                   created_via=created_via, next_at=iso(now_utc()), **parts)
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
    parts = checked(name=current.name, check=given.get("check", current.check),
                    pick=given.get("pick", current.pick),
                    every=given.get("every", current.every),
                    thing=given.get("thing", current.thing),
                    share=given.get("share", current.share))
    fields = {k: parts[k] for k in ("check", "pick", "every", "thing", "share")}
    if {"check", "pick"} & set(given):
        fields.update(value="", stored="", read_at=None, trouble=0, next_at=iso(now_utc()))
        if current.state == "paused" and current.paused_because.startswith(
                ("broken", "failed")):
            fields.update(state="active", paused_because="")
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
               created_via: str = "cli") -> tuple[Indriya, list[Watch], list[Watch]]:
    """An indriya made from a watch's own call: its check, pick, thing,
    road and how often (or ``every``). Returns it, the watches moved onto
    it (``move``: every watch of this person's that makes the very same
    call), and those that could be (not ``move``) -- the person decides."""
    from prahari import watches as watches_module

    if not watch.check:
        raise WatchError(f"{watch.id} makes no call of its own (it "
                         + ("senses an indriya" if watch.sense else "listens")
                         + "), so there is nothing to make a reading from")
    made = create(store, name=name, check=watch.check, pick=watch.pick,
                  every=every or watch.every or DEFAULT_EVERY, thing=watch.thing,
                  share=share, owner=watch.owner, runner=watch.runner, agent=watch.agent,
                  created_via=created_via)
    same = [w for w in store.watches(owner=watch.owner)
            if w.check == watch.check and w.state != "ended"]
    if not move:
        return made, [], same
    moved = [watches_module.update(store, w.id, sense=made.id, home=home) for w in same]
    return store.get_indriya(made.id) or made, moved, []


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
    this indriya, so it reads at least that often. Returns what changed,
    in words ("" for nothing)."""
    wanted, now = recipe.every(every), recipe.every(indriya.every)
    if wanted >= now:
        return ""
    store.update_indriya(indriya.id, every=every.strip())
    due = from_iso(indriya.next_at)
    soon = now_utc() + wanted
    if due is None or due > soon:
        store.update_indriya(indriya.id, next_at=iso(soon))
    return (f"{indriya.name} now reads every {recipe.duration_words(wanted)} (it read "
            f"every {recipe.duration_words(now)}), as often as this watch asked")


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
    if indriya.state != "active":
        return indriya, (f"not read again: {indriya.name} is paused "
                         f"({indriya.paused_because or 'by hand'})")
    last = store.readings(indriya.id, limit=1)
    tried = from_iso(last[0].at) if last else None
    if tried is not None and now - tried < FRESH_FLOOR:
        return indriya, (f"not read again: it was read {age_words(last[0].at)}, and a "
                         f"reading is not made again within "
                         f"{recipe.duration_words(FRESH_FLOOR)}")
    reading, _ = take(caller, indriya, now)
    reading.why = f"Asked for fresh by a reader. {reading.why}"
    store.add_reading(reading)
    if reading.outcome != "read":
        return indriya, (f"read again, but it did not read ({reading.outcome}: "
                         f"{reading.detail or reading.why}); the value below is the kept one")
    store.update_indriya(indriya.id, value=reading.value, stored=reading.stored,
                         read_at=reading.at)
    return store.get_indriya(indriya.id) or indriya, "read again just now, as asked"


def pause(store: Store, indriya: Indriya, because: str = "paused by you") -> Indriya:
    store.update_indriya(indriya.id, state="paused", paused_because=because)
    return store.get_indriya(indriya.id)


def resume(store: Store, indriya: Indriya) -> Indriya:
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


def probe(indriya: Indriya) -> Watch:
    """A watch-shaped view of an indriya, for the roads that make a look
    (``looking.Roads``) and the notifier: they need its id, owner, road,
    agent and call, and nothing a watch decides with."""
    return Watch(id=indriya.id, owner=indriya.owner, name=f"indriya {indriya.name}",
                 check=indriya.check, pick=indriya.pick, runner=indriya.runner,
                 agent=indriya.agent, thing=indriya.thing)
