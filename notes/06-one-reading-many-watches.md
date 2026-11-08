# 06 — One reading, many watches

The guestroom band — *heat below 60 °F outside, cool above 70 °F* — is
two watches ([05](05-a-look-says-why.md#a-band-is-two-watches)). Each
one called the weather service every hour with the same address, so
there were two calls where one would do. Each call is another chance to
be refused, and for a minute after one watch has looked and the other
hasn't, the two can disagree about what the temperature is. Add a third
watch on the humidity from the same answer, or have the agent asked
"how cold is it out?", and that's three or four calls for one number.

Continues [05 — a look says why](05-a-look-says-why.md) and the rules of
[01 — a watch with no model](01-a-watch-with-no-model.md).

## An indriya is the looking half of a watch

A watch did two jobs. It **looked**: a check, a pick, an `every`. And it
**decided**: a `when`, and what to do then. An **indriya** (इन्द्रिय,
*a sense*, the faculty that takes in the world as eye, ear and touch
do; said *in-dree-yuh*) is the looking half on its own:

```bash
prahari indriya add outside-temp --check web_fetch \
  --args '{"url": "https://api.open-meteo.com/v1/forecast?latitude=35.79&longitude=-78.78&current=temperature_2m,relative_humidity_2m&temperature_unit=fahrenheit"}' \
  --pick json:current.temperature_2m --thing "the outside temperature" --every 15m
```

It reads on its own `every`, with no model, on the same roads and grants
a watch's check uses. It keeps the value it took, with a time on it, and
its last 500 readings. It decides nothing and tells nobody anything.

A watch then **senses** it instead of looking:

```bash
prahari add "Heat the guestroom" --sense outside-temp --when 'below 60'
prahari add "Cool the guestroom" --sense outside-temp --when 'above 70'
```

So a watch either looks (`--check`), listens at the inlet (`--listen`)
or senses an indriya (`--sense`): exactly one of the three. One that
senses has no check, `every` or `wake` of its own; how often belongs to
the indriya, and asking to change it on the watch says where to go
instead (`prahari indriya edit outside-temp --every 30m`).

## The rules

**A READING IS A LOOK WITH NO DECISION.** The indriya runs its call
exactly as a watch's check would run, on the same road (here, or through
Dvara as its person) with the same grant. A bot check, a refusal or a
sign-in wall are caught the same way too. What it keeps is what its pick
took out of the answer.

**THE WATCH DECIDES ON THE WHOLE ANSWER.** Each sensing watch is handed
the indriya's full answer and judged by the same code that judges a
watch that looked itself: the first look only learns, a line fires on
its edge, items are news by key, `ask` asks last, `stop` ends it. So a
watch can pick something else out of the same call (`--pick
json:current.relative_humidity_2m`), and with no pick of its own it
takes the indriya's.

**A FAILED READING IS SAID ON EVERY WATCH, AND COUNTED ONCE.** When the
call fails, each sensing watch gets a `failed` look whose why says
*"Its indriya outside-temp could not read (failed), so nothing was
decided"*, so "why so quiet?" has its answer on the watch where you'd
look for it. The count is the indriya's alone: three in a row pause the
indriya, and its owner is told which watches went quiet with it. The
watches stay active, and pick up again on the first good reading after
`prahari indriya resume`. Counting against each watch as well would have
paused three watches for one broken call, and each one's message would
have blamed itself.

**AN INDRIYA IN USE IS NOT REMOVED.** `prahari indriya rm` names the
watches that sense it and stops. Pulling a reading out from under a
watch would leave it quiet for good, and that looks exactly like
"nothing happened".

**A NEW CALL OR PICK STARTS ITS WATCHES OVER**, as mending a watch does:
what they remembered was picked from the old answer. A new `every`
forgets nothing.

**ONE NAME, ONE CALL, PER PERSON.** An indriya is called by one short word
(`outside-temp`) because an agent asks for it by name and a person types
it. A second indriya with the same call is refused, naming the first,
for the same reason as two watches on one fare. A cap of 30 per person
(`$PRAHARI_MAX_INDRIYAS`) is there because each one starts a program on
its own clock.

**SHARING SHARES THE VALUE, NOT THE ACCOUNTS.** An indriya reads with its
owner's accounts. `--share house` lets anyone's watches and agents read
its value. It never lets them call anything as the owner, or change the
indriya: theirs is to read. It starts as `mine`, because the outside
temperature is fine to share and unread mail from the bank should be
shared only on purpose. A person's own indriya wins over a house one with
the same name. Taking `house` back is refused while someone else's watch
senses it.

## Three doors, none of them Prahari's own

A reading is no use if only Prahari can see it. It can be reached three
ways, and those three are the whole contract. Nothing that reads one
depends on how Prahari keeps it:

| Who's asking | Door |
|---|---|
| any agent: the Yantra page, a Dvara chat, Telegram, the puck, a Samay run | `list_indriyas` and `read_indriya` on `prahari mcp`, which Yantra already attaches to every turn |
| a page, Home Assistant, a script that speaks HTTP | `GET /api/indriyas`, `/api/indriyas/NAME`, `/api/indriyas/NAME/readings` |
| a terminal | `prahari indriya get NAME --json` |

`list_indriyas` tells the model so in its description: when a fresh
reading answers what the person asked, answer from it instead of calling
the tool again. The agent can also make one (`create_indriya`), from a
tool it already has: preview the call and pick first, tell the person
what it sees, and save only on their yes. It writes a definition, never
code that runs every fifteen minutes.

## Live receipt

The band and a humidity watch on one indriya, in a scratch state folder,
looking through the house's Yantra (`yantra --call web_fetch`):

```
$ prahari indriya add outside-temp --check web_fetch --args '{"url": "https://api.open-meteo.com/…"}' \
    --pick json:current.temperature_2m --thing "the outside temperature" --every 15m
added indriya outside-temp: reads the outside temperature every 15 minutes:
looks at api.open-meteo.com/v1/forecast (with web_fetch)
watches decide on it with: prahari add NAME --sense outside-temp --when ...

$ prahari add "Heat the guestroom" --asked "heat the guestroom when it gets below 60 outside" \
    --sense outside-temp --when 'below 60'
added 29fa64b3: Heat the guestroom -- senses outside-temp (every 15 minutes); tells
you when the outside temperature is below 60 (once each time it becomes true)
$ prahari add "Cool the guestroom" --sense outside-temp --when 'above 70'      # 7f184479
$ prahari add "Damp outside" --sense outside-temp \
    --pick json:current.relative_humidity_2m --thing "the humidity" --when 'above 50'   # 63e8fd74

$ prahari indriya look outside-temp
Sun 8 Nov 17:23  read       56.9
29fa64b3  Sun 8 Nov 17:23  fired      56.9  then: told
              • the outside temperature is now 56.9
              why: The outside temperature is 56.9, so it is below 60, and it did not last time
7f184479  Sun 8 Nov 17:23  learned    56.9
              why: The first look: the outside temperature is 56.9, which is not what it waits for (is above 70)
63e8fd74  Sun 8 Nov 17:23  fired      57  then: told
              • the humidity is now 57
              why: The humidity is 57, so it is above 50, and it did not last time

$ prahari indriya list
98a752ef  active  outside-temp: 56.9 (just now)
          reads the outside temperature every 15 minutes: looks at api.open-meteo.com/v1/forecast (with web_fetch)
          sensed by: 29fa64b3 (Heat the guestroom), 7f184479 (Cool the guestroom), 63e8fd74 (Damp outside)
```

One call out; three watches decided. The humidity watch picked its own
number, 57, out of the same answer. The same reading through the other
two doors, from `prahari serve` and a real `prahari mcp` process:

```
$ curl -H "Authorization: Bearer …" http://127.0.0.1:8784/api/indriyas/outside-temp
{"name": "outside-temp", "value": "56.9", "age": "just now",
 "sensed_by": [{"name": "Heat the guestroom"}, {"name": "Cool the guestroom"}, {"name": "Damp outside"}], …}

tools/call list_indriyas  →
outside-temp: 56.9 (just now) -- reads the outside temperature every 15 minutes:
looks at api.open-meteo.com/v1/forecast (with web_fetch)
```

## The tradeoff accepted

`prahari mcp` has fifteen tools now, up from ten, and every turn that
has Prahari's tools carries all of them. Choosing among tools gets
measurably worse past about ten (Yantra's notes/17), so this costs
something on small local models. The five are kept to what a
conversation needs (list, read, create, mend, delete). Pausing an
indriya and reading it now are left to the page and the terminal.

A host that trusts Prahari's reads by exact name (Yantra's
`trusted_reads`, Dvara's `trusted`, which take no wildcards) needs
`mcp__prahari__list_indriyas` and `mcp__prahari__read_indriya` added to
trust them too. Naming the whole server (`prahari`) covers them already.

## What was deliberately not built

* **Moving existing watches onto an indriya by themselves.** A new watch
  on the same call as an indriya is not yet turned into one that senses
  it, and the live guestroom pair still looks twice. Doing that silently
  would change watches the person agreed to. It comes with a way to say
  it in words first.
* **A read that asks for fresh.** `read_indriya` answers with the value
  and its age; "no older than 5 minutes, else look now" needs a cap on
  how often a reader can make it look, and waits for one.
* **Values pushed in.** A Home Assistant thermometer posting its value
  to the inlet, instead of being looked at, belongs here and isn't here
  yet.
* **Pausing an indriya nobody senses.** A watch with no end asks once a
  month whether it's still wanted; an unused indriya doesn't yet.
* **Code.** An indriya, like a recipe, is a call, a pick and a time. A
  source with no tool gets an MCP server through Setu, written or
  installed once, not a script that Prahari runs.
