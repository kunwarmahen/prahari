"""Floors -- the least time between two calls to one site.

Every call Prahari makes, a watch's or an indriya's, waits at least five
minutes after the last (``recipe.MIN_EVERY``). Some sites ask for more.
A free weather service may want no more than one call in fifteen minutes
from one address; a shop that turns bots away is kinder to everyone when
it is asked once an hour. A FLOOR is that wish, kept once for the site,
so it doesn't have to be remembered at every watch.

A SITE IS AN ADDRESS'S HOST, OR A TOOL'S NAME. A call whose arguments
carry a web address is on that address's host (``api.open-meteo.com``),
and a floor for ``open-meteo.com`` covers its subdomains too. A call with
no address (a mail search, a Home Assistant tool) is on its tool:
``mcp__homeassistant-home__get_state`` is a site of its own.

A FLOOR IS ASKED OF NEW THINGS AND MADE TRUE OF OLD ONES. A watch or an
indriya asked to call more often than its site's floor is refused, in
words that name the floor. Setting a floor slows what already calls
faster down to it, and says which ones. Nothing is left calling faster
than the person said the site wants.

AN INDRIYA'S SPEED-UP STOPS AT THE FLOOR. A watch that asks for five
minutes on a fifteen-minute site still goes by the reading; the reading
reads every fifteen, and the watch is told so.

A FRESH READ WAITS FOR IT TOO. A reader asking for a value newer than
the floor gets the kept one and why, as with the five-minute floor.

Floors are the house's, not a person's: the site doesn't care whose
account is calling, only how often its address is asked.
"""

from __future__ import annotations

import re
from datetime import timedelta

from prahari import recipe
from prahari.store import Floor, Store

_ADDRESS = re.compile(r"https?://(?:www\.)?([^/?#:]+)", re.IGNORECASE)
_SITE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,99}$")


def _error(text: str) -> Exception:
    from prahari.watches import WatchError
    return WatchError(text)


def site_of(check: dict | None) -> str:
    """The site a call is on: its address's host, else its tool's name."""
    if not check:
        return ""
    args = check.get("args") or {}
    first = [args[k] for k in ("url", "address", "endpoint") if k in args]
    for value in [*first, *args.values()]:
        if isinstance(value, str):
            found = _ADDRESS.search(value)
            if found:
                return found.group(1).lower()
    return str(check.get("tool") or "").strip().lower()


def _covers(site: str, called: str) -> bool:
    return called == site or called.endswith("." + site)


def floor_for(store: Store, check: dict | None) -> tuple[timedelta, Floor | None]:
    """The least step a call may be made at: the five-minute floor, or its
    site's when that is longer (the longest that covers it)."""
    step, which = recipe.MIN_EVERY, None
    called = site_of(check)
    if not called:
        return step, None
    for floor in store.floors():
        own = recipe.every(floor.every)
        if _covers(floor.site, called) and own > step:
            step, which = own, floor
    return step, which


def words(floor: Floor) -> str:
    said = (f"{floor.site} is called no more than once every "
            f"{recipe.duration_words(recipe.every(floor.every))}")
    return said + (f" ({floor.why})" if floor.why else "")


def check_pace(store: Store, check: dict | None, every: str, what: str = "it") -> None:
    """Refuse a pace faster than the call's site allows, in words."""
    if not check or not every:
        return
    step, floor = floor_for(store, check)
    if floor is not None and recipe.every(every) < step:
        raise _error(f"{what} would call every {recipe.duration_words(recipe.every(every))}"
                     f", but {words(floor)}: every {floor.every} or slower "
                     "(prahari floor list)")


def at_floor(store: Store, check: dict | None, every: str) -> str:
    """``every``, raised to the call's floor when it is faster."""
    step, floor = floor_for(store, check)
    if floor is not None and recipe.every(every) < step:
        return floor.every
    return every


def put(store: Store, site: str, every: str, why: str = "") -> tuple[Floor, list[str]]:
    """Set a site's floor, and slow what already calls it faster. Returns
    the floor and a line for each watch or indriya slowed."""
    site = (site or "").strip().lower()
    site = re.sub(r"^https?://(?:www\.)?", "", site).split("/")[0]
    if not _SITE.match(site):
        raise _error(f"a site is a host (api.open-meteo.com) or a tool's name, not {site!r}")
    try:
        step = recipe.every(every)
    except recipe.RecipeError as exc:
        raise _error(str(exc)) from None
    why = " ".join((why or "").split())[:120]
    floor = Floor(site=site, every=every.strip(), why=why)
    store.put_floor(floor)
    slowed = []
    for watch in store.watches():
        if watch.check and watch.every and _covers(site, site_of(watch.check)) \
                and recipe.every(watch.every) < step:
            store.update(watch.id, every=floor.every)
            slowed.append(f"watch {watch.id} ({watch.name}) now looks every "
                          f"{recipe.duration_words(step)} (it looked every "
                          f"{recipe.duration_words(recipe.every(watch.every))})")
    for indriya in store.indriyas():
        if indriya.pushed or not _covers(site, site_of(indriya.check)):
            continue
        changes = {}
        if recipe.every(indriya.every) < step:
            changes["every"] = floor.every
            slowed.append(f"indriya {indriya.name} now reads every "
                          f"{recipe.duration_words(step)} (it read every "
                          f"{recipe.duration_words(recipe.every(indriya.every))})")
        if indriya.own_every and recipe.every(indriya.own_every) < step:
            changes["own_every"] = floor.every
        store.update_indriya(indriya.id, **changes)
    return floor, slowed


def remove(store: Store, site: str) -> bool:
    return store.delete_floor((site or "").strip().lower())
