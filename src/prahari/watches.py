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

A CAP PER PERSON (``$PRAHARI_MAX_WATCHES``, default 30). A watch looks on
its own, forever, and every look starts a program; a loop in a model's
reasoning should not be able to leave hundreds behind.
"""

from __future__ import annotations

import os
import re
from datetime import timedelta

from prahari import recipe
from prahari.store import RUNNERS, Store, Watch, iso, now_utc

#: The person at this computer -- Samay's word for it too.
LOCAL_OWNER = "local"

DEFAULT_MAX_PER_DAY = 10
DEFAULT_WAIT = 30
DEFAULT_TIME_LIMIT = 600

_TOOL = re.compile(r"^[A-Za-z_][A-Za-z0-9_.:-]{0,127}$")
_WORD = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")


class WatchError(ValueError):
    """A watch that cannot be made or changed, said in words."""


def max_watches() -> int:
    try:
        return max(1, int(os.environ.get("PRAHARI_MAX_WATCHES", "30")))
    except ValueError:
        return 30


def checked(*, name: str = "", check=None, listen: str = "", pick=None, when=None,
            every: str = "") -> dict:
    """The recipe's parts, checked together; WatchError in words."""
    try:
        check = recipe._form(check, "check")
        listen = (listen or "").strip().lower()
        if check and listen:
            raise WatchError("a watch either looks (check) or listens (listen), not both")
        if not check and not listen:
            raise WatchError("a watch needs a check -- {\"tool\": NAME, \"args\": {...}} "
                             "-- or a listen word for the inlet")
        if check:
            unknown = [k for k in check if k not in ("tool", "args")]
            if unknown:
                raise WatchError(f"unknown key(s) {', '.join(unknown)} in check; known: "
                                 "tool, args")
            tool = str(check.get("tool") or "")
            if not _TOOL.match(tool):
                raise WatchError(f"check tool is a tool's exact name, not {tool!r}")
            args = check.get("args") or {}
            if not isinstance(args, dict):
                raise WatchError("check args is an object of the tool's arguments")
            check = {"tool": tool, "args": args}
            recipe.every(every)
        else:
            if not _WORD.match(listen):
                raise WatchError(f"listen is one short lowercase word (whatsapp, "
                                 f"doorbell), not {listen!r}")
            if every:
                raise WatchError("a watch that listens has no every: it hears when "
                                 "something is sent")
        pick = recipe.check_pick(pick)
        when = recipe.check_when((when or {"any": True}) if listen else when, pick)
    except recipe.RecipeError as exc:
        raise WatchError(str(exc)) from None
    name = " ".join((name or "").split())
    if len(name) > 80:
        raise WatchError("a watch's name is a few words (80 letters at most)")
    if not name:
        name = (f"{check['tool']} watch" if check else f"{listen} at the inlet")
    return {"name": name, "check": check, "listen": listen, "pick": pick, "when": when,
            "every": every.strip() if check else ""}


def create(store: Store, *, name: str = "", check=None, listen: str = "", pick=None,
           when=None, every: str = "", then: str = "", owner: str = LOCAL_OWNER,
           runner: str = "direct", agent: str = "", allow_tools: list[str] | None = None,
           wait: int = DEFAULT_WAIT, time_limit: int = DEFAULT_TIME_LIMIT,
           max_per_day: int = DEFAULT_MAX_PER_DAY, created_via: str = "cli",
           dvara=None) -> Watch:
    parts = checked(name=name, check=check, listen=listen, pick=pick, when=when,
                    every=every)
    if runner not in RUNNERS:
        raise WatchError(f"runner is direct or dvara, not {runner!r}")
    if runner == "dvara":
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
        watch.next_at = iso(now_utc())      # the first look, soon: it learns
    return store.add(watch)


def update(store: Store, watch_id: str, *, owner: str | None = None, **changes) -> Watch:
    """Mend a watch: its check, pick, test, how often, or what it does.

    A CHANGED RECIPE STARTS OVER. What the old one remembered -- its last
    value, what it had seen -- was picked by the old pick, so the next
    look learns again instead of comparing apples with what came before.
    """
    watch = find(store, watch_id, owner=owner)
    allowed = {"name", "check", "pick", "when", "every", "then", "allow_tools",
               "max_per_day"}
    unknown = [k for k in changes if k not in allowed]
    if unknown:
        raise WatchError(f"can't change {', '.join(unknown)}; can change: "
                         f"{', '.join(sorted(allowed))}")
    given = {k: v for k, v in changes.items() if v is not None}
    recipe_keys = {"check", "pick", "when", "every"}
    parts = checked(
        name=given.get("name", watch.name),
        check=given.get("check", watch.check) if not watch.listen else None,
        listen=watch.listen, pick=given.get("pick", watch.pick),
        when=given.get("when", watch.when), every=given.get("every", watch.every))
    fields: dict = {"name": parts["name"]}
    if recipe_keys & set(given):
        fields.update(check=parts["check"], pick=parts["pick"], when=parts["when"],
                      every=parts["every"], armed=True, last_value="", trouble=0,
                      looked=bool(watch.listen))
        if not watch.listen:
            fields["next_at"] = iso(now_utc())
        if watch.state == "paused" and watch.paused_because.startswith(("broken", "failed")):
            fields.update(state="active", paused_because="")
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
    return recipe.sentence(watch.check, watch.listen, watch.pick, watch.when, watch.every)


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
            every: str = "", sample=None, agent: str = "") -> dict:
    """Try a recipe ONCE, before anybody said yes: look (only with a tool
    that reads -- nothing is granted yet), pick, and say what it saw.

    WRITTEN FOR THE ONE WRITING THE PICK. The answer carries the start of
    what the tool said, so a model whose pick found nothing can see why
    and write a better one, and the sentence the person will be asked to
    accept. A watch that listens is tried on ``sample``, an event like
    the one the sender will send."""
    import json as _json

    parts = checked(check=check, listen=listen, pick=pick, when=when, every=every)
    out: dict = {"sentence": recipe.sentence(parts["check"], parts["listen"],
                                             parts["pick"], parts["when"], parts["every"]),
                 "looked": False}
    if parts["listen"]:
        if sample is None:
            out["said"] = ("Nothing to try it on yet: give a sample of what the sender "
                           "will send (a JSON object), or send one to the inlet.")
            return out
        text = _json.dumps(sample if isinstance(sample, dict) else {"text": str(sample)},
                           sort_keys=True, ensure_ascii=False)
    else:
        probe = Watch(id="", owner="", name="", check=parts["check"], agent=agent)
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
