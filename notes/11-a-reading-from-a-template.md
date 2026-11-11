# 11 — A reading from a template

"The outside temperature for 35.79, -78.78, every 15 minutes" is the
same call for everybody but two numbers. Writing it by hand meant knowing
Open-Meteo's address, its parameters, and that the number sits at
`current.temperature_2m`. Asking the agent meant a model writing a URL.
A template is that call written once, with blanks where the numbers go.

Continues [06](06-one-reading-many-watches.md).

## The file

```toml
kind = "indriya"
name = "outside-temp"
title = "Outside temperature"
thing = "the outside temperature"
every = "15m"

[inputs.latitude]
kind = "number"
[inputs.longitude]
kind = "number"
[inputs.unit]
default = "fahrenheit"

[check]
tool = "web_fetch"
args = { url = "https://api.open-meteo.com/v1/forecast?latitude={{inputs.latitude}}&longitude={{inputs.longitude}}&current=temperature_2m&temperature_unit={{inputs.unit}}" }
pick = "json:current.temperature_2m"
```

**ONE CALL WITH BLANKS, AND NOTHING ELSE.** A template is one tool
call (or `pushed = true`: a value sent in, no call), a pick, how often,
and blanks that are numbers or a few words. Any other key is refused.
There is no code in it and no second call. It is read through the same
check an indriya made by hand is (`indriyas.checked`), with every blank
filled by a stand-in, so a template whose pick or pace a real indriya
would refuse is refused when it is read, not when someone installs it.

**A BLANK GOES ONLY WHERE THE TEMPLATE PUT IT, AND AN ADDRESS QUOTES
IT.** Filling `{{inputs.city}}` into a string that is an address encodes
the value, so `Cary&key=stolen` arrives as `Cary%26key%3Dstolen`: one
value, never a parameter of its own. A number blank takes a number
(`north` is refused), and a blank the template doesn't have is refused,
not ignored.

**NOBODY RUNS A READING FOR ANYBODY ELSE.** Installing makes an ordinary
indriya of the person's own, read with their accounts on their road.
Two people with the same template have two readings. Sharing one is
`--share house`, the person's choice, as for any indriya.

**IT SAYS WHERE IT CAME FROM.** The indriya's `made` line keeps the
template and its version, and for one from a marketplace who signed it:
*by cli: template eth-price v1, signed by rita*.

## Where they come from

Four come with Prahari (`prahari/templates/`): `outside-temp` and
`air-quality` (Open-Meteo, no account, no key), `coin-price` (Coinbase's
public prices), and `home-sensor` (a Home Assistant value sent in, as
[08](08-a-value-sent-in.md)). `prahari indriya templates` lists them,
each with what it calls, its blanks shown as `[latitude]`.

**A MARKETPLACE'S ARE SIGNED, AND CHECKED IN ONE PLACE.** Vidhi's
marketplace carries indriya templates beside routines (Vidhi's notes/06):
published by anyone, read by a reviewer whose notes say what it calls
and every address it reaches, signed with the reviewer's SSH key.
`prahari indriya install NAME --from-market` asks `vidhi market get NAME
--json`, which checks the signature against the reviewers *this person*
trusts and refuses otherwise. Prahari keeps no keys and no trust list of
its own: one place decides what is signed.

**A REVIEW TAKEN BACK PAUSES WHAT WAS MADE FROM IT.** A reviewer can take
a review back (Vidhi's notes/08). A reading made `--from-market` keeps
the sha256 of the exact text that was reviewed (`template_sha256`).
Once an hour, and only when some active reading has one, the clock asks
`vidhi market revoked --json` for the take-backs Vidhi believed -- each
signed by a reviewer *this person* trusts, the same list as the review
-- and pauses every reading made from a text on it, saying who took the
review back and why, and naming the watches that go quiet with it.

* **THE EXACT TEXT, NOT THE NAME.** A reading made from one that comes
  with Prahari, or from another version, or made here, is not touched.
* **RESUME IS REFUSED; A MEND IS THE OWNER'S.** `prahari indriya resume`
  says why it stays paused. Mending its call or pick makes it the owner's
  own reading: the hash goes, and it runs again.
* **VIDHI AWAY IS NOT A TAKE-BACK.** No answer from Vidhi pauses nothing;
  it is asked again the next hour.

## The doors

| Door | Templates | Install |
|---|---|---|
| CLI | `prahari indriya templates [--market]` | `prahari indriya install NAME --input k=v [--name] [--every] [--share] [--from-market]` |
| HTTP | `GET /api/indriya-templates?market=1` | `POST /api/indriya-templates/NAME/install {inputs, name, every, share, from_market, as}` |
| MCP | `indriya_templates` (reads) | `install_indriya_template` (a write: Yantra shows a card with what it calls, the blanks as filled, and, from a marketplace, that it is made only if a trusted reviewer signed it) |
| page | **From a template** under Indriyas, with the marketplace's on **Show the marketplace's too** | **Install** |

The agent is told, in its prompt, that a reading somebody already wrote
is a template: fill the blanks, rather than write a URL.

## Live receipt

A scratch state, the real `yantra` (`web_fetch`):

```
$ prahari indriya install outside-temp --input latitude=35.79 --input longitude=-78.78
added indriya outside-temp from outside-temp: reads the outside temperature every 15 minutes: looks at api.open-meteo.com/v1/forecast (with web_fetch)
$ prahari indriya get outside-temp --max-age 5m
f1301433  active  outside-temp: 70.2 (just now)
          check: web_fetch {"url": "https://api.open-meteo.com/v1/forecast?latitude=35.79&longitude=-78.78&current=temperature_2m&temperature_unit=fahrenheit"}
          pick: {"json": "current.temperature_2m"}   next reading: Mon 9 Nov 15:34
          made Mon 9 Nov 15:34 (by cli: template outside-temp v1), for local
```

And one from a scratch marketplace, refused until its reviewer was
trusted, then installed and read (Vidhi's notes/06 has the publishing
half):

```
$ prahari indriya install eth-price --from-market
error: no reviewers are trusted yet (.../reviewers): vidhi market trust NAME 'ssh-ed25519 AAAA...'
$ vidhi market trust rita rita.pub
$ prahari indriya install eth-price --from-market
added indriya eth-price from eth-price (signed by rita): reads the coin's price every 15 minutes: looks at api.coinbase.com/v2/prices (with web_fetch)
$ prahari indriya get eth-price --max-age 5m
15101def  active  eth-price: 2,121.89 (just now)
          made Mon 9 Nov 15:35 (by cli: template eth-price v1, signed by rita), for local
```

### A review taken back

A scratch marketplace with reviewer `rita`, a pushed `porch-temp`
template published, approved, and installed in a scratch Prahari through
a scratch Vidhi that trusts `rita`; then `rita` took the review back:

```
$ prahari indriya install porch-temp --from-market
added indriya porch-temp from porch-temp (signed by rita): keeps the porch temperature, pushed in to the inlet as porch-temp (a value expected at least every hour)
$ vidhi market revoke porch-temp --version 1 --why "it asks for your street address" --key rita --as rita
porch-temp v1: review taken back by rita (it asks for your street address); ...
$ vidhi market check
taken back: porch-temp v1 by rita
$ prahari serve --port 8812          # a few seconds: the clock's first tick
$ prahari indriya list
ac82ab77  paused  porch-temp: not read yet [paused: review taken back by rita (template porch-temp version 1): it asks for your street address]
$ prahari indriya resume porch-temp
error: porch-temp is paused: review taken back by rita (template porch-temp version 1): it asks for your street address. It stays paused as it was; mend it (prahari indriya edit porch-temp) to make it your own, or remove it
$ prahari indriya edit porch-temp --pick json:reading
updated indriya porch-temp: ...
$ prahari indriya list
ac82ab77  active  porch-temp: not read yet
```

## Not here

* **A template that makes watches too.** A template makes a reading.
  What to do about its value is the person's, a watch at a time.
* **Updating an installed reading to a template's new version.** It was
  filled in once; a new version is installed again, under its name.
* **Blanks of other kinds** (a Setu account, a list). Numbers and words.
* ~~**A reading paused when its template's review is taken back.**~~
  Paused by the clock within the hour (above, and the receipt below).
