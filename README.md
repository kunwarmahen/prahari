# prahari — tells your agent when something happens

"Tell me when ALAB drops under $50."
"Tell me when a mail from the bank arrives."
"When Mum messages me on WhatsApp, read it to me and draft a reply."

An agent can check any of those once, while you watch. [Samay](https://github.com/kunwarmahen/samay)
can run a check on a schedule, but every run is a whole agent turn: a
model is asked, every hour, to look and say whether anything changed.
Ninety-nine looks in a hundred find nothing, and you pay for all of
them.

**Prahari** watches without a model. Your agent writes a small
*recipe* once, out of tools it already has: which tool to look with,
what to pick out of its answer, and when that matters. Prahari repeats
the look on its own, with no model, and wakes the agent only when the
thing you were waiting for happens. Things that can tell you
themselves, like a phone that just got a notification or a webhook,
knock on Prahari's **inlet** instead, and the same recipe decides.

## The name

**prahari** — प्रहरी (Sanskrit *praharī*; said roughly *pruh-huh-ree*).

A *prahari* is the guard on watch, the sentinel at the gate. The word
comes from *prahara*, a watch of the day or night: the old Indian day
was cut into eight *praharas* of three hours, and a *prahari* kept one.
He doesn't do the household's work. He watches, and when the thing he
was set to watch for comes, he calls whoever must act. That is this
program's whole job.

```
             ┌──────────────────────────────────────────────┐
  a recipe   │  check   one tool call that reads             │
  (the agent │  pick    what to take out of its answer       │
   writes    │  when    below 50 · new · contains Mum · …    │
   it once)  │  every   how often to look                    │
             └──────┬───────────────────────────▲───────────┘
                    │ every 3h, no model         │ an event (the inlet):
                    ▼                            │ MacroDroid, Home Assistant,
       yantra --call TOOL --args JSON            │ a webhook
                    │                            │
                    ▼                            │
          pick → when ── no ──▶ quiet (a row in the logbook, nothing else)
                    │
                   yes
                    ▼
     a line to you (no model)   or   a Yantra turn with `then`
                    └──────── through Dvara, to your chat ────────┘
```

**Prahari never does the work itself.** Every look is one tool call
made by Yantra with no model (`yantra --call`, [Yantra's note 139](https://github.com/kunwarmahen/yantra/blob/main/notes/139-one-tool-no-model.md)),
and when a watch fires, the work is an ordinary Yantra turn. Prahari
starts Yantra as a program and reads the JSON it prints. It imports
nothing from Yantra and has no dependencies of its own.

How it's built, and why: [01 — a watch with no model](notes/01-a-watch-with-no-model.md).

## Works with

* **[Yantra](https://github.com/kunwarmahen/yantra)** makes every look (`yantra --call`) and every
  then-turn (`yantra --json --unattended`). Yantra also finds Prahari by
  itself: with `prahari` on `PATH`, the agent gets the tools to offer
  "I'll tell you when that happens", and you approve each watch on a card
  that says in words what it looks at, how often, and what happens then.
* **[dvara](https://github.com/kunwarmahen/dvara)** carries the news to you: answers go to your
  Telegram, Dvara's web chat and Sarathi's home page through Dvara's
  `/notify`. With `dvara --prahari`, the owner's agent can make a watch
  from the chat.
* **[Setu](https://github.com/kunwarmahen/setu)** is reached through Yantra: a look can use any
  account Setu keeps (a Gmail search, a signed-in site's page, Notion),
  exactly as a turn would.
* **[Sarathi](https://github.com/kunwarmahen/sarathi)** starts it with the rest (`[prahari]` in
  `sarathi.toml`), as a program or a Podman container, and links its
  page from the home page.

## Setup

```bash
uv sync
# Tell Prahari how to start Yantra, and where (Yantra reads .env from there):
export PRAHARI_YANTRA=~/yantra/.venv/bin/yantra
export PRAHARI_YANTRA_HOME=~/yantra
```

Looks need no model at all. The model in Yantra's `.env` is used only
when a watch fires with a `then`, or for a test that asks a yes/no
(`ask`). A local model on Ollama is fine for both: put
`YANTRA_PROVIDER=ollama` and `OLLAMA_MODEL=qwen3.8:latest` in Yantra's
`.env`.

## Using it

```bash
# try a recipe once, before saving anything: what it sees, in words
prahari preview --check mcp__gmail__search_threads \
    --args '{"account": "personal", "query": "from:alerts@bank.example newer_than:2d"}' \
    --pick 'items:thread (\w+)' --when new --every 30m
#   every 30 minutes, looks with mcp__gmail__search_threads; tells you when the list has something new
#   It sees 1 item(s) now; the first look remembers them, and only ones after that are news.

# save it
prahari add "Mail from the bank" --check mcp__gmail__search_threads \
    --args '{"account": "personal", "query": "from:alerts@bank.example newer_than:2d"}' \
    --pick 'items:thread (\w+)' --when new --every 30m

# a price, from a public JSON address, and the agent's view when it drops
prahari add "BTC under 60k" --check web_fetch \
    --args '{"url": "https://api.coinbase.com/v2/prices/BTC-USD/spot"}' \
    --pick 'json:data.amount' --when 'below 60000' --every 1h \
    --then "Tell me the price, and how far it fell this week."

# keep it running (nothing is looked at otherwise)
prahari serve
#   page: http://127.0.0.1:8782/#token=…     open this once; the browser keeps it
#   inlet: http://127.0.0.1:8782/inlet/WORD  (key: prahari inlet)

# see, try, mend, stop
prahari list
prahari looks                  # newest first, every watch
prahari show 1e69              # one watch in full (the first letters of its id will do)
prahari look 1e69              # look once, now, here -- and wait
prahari edit 1e69 --every 2h   # mend its check, pick, test, how often or then
prahari pause 1e69 | resume 1e69 | rm 1e69
```

A real run, against a real inbox and a real price (no model anywhere):

```
$ prahari look 9c7e7378
Thu 22 Oct 08:31  fired      81,633.9  then: told
    • the value is now 81,633.9
$ prahari look 9c7e7378
Thu 22 Oct 08:31  quiet      81,633.9
$ prahari look 1e691992
Thu 22 Oct 08:32  learned    1 item(s)
    the first look: what is there now is remembered
$ prahari look 1e691992
Thu 22 Oct 08:32  quiet      1 item(s)
```

The price watch fired on its first look because the price was already
below its line; the second look was quiet, because a test on a value
fires when it *becomes* true, not every time it *is* true. The mail
watch's first look only learned what was there.

Every command takes `--json`.

### A recipe

**check** — one call of a tool your agent has, with its arguments:
`{"tool": "mcp__gmail__search_threads", "args": {...}}`. It must be a
tool that only reads (a search, a site's page, a screenshot), or the
exact call you accepted: `web_fetch` of one address is allowed because
the watch's card showed you that address, and Prahari passes Yantra a
grant fixing every argument, so a fetch of any other address isn't.
Nothing is granted before you accept, so `preview` can only try a tool
that reads.

**pick** — what to take out of the answer:

| Short form | JSON | Takes |
|---|---|---|
| `number` | `{"number": ""}` | the first number |
| `number:Last\s*([\d.,]+)` | `{"number": "Last\\s*([\\d.,]+)"}` | the number a pattern finds (group 1), or the first one after it |
| `text:status: (\w+)` | `{"text": "status: (\\w+)"}` | a piece of text |
| `json:data.amount` | `{"json": "data.amount"}` | a value from JSON (`a.b[0].c`, `list[*].id`) |
| `items:thread (\w+)` | `{"items": "thread (\\w+)"}` | every match is an item; group 1 is its key |
| `items_json:messages[*]:id` | `{"items_json": "messages[*]", "key": "id"}` | items from a JSON list |
| (nothing) | `{}` | the whole answer |

**when** — when it matters:

| | |
|---|---|
| `below 50`, `above 50`, `at_most 50`, `at_least 50` | numbers; fires when it becomes true, and again only after it was false in between |
| `contains Mum`, `lacks In stock`, `equals shipped`, `matches REGEX` | text; the same edge |
| `changed` | the value isn't what it was last time |
| `new` | items not seen before (by their key) |
| `any` | every time (an inlet's event, usually) |
| `ask is this an invoice?` | a yes/no for a model, asked only about a value that changed or items that are new |

**every** — `30m`, `3h`, `1d`: five minutes at the least, seven days at
the most (less often than that is a schedule, and Samay's job).

**then** — what the agent is asked when it fires, with nobody watching.
Leave it out, and you get a line saying what was seen, with no model
asked at all.

A mistake is refused before anything is saved, with what to write
instead:

```
$ prahari add x --check t --when 'belw 50'
error: when is one of: below N, above N, at_most N, at_least N, equals X, contains X,
lacks X, matches REGEX, changed, new, any, ask QUESTION -- not 'belw 50'
```

### The inlet

Some things can tell you themselves. Your Android phone gets a
WhatsApp notification the moment Mum writes; a Home Assistant
automation knows the instant the door opens; a price tracker
(Keepa, CamelCamelCamel) can call a webhook. Polling any of those would
be slower and wasteful. Instead, they knock:

```bash
prahari add "Mum on WhatsApp" --listen whatsapp --pick json:title --when 'contains Mum' \
    --then "Read me what Mum said, and draft a reply I can send."
prahari inlet
#   send to:   POST http://127.0.0.1:8782/inlet/WORD
#   with:      Authorization: Bearer <key>
#      or:     http://127.0.0.1:8782/inlet/WORD?key=<key>
#   listening: whatsapp

curl -X POST "http://127.0.0.1:8782/inlet/whatsapp?key=<key>" \
     -H 'Content-Type: application/json' -d '{"title": "Mum", "text": "Dinner at 8?"}'
#   {"heard_by": 1}
```

**On an Android phone, with MacroDroid** (Tasker works the same way):

1. Trigger: *Notification received*, application WhatsApp (or any app).
2. Action: *HTTP request*, method POST, to
   `http://<your computer>:8782/inlet/whatsapp?key=<key>`, content type
   `application/json`, body
   `{"title": "[notification_title]", "text": "[notification]"}`.
3. Your computer's address is the one Sarathi's `[house]` name gives
   (`linux-al-ml-beast.local`), or its LAN address; the phone must be
   able to reach port 8782 (Sarathi's `up` prints the firewall line).

That's all: the phone tells Prahari, the watch decides, and the agent
answers in your chat. No polling, nothing unofficial logged in to
WhatsApp, and nothing read from your phone that you didn't send.

**The inlet's key can only knock.** It goes into apps and webhook
settings, where keys leak, so it isn't the page's token: with it,
something can be *said* to Prahari, and nothing can be read, made,
changed or deleted. What is said is matched against the watches you
already set up, and fires only those. It answers `202` at once, with
how many watches heard it; the deciding happens behind, because a test
that asks a model may take a minute, and a phone app sending a
notification shouldn't wait. The same body twice inside ten minutes is
one event (an `id` in the body, if the sender has one, is better). A
JSON object is read as it is, a form is made one, and anything else is
`{"text": ...}`; 16 KB at most.

`prahari hear WORD JSON` sends the inlet something on this computer
without the network, to try a watch before you set up the phone.

**What the inlet can't do.** An iPhone doesn't let other apps read its
notifications, so there's no WhatsApp road there. And Prahari doesn't
log in to WhatsApp itself: the unofficial WhatsApp Web clients that
would let it are against WhatsApp's terms, and personal numbers get
banned for them.

### The page

`prahari serve` serves a page at the address it prints: every watch in
words, when it looks next and what it saw last, with **Look now**,
**Pause** / **Resume**, **Looks** (its history) and **Delete**; the
inlet's address, its key behind **Show**, and the body for MacroDroid;
and **Lately**, the last looks across all watches. **New watch** writes
one by hand, and **Try it** looks once and says what it sees before
anything is saved.

![Prahari's page: three watches -- a price under a line, new mail, Mum on WhatsApp at the inlet -- then the inlet's address and key, then the latest looks, fired ones in teal](docs/page.png)

It listens on localhost only (`--host` to change that), and every API
request needs the page's token, for the reason Samay's page gives: any
website you visit can send a request to 127.0.0.1. The token comes
after the `#` in the printed address, which a browser never sends to a
server.

```
GET    /api/status                       is it watching; how many watches
GET    /api/watches                      every watch, with its last look
POST   /api/preview   {check|listen, pick, when, every, sample}   try it once
POST   /api/watches   {name, check|listen, pick, when, every, then, ...}
PATCH  /api/watches/ID   {check, pick, when, every, then, name, max_per_day}
POST   /api/watches/ID/pause | /resume | /look     (look answers 202 at once)
DELETE /api/watches/ID
GET    /api/looks?watch=ID&limit=N       newest first
GET    /api/inlet                        the inlet's address, key and words
POST   /inlet/WORD                       the inlet (its own key)
```

### Your agent writes the recipe

The best moment to set up a watch is in the middle of a conversation:
"let me know when that's back in stock". `prahari mcp` is an MCP server
with the tools an agent uses:

```bash
prahari mcp --for local --agent ~/agents/reader     # what a harness starts
```

| Tool | |
|---|---|
| `preview_watch` | looks ONCE (only with a tool that reads) and says what it sees, with the start of the tool's answer |
| `list_watches`, `watch_looks` | what this person is watching, and what each saw |
| `create_watch` | saves one, after the person agreed |
| `update_watch` | mends one: a site moved its price, so the pick needs changing |
| `allow_for_watch` | lets a watch's then-turn use a tool it was refused |
| `pause_watch`, `resume_watch`, `delete_watch` | |

**The agent writes the recipe; you accept it.** The three reading tools
say they only read, and the six that change something don't, so Yantra
asks you before each one, on a card in words. `preview_watch` comes
first and answers with the start of what the tool said, so a model whose
pick found nothing sees why and writes a better one before you are asked
anything.

**One person per server.** `--for`, `--agent` and `--runner` are the
harness's to set; the model has no argument with which to name anyone
else.

### The rules

Each one is there because of a way an unwatched watch goes wrong
([notes/01](notes/01-a-watch-with-no-model.md)):

| | |
|---|---|
| **The first look only learns** | a new "tell me about new mail" would otherwise fire on the whole inbox. A test on a value ("below 50") is about now, so if it's already true you hear at once |
| **A test on a value fires on its edge** | "below 50" tells you once when the price goes under, not every three hours while it stays there |
| **New is by key** | the same mail is news once, across restarts |
| **Ask the model last** | `ask` sends only what changed or is new, never the whole answer every look |
| **A broken check never fires** | a tool that failed, or a pick that found nothing (the site moved its price), is `failed` or `broken`, never quiet. Three in a row pause the watch, and you're told how to mend it |
| **A sign-in wall pauses at once** | an expired login doesn't fix itself before the next look |
| **A limit per day** | at most `max_per_day` fires (10 unless you say) in any 24 hours; past it, kept and not run, and you're told once |
| **A late look is just a look** | asleep at the due time, Prahari looks once when it wakes; it never replays a backlog |
| **What was found is outside text** | the then-turn is given it inside a block marked as text to read and never to obey: a mail or a page can say anything |

### Where news goes

With `PRAHARI_DVARA_URL` set, a fire is sent to the watch's person
through Dvara (`POST /notify`): their Telegram, Dvara's web chat,
Sarathi's home page. A watch made at this computer (`local`) goes to
`PRAHARI_DVARA_ACTOR`; Sarathi sets it to its owner. Without a Dvara,
looks are kept for `prahari looks` and the page, and nothing is sent.

A then-turn runs here (`--runner direct`, the default: Yantra as a
program, its questions put to you in your chat when a Dvara is set) or
through Dvara as a person (`--runner dvara --as NAME`: their allowance,
their rules, `came_by: prahari` on Dvara's page).

## Settings

| Variable | What |
|---|---|
| `PRAHARI_STATE` | where watches and looks are kept (default `~/.prahari`; also `--state`) |
| `PRAHARI_YANTRA` | the command that starts Yantra; may be several words |
| `PRAHARI_YANTRA_HOME` | the folder Yantra starts in, for its `.env` |
| `PRAHARI_DVARA_URL`, `PRAHARI_DVARA_TOKEN` | where Dvara is, and its `DVARA_TOKEN`: news is sent, and `--runner dvara` works |
| `PRAHARI_DVARA_ACTOR` | who a watch made here is for |
| `PRAHARI_MAX_WATCHES` | how many watches one person may have (default 30) |
| `PRAHARI_TOKEN` | the page's token, instead of the one kept in the state folder |
| `PRAHARI_INLET_TOKEN` | the inlet's key, instead of the one kept in the state folder |
| `PRAHARI_PUBLIC_URL` | where a browser reaches the page when that isn't where it is bound (a container's port mapping) |

Everything is in one SQLite file, `~/.prahari/prahari.sqlite3`. Each
watch's looks work in a folder of their own, `~/.prahari/work/<id>`.

### Keeping it running

```bash
prahari unit --install        # a systemd user unit, and an env file (yours alone)
systemctl --user daemon-reload
systemctl --user enable --now prahari
```

`--install` copies this shell's `PRAHARI_*` and `YANTRA_*` settings and
its `PATH` into `~/.config/prahari/prahari.env`, readable by you alone;
it starts nothing. Sarathi users don't need this: `sarathi up` runs it.

## The source

```
src/prahari/
├── recipe.py    the recipe's form: pick (number, text, json, items) and when
│                (below, contains, changed, new, any, ask), checked with
│                the known keys named, and applied to a tool's answer
├── store.py     the SQLite file: watches (the promise), looks (the receipt),
│                seen (keys already told)
├── watches.py   make, mend, pause, find, a cap per person; preview, which
│                looks once with nothing granted
├── clock.py     the rules above; the loop prahari serve runs; the inlet's
│                events; firing: a line, or a then-turn with what was found
│                marked as outside text
├── looking.py   Yantra as a program: the look (yantra --call, granted word
│                for word), the yes/no for ask, the then-turn (Samay's
│                direct road)
├── dvara.py     the Dvara road: /notify for news, /message for a turn as
│                the person (came_by prahari). Standard library only
├── http.py      the page, its JSON API (the page's token), and the inlet
│                (a key of its own that can only knock)
├── static/      the page: one file and its icon, nothing fetched
├── mcp.py       the agent's tools, for one person (stdio MCP, by hand)
├── status.py    prahari status --json: here, watching (a lock, not a pid)
├── unit.py      prahari unit: a systemd user unit
└── cli.py       the commands above
```

## Status

The watch, its rules, the inlet, the page and the agent's tools work,
and are covered by 106 tests. The API is not stable.

Not here yet:

* **Watches for other people in the house.** A look runs this computer's
  Yantra, with the owner's accounts; another person's watch would need
  their own (a look through Dvara as that person). For now, Dvara offers
  the tools to its owner only.
* **Mail pushed, not polled.** IMAP IDLE (any mail server) and Gmail's
  push through a Pub/Sub pull subscription would tell Prahari about a
  mail within seconds, with no public address. A look every 15–30
  minutes is the road for now; the push roads would sit behind the same
  check.

## Tests

```bash
uv run pytest -q          # offline: a fake caller, a fake runner, a fake
                          #   yantra on a real process, the page and the inlet
                          #   on local sockets, and prahari mcp as a real process
```
