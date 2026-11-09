# 07 — One call, by itself

[06](06-one-reading-many-watches.md) made the indriya: one call, read by
every watch that senses it. But that only worked when someone knew to
make one. A watch written the usual way, `--check web_fetch` on the
weather address, still called the weather on its own beside an indriya
making the very same call. The guestroom pair, made before indriyas
existed, still made two calls an hour. A reader who wanted the value
*now* could only take what was kept, however old. And an indriya whose
last watch was removed went on calling every fifteen minutes, with its
owner's accounts, for nobody.

## A new watch goes by the reading

A watch made on exactly the call an indriya already makes (same tool,
same arguments) **senses that indriya instead**, and says so:

```
$ prahari add "Damp outside" --check web_fetch --args '{"url": "…open-meteo…"}' \
    --pick json:current.relative_humidity_2m --when 'above 90' --every 5m
added c0fb0bf0: Damp outside -- senses outside-temp (every 5 minutes); tells you when
the humidity is above 90 (once each time it becomes true)
  It goes by the reading outside-temp, which already makes this call, instead of calling again
  outside-temp now reads every 5 minutes (it read every 15 minutes), as often as this watch asked
```

**THE FASTEST NEED SETS THE PACE, FOR YOUR OWN.** The watch asked to look
every 5 minutes, and a watch that senses has no pace of its own. So the
person's own indriya speeds up to the fastest watch's pace. That is what
the person asked for, and it still makes only one call each time. It
never goes below the five-minute floor every call has. It doesn't slow
down again when that watch is removed, because a slower pace is a choice
someone else may have made. `prahari indriya edit NAME --every` is how to
change it.

**SOMEONE ELSE'S READING IS THEIRS TO PACE.** A house indriya kept by
someone else is used only if it already reads at least as often as the
watch asks. If it's slower, the watch looks itself and says why (*"asha's
reads this same call every 1 hour, less often than asked"*). One person's
new watch shouldn't make another person's accounts call four times as
often.

**A PRIVATE OR PAUSED READING IS NOT TAKEN.** Someone else's private
indriya isn't visible, so it's never found. A paused one would leave the
watch silent, so the watch looks itself and says that too.

`--look-itself` (`look_itself: true` for the agent) keeps the old way,
for the rare watch that wants its own call. The preview says the same
thing before the person's yes, so the agent's card for a watch about to
go by a reading says, in capitals, *BUT A READING ALREADY MAKES THIS
CALL … No second call is made*.

## Watches made before it move on your word

Prahari doesn't move a watch the person already agreed to on its own.
It says which watches could move and how:

```
$ prahari indriya add outside-temp --from-watch aa5afa6c --every 15m
added indriya outside-temp: reads the outside temperature every 15 minutes: …
watches of yours on this same call (each still calls itself):
  aa5afa6c  Heat the guestroom
  f243cf84  Cool the guestroom
move them with: prahari edit ID --sense outside-temp   (or add again with --move)
```

`--from-watch` takes the watch's call, pick, thing, road and pace (or the
`--every` given). `--move` moves them all at once, and `prahari edit ID
--sense NAME` moves one. For the agent, these are `create_indriya` with
`from_watch` (and `move`), and `update_watch` with `sense`. Each gets a
card that says the watch stops making its own call.

**WHAT IT REMEMBERED IS KEPT WHEN THE ANSWER IS THE SAME.** A watch that
moves onto an indriya making its own call, with the same pick, is handed
exactly the value it compared against before. So it keeps its memory:
the heat watch that already told you *below 60* stays waiting for the
temperature to come back up, instead of learning again. A watch moved
onto a *different* call starts over, as any mended recipe does, because
its memory was picked from another answer.

**MOVING IS A CHANGE OF ITS OWN.** `--sense` goes alone (a new name may
come with it). Moving and changing the test in the same breath would
leave the person unable to say which of the two made it fire.

## Fresh on asking

`read_indriya` answers with what is kept and its age. A question that
needs *now* (*"I'm about to go out"*) gives `max_age`. The same option is
`prahari indriya get --max-age 5m`, and `?max_age=5m` on the API. If the
kept value is older than that, it's read again first, with the call the
person already said yes to.

**NOT WITHIN FIVE MINUTES, WHOEVER ASKS.** The last reading's time counts
whether the clock made it or another reader did. A chat asking in a loop
can't turn a fifteen-minute reading into a call a second. When it's too
soon, the answer is the kept value and why it wasn't read again (*"it
was read just now, and a reading is not made again within 5 minutes"*).

**A FRESH READ ONLY READS.** It keeps the value and adds a reading whose
why starts *Asked for fresh by a reader*. It isn't handed to the
watches, because a watch that fires might start a turn, and the reader's
question would wait minutes on it. It doesn't count against the
indriya, and it doesn't move the clock. The next reading on the clock
decides for the watches, as always. If a fresh read fails, the answer is
the kept value, said as kept.

## Unused, it stops

Every reading a watch decides on, and every reader that asks for the
value (`read_indriya`, `get`, the API's one-indriya answer), marks the
indriya used. Listing doesn't count, because Yantra lists them on every
turn. After **30 days** with neither, the clock pauses it instead of
reading, and tells the owner, the same way a watch with no end asks
once a month. `resume` starts its month again.

## Live receipt

A scratch state folder, the house's Yantra looking (`yantra --call`),
and the real weather address. The guestroom pair, made the old way:

```
$ prahari look aa5afa6c            # Heat the guestroom, looking itself
Mon 9 Nov 07:29  fired      46.4  then: told
$ prahari look f243cf84            # Cool the guestroom
Mon 9 Nov 07:29  learned    46.4

$ prahari indriya add outside-temp --from-watch aa5afa6c --every 15m   # lists both
$ prahari edit aa5afa6c --sense outside-temp
updated aa5afa6c: Heat the guestroom -- senses outside-temp (every 15 minutes); …
$ prahari edit f243cf84 --sense outside-temp

$ prahari indriya look outside-temp
Mon 9 Nov 07:29  read       46.4
aa5afa6c  Mon 9 Nov 07:29  quiet      46.4
              why: The outside temperature is 46.4: it still is below 60, as it did last
              time. It told you when that became true, and tells again only after it has
              stopped being true in between
f243cf84  Mon 9 Nov 07:29  quiet      46.4
```

One call where there were two, and the heat watch didn't tell you
46.4 °F a second time. Then a third watch, on humidity, written the old
way (above): it went by the reading by itself and sped it up to five
minutes.

Fresh, at the terminal, right after that reading:

```
$ prahari indriya get outside-temp --max-age 0
  (not read again: it was read just now, and a reading is not made again within 5 minutes)
```

And a local model (`qwen3.8:latest`). The kept value's time was moved an
hour back by hand, so that "current" would need a new reading:

```
$ yantra --provider ollama --model qwen3.8:latest --prompt \
    "Is it colder than 50 outside right now? I'm about to go out, so it has to be current."
→ mcp__prahari__list_indriyas()
→ mcp__prahari__read_indriya()   {"name": "outside-temp", "max_age": "5m"}
  outside-temp: 45.7 (just now) -- reads the outside temperature every 5 minutes: …
  (read again just now, as asked)
Yes — it's 45.7°F right now (freshly read), so that's colder than 50. You'll want a jacket.
── end_turn · 13802 in / 371 out · 3 iteration(s)
```

The model chose `max_age` itself, from *"it has to be current"* and the
prompt's one line about it. There was one weather call, made by Prahari
with the call already agreed to. An earlier run of the same question
took seven steps; only its end was kept, so what the extra steps were
isn't known.

## Not here

* **Slowing back down.** An indriya sped up for a watch stays fast after
  that watch is removed. Working out the slowest pace that still serves
  everyone would mean keeping each watch's wish. A person who wants it
  slower says so with `--every`.
* **A floor for each site.** Every call has the same five-minute floor.
  A weather service that asks for fifteen would need a per-site list,
  which nobody has needed yet.
* **Moving a watch back off a reading.** A watch that senses can't be
  given its own call again. Remove it and make it anew with
  `--look-itself`.
* **Values pushed in** (a Home Assistant thermometer posting to the
  inlet) still belong here and still aren't here.
