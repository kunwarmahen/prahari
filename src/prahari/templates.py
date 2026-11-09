"""Indriya templates: a reading somebody wrote once, with blanks.

"The outside temperature for {latitude}, {longitude}, every 15 minutes"
is the same call for everybody but two numbers. A template is that call
written down with ``{{inputs.latitude}}`` where the numbers go; installing
it is filling the blanks, and what comes out is an ordinary indriya of the
person's own (indriyas.py), read with their own accounts on their own
road. NOBODY RUNS A READING FOR ANYBODY ELSE: a template shares the
recipe, never the value.

Two places to find one:

* the templates that come with Prahari (``prahari/templates/``): the
  outside temperature and the air quality (Open-Meteo, no key), a coin's
  price (Coinbase's public prices), and a Home Assistant sensor sent in;
* a marketplace (Vidhi's: ``VIDHI_MARKET``), where anyone may publish one
  and a reviewer reads and signs it before it is listed. Prahari fetches
  one through ``vidhi market get``, which checks the signature against
  the reviewers THIS person trusts; the indriya it makes says who signed
  it.

A TEMPLATE IS ONE CALL WITH BLANKS, AND NOTHING ELSE. Its file says
``kind = "indriya"``, a name, a ``[check]`` (one tool, its arguments, a
pick), how often, and its inputs -- each a number or a few words. There is
no code in it and no second call; unknown keys are refused. A blank goes
only where the template put it, and A BLANK IN AN ADDRESS IS QUOTED: a
"city" of ``Cary&key=x`` arrives as ``Cary%26key%3Dx``, one value, and
can't add a parameter of its own.

THE PERSON'S YES IS STILL THEIRS. Installing makes the indriya; it does
not make watches. The call it reads with is the template's, filled, shown
before anything is made (``prahari indriya templates``, the page, the
agent's ``install_indriya_template`` says what it calls).
"""

from __future__ import annotations

import json
import re
import subprocess
import tomllib
import urllib.parse
from dataclasses import dataclass, field
from importlib.resources import files

from prahari import indriyas, recipe
from prahari.store import Indriya, Store
from prahari.watches import LOCAL_OWNER, WatchError

TOP = {"kind", "name", "title", "about", "version", "author", "thing", "every", "pushed",
       "share", "inputs", "check"}
CHECK = {"tool", "args", "pick"}
INPUT_KINDS = ("text", "number")
REF = re.compile(r"\{\{\s*inputs\.([a-z][a-z0-9_-]*)\s*\}\}")
INPUT_NAME = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
#: How long a text input may be.
MAX_INPUT = 200
QUICK = 60


@dataclass
class Template:
    name: str
    title: str
    about: str = ""
    version: str = "1"
    author: str = ""
    thing: str = ""
    every: str = indriyas.DEFAULT_EVERY
    pushed: bool = False
    share: str = "mine"
    #: name -> {"kind", "label", "default"}
    inputs: dict = field(default_factory=dict)
    tool: str = ""
    args: dict = field(default_factory=dict)
    pick: str = ""
    #: "prahari" (comes with it), or "market" (fetched, signed)
    source: str = "prahari"
    signed_by: str = ""

    def card(self) -> dict:
        return {"name": self.name, "title": self.title, "about": self.about,
                "version": self.version, "author": self.author, "thing": self.thing,
                "every": self.every, "pushed": self.pushed, "source": self.source,
                "signed_by": self.signed_by,
                "inputs": [{"name": k, **v} for k, v in self.inputs.items()],
                "calls": self.calls()}

    def calls(self) -> str:
        """What it calls, in words, blanks shown as [name]."""
        if self.pushed:
            return (f"no call: a value is sent in (Home Assistant), one every {self.every} "
                    "at least")
        shown = _fill(self.args, {k: f"[{k}]" for k in self.inputs}, quote=False)
        return f"{self.tool} {json.dumps(shown)} every {self.every}, with no model"


def parse(text: str, *, source: str = "prahari", signed_by: str = "") -> Template:
    """A template from its TOML; WatchError says what's wrong."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise WatchError(f"a template is TOML: {exc}") from None
    if data.get("kind") != "indriya":
        raise WatchError("an indriya template says kind = \"indriya\" at its top")
    unknown = sorted(set(data) - TOP)
    if unknown:
        raise WatchError(f"unknown keys in an indriya template: {', '.join(unknown)} "
                         f"(known: {', '.join(sorted(TOP))})")
    check = data.get("check") or {}
    if not isinstance(check, dict) or set(check) - CHECK:
        raise WatchError("check is a table of tool, args and pick")
    inputs = {}
    raw_inputs = data.get("inputs") or {}
    if not isinstance(raw_inputs, dict):
        raise WatchError("inputs is a table of tables: [inputs.latitude] kind = \"number\"")
    for name, spec in raw_inputs.items():
        spec = spec if isinstance(spec, dict) else {"default": spec}
        kind = str(spec.get("kind") or "text")
        if not INPUT_NAME.match(name) or kind not in INPUT_KINDS:
            raise WatchError(f"input {name!r}: one lowercase word, kind text or number")
        inputs[name] = {"kind": kind, "label": str(spec.get("label") or name)[:80],
                        **({"default": spec["default"]} if "default" in spec else {})}
    pushed = bool(data.get("pushed", False))
    tool = str(check.get("tool") or "").strip()
    if pushed and tool:
        raise WatchError("a pushed template makes no call: leave out check.tool")
    if not pushed and not tool:
        raise WatchError("a template reads with one call: check.tool")
    args = check.get("args") or {}
    if not isinstance(args, dict):
        raise WatchError("check.args is a table of the tool's arguments")
    for found in REF.finditer(json.dumps(args)):
        if found.group(1) not in inputs:
            raise WatchError(f"{{{{inputs.{found.group(1)}}}}} is not one of the "
                             "template's inputs")
    template = Template(
        name=str(data.get("name") or ""), title=str(data.get("title") or "")[:120],
        about=str(data.get("about") or "")[:2000],
        version=str(data.get("version") or "1")[:20],
        author=str(data.get("author") or "")[:80], thing=str(data.get("thing") or ""),
        every=str(data.get("every") or (indriyas.DEFAULT_PUSHED_EVERY if pushed
                                        else indriyas.DEFAULT_EVERY)),
        pushed=pushed, share=str(data.get("share") or "mine"), inputs=inputs, tool=tool,
        args=args, pick=str(check.get("pick") or ""), source=source, signed_by=signed_by)
    template.title = template.title or template.name
    # the parts an indriya is made of, checked as one would be (the name,
    # how often, the pick), with every blank filled by a stand-in
    indriyas.checked(name=template.name, check=None if pushed else {
        "tool": tool, "args": _fill(args, {k: "1" for k in inputs}, quote=False)},
        pick=recipe.pick_from_text(template.pick) if template.pick else None,
        every=template.every, thing=template.thing, share=template.share, pushed=pushed)
    return template


def bundled() -> list[Template]:
    """The templates that come with Prahari."""
    root = files("prahari") / "templates"
    return sorted((parse(p.read_text()) for p in root.iterdir() if p.name.endswith(".toml")),
                  key=lambda t: t.name)


def find(name: str) -> Template:
    for template in bundled():
        if template.name == name:
            return template
    raise WatchError(f"no template {name!r} comes with Prahari (prahari indriya templates "
                     f"lists them: {', '.join(t.name for t in bundled())}); one from a "
                     "marketplace: --from-market")


def filled(template: Template, given: dict) -> dict:
    """The inputs a template is installed with: given over defaults, each
    of its kind, none missing and none it doesn't have."""
    unknown = sorted(set(given) - set(template.inputs))
    if unknown:
        raise WatchError(f"{template.name} has no input {', '.join(unknown)} (it has: "
                         f"{', '.join(template.inputs) or 'none'})")
    out = {}
    for name, spec in template.inputs.items():
        value = given.get(name, spec.get("default"))
        if value is None or str(value).strip() == "":
            raise WatchError(f"{template.name} needs {name} filled in ({spec['label']})")
        if spec["kind"] == "number":
            if isinstance(value, bool):
                raise WatchError(f"input {name} is a number, not {value!r}")
            try:
                number = float(str(value).strip())
            except ValueError:
                raise WatchError(f"input {name} is a number, not {value!r}") from None
            value = str(int(number)) if number == int(number) else str(number)
        else:
            value = " ".join(str(value).split())
            if len(value) > MAX_INPUT:
                raise WatchError(f"input {name}: {MAX_INPUT} characters at the most")
        out[name] = value
    return out


def _fill(value, given: dict, *, quote: bool = True):
    if isinstance(value, dict):
        return {k: _fill(v, given, quote=quote) for k, v in value.items()}
    if isinstance(value, list):
        return [_fill(v, given, quote=quote) for v in value]
    if not isinstance(value, str):
        return value
    in_address = quote and value.strip().startswith(("http://", "https://"))
    return REF.sub(lambda m: urllib.parse.quote(str(given[m.group(1)]), safe="")
                   if in_address else str(given[m.group(1)]), value)


def install(store: Store, template: Template, given: dict, *, name: str = "",
            every: str = "", share: str = "", owner: str = LOCAL_OWNER,
            runner: str = "direct", agent: str = "", dvara=None,
            created_via: str = "cli") -> Indriya:
    """The person's own indriya, made from a template filled in."""
    values = filled(template, given)
    whence = f"template {template.name} v{template.version}" + (
        f", signed by {template.signed_by}" if template.signed_by else "")
    return indriyas.create(
        store, name=name or template.name,
        check=None if template.pushed else {"tool": template.tool,
                                            "args": _fill(template.args, values)},
        pick=recipe.pick_from_text(template.pick) if template.pick else None,
        every=every or template.every, thing=template.thing,
        share=share or template.share, owner=owner, runner=runner, agent=agent,
        created_via=f"{created_via}: {whence}", dvara=dvara, pushed=template.pushed)


# -- from a marketplace -------------------------------------------------------------


def _vidhi(args: list[str]) -> dict | list:
    from prahari.looking import RunnerMissing, find_vidhi
    try:
        argv = [*find_vidhi(), *args, "--json"]
    except RunnerMissing as exc:
        raise WatchError(f"a marketplace's templates come through Vidhi: {exc}") from None
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=QUICK,
                              stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise WatchError(f"vidhi didn't answer ({type(exc).__name__})") from None
    if done.returncode != 0:
        said = " ".join((done.stderr or done.stdout or "").split()).removeprefix("error: ")
        raise WatchError(said or "vidhi said nothing")
    lines = (done.stdout or "").strip().splitlines()
    try:
        return json.loads(lines[-1]) if lines else {}
    except json.JSONDecodeError:
        raise WatchError("vidhi's answer wasn't JSON") from None


def market() -> list[dict]:
    """The indriya templates the marketplace (VIDHI_MARKET) lists."""
    listed = _vidhi(["market", "list", "--kind", "indriya"])
    return listed if isinstance(listed, list) else []


def fetch(name: str) -> Template:
    """One from the marketplace, its signature checked by Vidhi against the
    reviewers this person trusts: refused if no one they trust signed it."""
    got = _vidhi(["market", "get", name])
    if not isinstance(got, dict) or got.get("kind") != "indriya":
        raise WatchError(f"{name} in the marketplace is a routine, not an indriya "
                         "template (install it in Vidhi)")
    return parse(str(got.get("toml") or ""), source="market",
                 signed_by=str(got.get("signed_by") or ""))
