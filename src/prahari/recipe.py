"""A watch's recipe: what to look at, what to pick out, and when it matters.

"Tell me when the price drops under $50" is four things, and an agent
writes them once, out of tools it already has:

    check   one tool call that reads:   amazon_open(url=...)
    pick    what to take out of it:     the first number after "$"
    when    a plain test on that:       below 50
    every   how often to look:          3h

and Prahari repeats the first three with NO MODEL, waking the agent only
when ``when`` comes true. This module is the part with no clock and no
files: a pick turns a tool's text into a value (or a list of items), and
a test says whether that value matters.

THE FORM IS THE CONTRACT, LIKE SAMAY'S ``when``. A recipe is proposed by
a model, often a small local one, which is unreliable at writing code
and reliable at filling in a form. So a pick is one of a few kinds, a
test is one of a few kinds, and an unknown key is an error that names
the keys there are -- ``{"belw": 50}`` is a watch that would never fire,
silently.

    pick   {"number": REGEX}       a number (REGEX "" for the first one;
                                    a capture group says where it is)
           {"text": REGEX}         a piece of text ("" for all of it)
           {"json": PATH}          a value from JSON: a.b[0].c, list[*].id
           {"items": REGEX}        every match is an item; group 1 is its key
           {"items_json": PATH, "key": FIELD}   items from a JSON list
           {}                      the whole text

    when   {"below": N} {"above": N} {"at_most": N} {"at_least": N}
           {"equals": X} {"contains": S} {"lacks": S} {"matches": REGEX}
           {"changed": true}       the value is not what it was last time
           {"new": true}           items not seen before
           {"any": true}           every time (an inlet's event, usually)
           {"ask": QUESTION}       a yes/no for a model, asked only about
                                   a value that changed or items that are new

A TEST ON A VALUE FIRES ON ITS EDGE. "Below 50" is news when the price
goes under 50, not every three hours while it stays there; it fires
again only after the price has been 50 or more in between (``armed``).
That is decided in the clock, from what ``holds`` says here.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import timedelta

PICKS = ("number", "text", "json", "items", "items_json")
#: Keys a pick may have besides its kind.
PICK_EXTRA = {"items_json": ("key",)}

NUMBER_TESTS = ("below", "above", "at_most", "at_least")
TEXT_TESTS = ("equals", "contains", "lacks", "matches")
FLAGS = ("changed", "new", "any")
TESTS = (*NUMBER_TESTS, *TEXT_TESTS, *FLAGS, "ask")
#: Tests that look at one value and fire on their edge.
EDGED = (*NUMBER_TESTS, *TEXT_TESTS)

#: Nothing is looked at more often than this, however it is written.
MIN_EVERY = timedelta(minutes=5)
#: Nor less often than this: a watch looked at monthly is a schedule.
MAX_EVERY = timedelta(days=7)

#: How much of a picked text is kept and shown.
TEXT_CAP = 2000
#: How many items one look may report as new.
ITEMS_CAP = 50

_NUMBER = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?|[-+]?\.\d+")
_DURATION = re.compile(r"^\s*(\d+)\s*(m|min|mins|minutes?|h|hr|hrs|hours?|d|days?)\s*$",
                       re.IGNORECASE)


class RecipeError(ValueError):
    """A recipe that cannot become a watch, said so a model can fix it."""


@dataclass
class Item:
    """One thing a look found: its key (never shown twice) and its line."""

    key: str
    line: str


@dataclass
class Picked:
    """What a pick took out of a result. ``found`` is False when the pick
    found nothing at all -- a check that no longer finds what it looked
    for, not a value that happens to be empty."""

    found: bool
    value: object = None
    items: list[Item] = field(default_factory=list)

    def shown(self) -> str:
        """The value in a few words, for a list and a message."""
        if self.items:
            return f"{len(self.items)} item(s)"
        if isinstance(self.value, float):
            return _number_words(self.value)
        text = "" if self.value is None else str(self.value)
        text = " ".join(text.split())
        return text if len(text) <= 120 else text[:119] + "…"

    def stored(self) -> str:
        """What is kept as the last value: JSON, for ``changed``."""
        return json.dumps(self.value, sort_keys=True, default=str)


# -- checking a recipe ----------------------------------------------------------


def check_pick(pick: dict | str | None) -> dict:
    """The pick, checked; RecipeError in words for anything else."""
    pick = _form(pick, "pick")
    if not pick:
        return {}
    kinds = [k for k in pick if k in PICKS]
    allowed = set(PICKS) | {x for k in kinds for x in PICK_EXTRA.get(k, ())}
    unknown = [k for k in pick if k not in allowed]
    if unknown:
        raise RecipeError(f"unknown key(s) {', '.join(unknown)} in \"pick\"; known: "
                          f"{', '.join(PICKS)} (items_json also takes key)")
    if len(kinds) != 1:
        raise RecipeError(f"a pick is exactly one of {', '.join(PICKS)}; got "
                          f"{', '.join(kinds) or 'none'}")
    kind = kinds[0]
    value = pick[kind]
    if not isinstance(value, str):
        raise RecipeError(f"pick {kind} is text (a pattern or a path), not {value!r}")
    if kind in ("number", "text", "items") and value:
        _regex(value, f"pick {kind}")
    if kind in ("json", "items_json"):
        _path(value)
    if kind == "items_json" and not isinstance(pick.get("key", ""), str):
        raise RecipeError("pick key is a field name in each item")
    return dict(pick)


def check_when(when: dict | str | None, pick: dict) -> dict:
    """The test, checked against the pick it reads."""
    when = _form(when, "when")
    unknown = [k for k in when if k not in TESTS]
    if unknown:
        raise RecipeError(f"unknown key(s) {', '.join(unknown)} in \"when\"; known: "
                          f"{', '.join(TESTS)}")
    if len(when) != 1:
        raise RecipeError(f"a when is exactly one test, of {', '.join(TESTS)}; got "
                          f"{', '.join(when) or 'none'}")
    (test, value), = when.items()
    kind = pick_kind(pick)
    if test in NUMBER_TESTS:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise RecipeError(f"when {test} is a number, not {value!r}")
        if kind != "number" and kind not in ("json",):
            raise RecipeError(f"when {test} compares a number: pick one with "
                              '{"number": ""} (or a JSON value)')
    elif test in TEXT_TESTS:
        if not isinstance(value, (str, int, float)) or isinstance(value, bool):
            raise RecipeError(f"when {test} is text, not {value!r}")
        if test == "matches":
            _regex(str(value), "when matches")
    elif test in FLAGS:
        if value is not True:
            raise RecipeError(f'when {test} is written {{"{test}": true}}')
        if test == "new" and kind not in ("items", "items_json"):
            raise RecipeError('when new needs items to tell apart: pick them with '
                              '{"items": REGEX} or {"items_json": PATH, "key": FIELD}')
    elif test == "ask":
        if not isinstance(value, str) or not value.strip():
            raise RecipeError("when ask is a yes/no question, in words")
    if kind in ("items", "items_json") and test not in ("new", "any", "ask"):
        raise RecipeError(f"a pick of items is tested with new, any or ask, not {test}")
    return {test: value}


def pick_kind(pick: dict) -> str:
    return next((k for k in pick if k in PICKS), "")


def test_of(when: dict) -> str:
    return next(iter(when))


def every(raw: str | None) -> timedelta:
    """"30m", "3h", "1d" as a step, between MIN_EVERY and MAX_EVERY."""
    match = _DURATION.match(str(raw or ""))
    if not match:
        raise RecipeError(f"every is how often to look, like 30m, 3h or 1d -- "
                          f"not {raw!r}")
    count, unit = int(match.group(1)), match.group(2)[0].lower()
    step = timedelta(**{"m": {"minutes": count}, "h": {"hours": count},
                        "d": {"days": count}}[unit])
    if step < MIN_EVERY:
        raise RecipeError(f"nothing is looked at more often than every "
                          f"{duration_words(MIN_EVERY)}; {raw!r} is too often")
    if step > MAX_EVERY:
        raise RecipeError(f"a watch looks at least every "
                          f"{duration_words(MAX_EVERY)}; for less often, a "
                          "schedule (Samay) is the better fit")
    return step


def duration_words(step: timedelta) -> str:
    minutes = int(step.total_seconds() // 60)
    for size, word in ((1440, "day"), (60, "hour"), (1, "minute")):
        if minutes % size == 0:
            count = minutes // size
            return word if count == 1 else f"{count} {word}s"
    return f"{minutes} minutes"


# -- short forms ----------------------------------------------------------------


def pick_from_text(text: str) -> dict:
    """``number``, ``number:\\$([\\d.]+)``, ``text:REGEX``, ``json:a.b``,
    ``items:thread (\\w+)``, ``items_json:messages[*]:id``, or JSON."""
    text = (text or "").strip()
    if not text or text in ("all", "whole"):
        return {}
    if text.startswith("{"):
        return check_pick(text)
    kind, _, rest = text.partition(":")
    kind = kind.strip().replace("-", "_")
    if kind == "items_json":
        path, _, key = rest.rpartition(":") if ":" in rest else (rest, "", "")
        return check_pick({"items_json": path.strip(), "key": key.strip()})
    return check_pick({kind: rest})


def when_from_text(text: str, pick: dict) -> dict:
    """``below 50``, ``above 1,200``, ``changed``, ``new``, ``any``,
    ``contains Mum``, ``matches REGEX``, ``ask is it an invoice?``, or JSON."""
    text = (text or "").strip()
    if text.startswith("{"):
        return check_when(text, pick)
    word, _, rest = text.partition(" ")
    word = word.strip().lower().replace("-", "_")
    rest = rest.strip()
    if word in FLAGS and not rest:
        return check_when({word: True}, pick)
    if word in NUMBER_TESTS:
        number = _to_number(rest)
        if number is None:
            raise RecipeError(f"when {word} needs a number, not {rest!r}")
        return check_when({word: number}, pick)
    if word in (*TEXT_TESTS, "ask") and rest:
        return check_when({word: rest}, pick)
    raise RecipeError(f"when is one of: below N, above N, at_most N, at_least N, "
                      f"equals X, contains X, lacks X, matches REGEX, changed, new, "
                      f"any, ask QUESTION -- not {text!r}")


# -- using one ------------------------------------------------------------------


def apply(pick: dict, text: str) -> Picked:
    """Take the pick out of a tool's text."""
    kind = pick_kind(pick)
    if not kind:
        stripped = text.strip()
        return Picked(found=bool(stripped), value=stripped[:TEXT_CAP])
    pattern = pick[kind]
    if kind == "number":
        return _pick_number(pattern, text)
    if kind == "text":
        if not pattern:
            stripped = text.strip()
            return Picked(found=bool(stripped), value=stripped[:TEXT_CAP])
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if not match:
            return Picked(found=False)
        got = match.group(1) if match.groups() else match.group(0)
        return Picked(found=True, value=(got or "").strip()[:TEXT_CAP])
    if kind == "json":
        data = _json(text)
        if data is _NOTHING:
            return Picked(found=False)
        got = _walk(data, pattern)
        if got is _NOTHING:
            return Picked(found=False)
        if isinstance(got, (int, float)) and not isinstance(got, bool):
            got = float(got)
        elif isinstance(got, str) and _NUMBER.fullmatch(got.strip().lstrip("$€£₹").strip()):
            got = _to_number(got)        # "47.10" or "$1,200" as sent by an API
        return Picked(found=True, value=got)
    if kind == "items":
        return _pick_items(pattern, text)
    data = _json(text)
    if data is _NOTHING:
        return Picked(found=False)
    got = _walk(data, pattern)
    if got is _NOTHING or not isinstance(got, list):
        return Picked(found=False)
    key = pick.get("key") or ""
    items = []
    for entry in got:
        ident = entry.get(key) if key and isinstance(entry, dict) else entry
        if ident is None:
            continue
        line = json.dumps(entry, default=str) if not isinstance(entry, str) else entry
        items.append(Item(key=str(ident), line=_short(line)))
    return Picked(found=True, value=[i.key for i in items], items=items)


def holds(when: dict, picked: Picked) -> bool | None:
    """Whether a test on one value is true now; None for tests that are
    not about one value (changed, new, any, ask: the clock decides those
    against what it kept)."""
    test, want = next(iter(when.items()))
    value = picked.value
    if test in NUMBER_TESTS:
        number = value if isinstance(value, float) else _to_number(str(value or ""))
        if number is None:
            return False
        return {"below": number < want, "above": number > want,
                "at_most": number <= want, "at_least": number >= want}[test]
    if test in TEXT_TESTS:
        text = "" if value is None else str(value)
        if test == "equals":
            if isinstance(want, (int, float)) and isinstance(value, float):
                return value == float(want)
            return text.strip().lower() == str(want).strip().lower()
        if test == "contains":
            return str(want).lower() in text.lower()
        if test == "lacks":
            return str(want).lower() not in text.lower()
        return re.search(str(want), text, re.IGNORECASE | re.MULTILINE) is not None
    return None


def sentence(check: dict, listen: str, pick: dict, when: dict, step: str,
             thing: str = "") -> str:
    """The watch in words: what is looked at, how often, and when it fires.
    WHERE, NOT WITH WHAT: "looks at google.com/travel/flights", the tool
    only after it -- the person knows the page, not the tool."""
    test = next(iter(when))
    what = when_words(when)
    thing = thing_words(pick, thing)
    if listen:
        head = f"when {listen} sends something"
        return f"{head}, if {thing} {what}" if test != "any" else head
    tool = check.get("tool", "?")
    where = where_words(check)
    look = (f"every {duration_words(every(step))}, "
            + (f"looks with {where}" if where.startswith(tool)
               else f"looks at {where} (with {tool})"))
    edge = (" (once each time it becomes true)" if test in EDGED else "")
    return f"{look}; tells you when {thing} {what}{edge}"


def when_words(when: dict) -> str:
    """The test in words, after the thing: "is below 571", "changes"."""
    test, want = next(iter(when.items()))
    return {"below": f"is below {_num(want)}", "above": f"is above {_num(want)}",
            "at_most": f"is {_num(want)} or less", "at_least": f"is {_num(want)} or more",
            "equals": f"is {want!r}", "contains": f"says {want!r}",
            "lacks": f"stops saying {want!r}", "matches": f"matches {want!r}",
            "changed": "changes", "new": "has something new",
            "any": "comes in", "ask": f"makes the answer to {want!r} yes"}[test]


def thing_words(pick: dict, thing: str = "") -> str:
    """What the pick takes, in words: the watch's own ("the fare"), else
    its kind ("the number", "the list")."""
    if thing:
        return thing
    return {"number": "the number", "text": "the text", "json": "the value",
            "items": "the list", "items_json": "the list", "": "the result"}[pick_kind(pick)]


def where_words(check: dict) -> str:
    """What a check looks at, in a few words: a page's site and path
    ("google.com/travel/flights"), else its first words of argument (a
    mail search's query), else the tool's name."""
    args = check.get("args") or {}
    # What narrows the call says most: a search's query before an account's name.
    first = [args[k] for k in ("url", "query", "q", "search") if k in args]
    texts = [v.strip() for v in [*first, *args.values()] if isinstance(v, str) and v.strip()]
    for text in texts:
        address = re.match(r"https?://(?:www\.)?([^/?#]+)((?:/[^/?#]+){0,2})", text)
        if address:
            return address.group(1) + address.group(2)
    tool = str(check.get("tool") or "?")
    if texts:
        said = " ".join(texts[0].split())
        return f"{tool} for {said if len(said) <= 40 else said[:39] + '…'!r}"
    return tool


# -- the parts ------------------------------------------------------------------


_NOTHING = object()


def _form(raw, name: str) -> dict:
    if raw is None or raw == "":
        return {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RecipeError(f"{name} is not JSON: {exc}") from None
    if not isinstance(raw, dict):
        raise RecipeError(f"{name} is an object, like {{\"below\": 50}}")
    return raw


def _regex(pattern: str, where: str) -> None:
    try:
        re.compile(pattern)
    except re.error as exc:
        raise RecipeError(f"{where}: not a pattern Python can read ({exc})") from None


_STEP = re.compile(r"([A-Za-z_][\w-]*)|\[(\d+|\*)\]")


def _path(path: str) -> list:
    """"a.b[0].c" / "list[*].id" as steps; RecipeError for anything else."""
    steps: list = []
    rest = path.strip()
    if not rest:
        raise RecipeError("a JSON path names something, like messages[*].id")
    position = 0
    while position < len(rest):
        if rest[position] == ".":
            position += 1
            continue
        match = _STEP.match(rest, position)
        if not match:
            raise RecipeError(f"JSON path {path!r}: can't read it from "
                              f"{rest[position:]!r} (use a.b[0].c or list[*].id)")
        if match.group(1):
            steps.append(match.group(1))
        else:
            steps.append("*" if match.group(2) == "*" else int(match.group(2)))
        position = match.end()
    return steps


def _walk(data, path: str):
    current = [data]
    spread = False
    for step in _path(path):
        nxt = []
        for node in current:
            if step == "*":
                if isinstance(node, list):
                    nxt.extend(node)
                    spread = True
            elif isinstance(step, int):
                if isinstance(node, list) and -len(node) <= step < len(node):
                    nxt.append(node[step])
            elif isinstance(node, dict) and step in node:
                nxt.append(node[step])
        current = nxt
    if spread:
        return current
    return current[0] if current else _NOTHING


def _json(text: str):
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # A tool that says a line first, then its JSON ("found 3:\n[...]").
    for opener in ("{", "["):
        start = text.find(opener)
        if start > 0:
            try:
                return json.loads(text[start:])
            except json.JSONDecodeError:
                continue
    return _NOTHING


def _pick_number(pattern: str, text: str) -> Picked:
    if not pattern:
        match = _NUMBER.search(text)
        return Picked(found=False) if not match else \
            Picked(found=True, value=_to_number(match.group(0)))
    match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
    if not match:
        return Picked(found=False)
    got = match.group(1) if match.groups() else match.group(0)
    number = _to_number(got or "")
    if number is None:
        # the pattern found where; the number is the first one after it
        after = _NUMBER.search(text, match.end())
        number = _to_number(after.group(0)) if after else None
    return Picked(found=number is not None, value=number)


def _pick_items(pattern: str, text: str) -> Picked:
    items: dict[str, Item] = {}
    lines = text.splitlines()
    for match in re.finditer(pattern, text, re.MULTILINE):
        key = match.group(1) if match.groups() else match.group(0)
        if not key or key in items:
            continue
        line_no = text.count("\n", 0, match.start())
        line = lines[line_no] if line_no < len(lines) else match.group(0)
        # the line under it, too: a mail's subject is on the next one
        if line_no + 1 < len(lines) and lines[line_no + 1].startswith((" ", "\t")):
            line = f"{line.strip()} — {lines[line_no + 1].strip()}"
        items[key] = Item(key=key, line=_short(line))
    found = list(items.values())
    # A list that came back empty is still a list that was found: an inbox
    # with no mail matching is not a broken check.
    return Picked(found=True, value=[i.key for i in found], items=found)


def _to_number(raw: str) -> float | None:
    text = str(raw).strip().replace("−", "-")
    match = _NUMBER.search(text)
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def _number_words(number: float) -> str:
    return f"{number:,.2f}".rstrip("0").rstrip(".") if number % 1 else f"{number:,.0f}"


def _num(value) -> str:
    return _number_words(float(value)) if isinstance(value, (int, float)) else str(value)


def _short(line: str, limit: int = 240) -> str:
    line = " ".join(line.split())
    return line if len(line) <= limit else line[:limit - 1] + "…"
