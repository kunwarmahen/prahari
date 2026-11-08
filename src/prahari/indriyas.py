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


def pause(store: Store, indriya: Indriya, because: str = "paused by you") -> Indriya:
    store.update_indriya(indriya.id, state="paused", paused_because=because)
    return store.get_indriya(indriya.id)


def resume(store: Store, indriya: Indriya) -> Indriya:
    store.update_indriya(indriya.id, state="active", paused_because="", trouble=0,
                         next_at=iso(now_utc()))
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
