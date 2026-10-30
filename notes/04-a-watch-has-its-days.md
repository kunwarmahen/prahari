# 04 — A watch has its days

A watch on the fare for Saturday's flight is no use on Sunday. A watch
on tomorrow's flight is no use today, and none once it lands. Most of
what people ask to be told about has days; a watch that ignores them
goes on looking, and telling, about something that is over.

Continues [03 — a watch says what it is for](03-a-watch-says-what-it-is-for.md).

## What a watch keeps

**`starts`** — when it begins. Before then it makes no look and hears
nothing at the inlet; its first look is due at the start, and that look
only learns, as every first look does.

**`ends`** — when it stops by itself.

**`stop`** — a test on what it sees that ends it: a flight's status
`{"contains": "Landed"}`. Only a test on the value now (below, above,
contains, equals …): "changed" can't say the thing is over. What it saw
on that look is told first, then that it ended.

Times are ISO 8601 with the person's offset (`2026-10-31T23:59-04:00`),
kept in UTC and said back on this computer's clock (`until Sat 31 Oct
23:59`). An agent works them out from what was said — "this Saturday",
"tomorrow morning" — and the card, the puck's sentence and the list all
say them, so the person hears the days before saying yes.

## When the end comes

**ENDING NEEDS NO YES.** The person agreed to the end when they agreed
to the watch, and a watch that stops looking can do no harm. So the
clock ends it — state `ended`, no more looks — and says so, with what
they asked:

```
Ended: BTC this minute
Its end came (Fri 30 Oct 13:21), as was set.
You asked: "watch bitcoin for the next minute only"
It looks no more. It's kept 30 days, then removed; to keep it going, ask me to keep watching (prahari edit bd781246 --keep).
```

**AN ENDED WATCH IS KEPT, THEN REMOVED.** Thirty days, to look back at
or to bring back; then the clock removes it with its looks, so a list
of ended watches doesn't grow forever. `keep` brings one back (its old,
passed end is dropped); so does a new `ends` or `starts`.

**ONE WITH NO END ASKS, ONCE A MONTH.** A watch with no `ends` and no
`stop`, thirty days after it was made or last kept, asks once: *Still
want this?* It goes on looking — the question stops nothing — and
`keep` quiets it for another thirty days. The point is the watch the
person forgot they had, still looking at a page that has nothing more
to say.

All of this is the clock's, with no model: a tick ends what is due,
asks what is due, and removes what has been ended long enough, before
it looks at anything.

## Live receipt

The real clock (`Clock.serve`), a scratch state, one real `web_fetch`
look at Coinbase through Yantra; a watch made at 13:19:17 to start a
minute later and end a minute and a half after that:

```
13:19:17 made: BTC this minute -- every 5 minutes, looks at api.coinbase.com/v2/prices (with web_fetch); tells you when BTC's price is below 200,000 (once each time it becomes true); from Fri 30 Oct 13:20; until Fri 30 Oct 13:21
--- 13:20:25 sent:
BTC this minute:
• BTC's price is now 77,123.04
You asked: "watch bitcoin for the next minute only"
(tells you when BTC's price is below 200,000; looks at api.coinbase.com/v2/prices every 5 minutes · watch bd781246)
--- 13:21:47 sent:
Ended: BTC this minute
Its end came (Fri 30 Oct 13:21), as was set.
…
look: 2026-10-30T17:20:17+00:00 fired 77,123.04
state: ended -- every 5 minutes, looks at api.coinbase.com/v2/prices (with web_fetch); …; until Fri 30 Oct 13:21; ended Fri 30 Oct 13:21
```

Nothing was looked at before 13:20; one look, which fired (the price was
already below the line); the end came between two looks and was said at
once, not at the next one.

## What was deliberately not built

* **A yes to end.** Asked for, and decided against with the person: the
  end was agreed with the watch, and asking again is a question nobody
  needs at the moment something stopped mattering.
* **Words for a time.** "Tomorrow morning" is the agent's to turn into a
  time; Prahari takes ISO, and refuses anything else in words, so a
  time is never guessed at by a program with no idea where the person
  is.
* **Ending on "changed" or "new".** Neither says the thing is over.
