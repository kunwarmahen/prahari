# 12 — A pace given back

[07](07-one-call-by-itself.md) let one reading serve every watch on its
call, and let the fastest watch set its pace. It left five things for
later, and the readings history of [08](08-a-value-sent-in.md) and
[09](09-what-happened-to-a-reading.md) left two more:

* a reading sped up for a watch stayed fast after the watch was gone;
* every site got the same five-minute floor, wanted or not;
* a watch that sensed a reading could never make the call itself again;
* a pushed value was dated when it arrived, not when it was measured;
* readings made before looks kept which one they judged showed no
  watches at all.

All five are here now. They share one idea: **what someone asked for is
kept, so it can be given back when they stop asking.**

## Slower when the need goes

**A WATCH KEEPS THE PACE IT ASKED FOR.** A watch that goes by a reading
has no pace of its own, but it still asked for one. *"Look every 5
minutes"* is kept on the watch (`wants_every`), and the reading keeps the
pace its owner set (`own_every`). The reading runs at the faster of the
two, as before.

**WHEN THE WISH GOES, THE PACE COMES BACK.** When a watch that sped a
reading up is removed, ends, or goes back to looking itself, the reading
slows to the slowest pace that still serves everyone left. That's the
owner's own pace, or the fastest wish still standing:

```
$ prahari rm b72897ae          # Cold snap, which asked for every 5 minutes
removed b72897ae
  outside-temp now reads every 10 minutes (it read every 5 minutes), as often as the
  fastest watch still on it asks
```

A paused watch still counts, because it comes back. A watch that ends
doesn't, and a watch kept going again asks for its pace again.

**THE OWNER'S `--every` IS THE LAST WORD.** `prahari indriya edit NAME
--every 30m` sets the pace to come back to. A watch's wish faster than
that is lowered to it, because the person who keeps the reading just
said how often it should call. A watch that wants something faster can
look itself.

**NOBODY GUESSES A PACE THAT WASN'T KEPT.** A reading made before its
owner's pace was recorded isn't slowed down, because nobody knows what
that pace was. Its first speed-up records the pace it had, so it can
come back to that one. `prahari indriya get` says it in a line when the
two differ (*"you set every 15m; a watch on it asked for 5m, and it
comes back when they go"*).

## A floor for each site

**A SITE MAY ASK FOR MORE THAN FIVE MINUTES.** A free weather service may
want one call in fifteen minutes from one address. A shop that turns bots
away is kinder to everyone when it's asked once an hour. A floor is kept
once, for the site, so nobody has to remember it at every watch:

```
$ prahari floor set open-meteo.com 10m --why "a free tier: be kind"
open-meteo.com is called no more than once every 10 minutes (a free tier: be kind)
  indriya outside-temp now reads every 10 minutes (it read every 5 minutes)
```

**A SITE IS AN ADDRESS'S HOST, OR A TOOL'S NAME.** A call whose arguments
carry a web address is on that address's host, and a floor for
`open-meteo.com` covers `api.open-meteo.com` too. A call with no address
(a mail search, a Home Assistant tool) is on its tool, so
`mcp__homeassistant-home__get_state` can have a floor of its own.

**ASKED OF NEW THINGS, MADE TRUE OF OLD ONES.** Setting a floor slows
whatever already calls that site faster, and says which ones (above).
A new watch or reading that asks for more is refused, and the refusal
names the floor:

```
$ prahari add "Too eager" --check web_fetch --args '{"url": "https://api.open-meteo.com/…"}' \
    --pick json:current.temperature_2m --when 'below 0' --every 5m
error: this watch would call every 5 minutes, but open-meteo.com is called no more than
once every 10 minutes (a free tier: be kind): every 10m or slower (prahari floor list)
```

A watch that asks a reading to speed up past the floor still goes by
the reading, and is told the reading stops at the floor. A reader asking
for a fresh value waits for the floor too, and is told so.

Floors belong to the house, not to a person. The site doesn't care whose
account is calling, only how often its address is asked.
`prahari floor list`, `set`, and `rm` (back to five minutes).

**THE SAME FLOORS FROM A PAGE.** `GET /api/floors`, `POST /api/floors
{site, every, why}` and `DELETE /api/floors/SITE` do what the three
commands do, behind the page's token, and answer with the same words
(the floor, and a line for each watch or reading slowed). Sarathi's
Settings → Sarathi → *Prahari: how often a site may be called* asks them,
so a floor can be kept without a terminal. Nothing about a floor is the
page's to decide: a site Prahari can't read is refused there in Prahari's
words.

```
$ curl -s -X POST -H "Authorization: Bearer $TOKEN" localhost:8782/api/floors \
    -d '{"site": "https://api.open-meteo.com/v1", "every": "15m", "why": "free tier"}'
{"site": "api.open-meteo.com", "every": "15m", "why": "free tier", ...,
 "said": "api.open-meteo.com is called no more than once every 15 minutes (free tier)",
 "slowed": ["watch f303989c (rain soon) now looks every 15 minutes (it looked every 5 minutes)"]}
```

## Back to its own call

```
$ prahari edit ea7bec47 --look-itself
updated ea7bec47: Hot day -- every 10 minutes, looks at api.open-meteo.com/v1/forecast
(with web_fetch); tells you when the outside temperature in °F is above 90 (once each
time it becomes true)
  outside-temp now reads every 15 minutes (it read every 10 minutes), as you set it
```

The watch takes back the reading's call, keeps its own pick, and goes
back to the pace it asked for (or the reading's, if it never asked for
one). Then the reading may slow down.

**WHAT IT REMEMBERED IS KEPT.** Its pick was always applied to the very
answer this call gives. So the value it last compared against is still
the right one to compare against: a heat watch that already said
*below 60* stays waiting for the temperature to come back up, instead of
learning again and telling you twice.

**ONLY YOUR OWN READING'S CALL.** A house reading kept by someone else
calls with their accounts, on their road. A watch can't take that over
as its own. It's refused in words (*"outside-temp is asha's: its call is
made with their accounts"*), and the way out is to remove the watch and
make it again on your own call. A pushed reading has no call to give
back, and says that.

**A CHANGE OF ITS OWN.** `--look-itself` goes alone (a new name may come
with it), as `--sense` does. Then the person can always say which change
made it fire. For the agent, it's `update_watch` with
`look_itself: true`.

## A value with its own time

A sender that queued values while the network was down can send each
one with its own time, as ISO 8601 with a zone or as seconds since 1970:

```
POST /inlet/indriya/guestroom-temp   {"value": 64.2, "at": "2026-11-09T22:09:06Z"}
```

**THAT TIME IS ITS AGE.** The reading's *at* stays the moment it
arrived. Its *measured* time is what the reading's age is counted from,
so `read_indriya` says *10 min ago* for a value measured ten minutes ago
that arrived just now. The deadline for the next value still counts from
arrival, because what that deadline checks is that the sender is alive.

**OLDER THAN WHAT IS KEPT IS HISTORY, NOT NEWS.** A value measured before
the one already kept is written into the history as **late**. It isn't
kept and it isn't handed to the watches, because a queue arriving out of
order must not fire a watch on the past:

```
$ prahari indriya push guestroom-temp 64.2 --at 2026-11-09T22:09:06Z
Mon 9 Nov 17:19  read       64.2  (measured Mon 9 Nov 17:09)
cc6336e8  Mon 9 Nov 17:19  learned    64.2
$ prahari indriya push guestroom-temp 55 --at 2026-11-09T21:39:06Z
Mon 9 Nov 17:19  late       55  (measured Mon 9 Nov 16:39)
    why: Pushed in: 55, measured 2026-11-09T21:39:06+00:00, before the value already kept
    (measured 2026-11-09T22:09:06+00:00): kept in the history only, and not handed to
    the watches
```

55 °F would have fired *Guestroom too cold*. It was forty minutes old
when it arrived, and the room had already warmed up past it.

**A TIME IT CAN'T BELIEVE COUNTS AS ARRIVAL.** A time more than five
minutes ahead of this computer's clock, a time with no zone, and words
that aren't a time are each set aside, and the value counts as measured
when it arrived. The reading's why says which of the three it was. The
value itself isn't thrown away for a bad date.

Home Assistant can send `"at": "{{ states.sensor.guestroom_temperature.last_updated.isoformat() }}"`
beside the value. It doesn't have to.

## Readings from before looks said which

Before [09](09-what-happened-to-a-reading.md), a look didn't record which
reading it judged, so those readings showed no watches. **THE READING
JUST BEFORE A LOOK IS THE ONE IT JUDGED.** A reading's looks start once
its call is done, and one indriya never reads twice at once. So a look
marked as made on an indriya, with no reading named, belongs to the
reading just before it (no more than fifteen minutes back). The history
shows it as matched, never as recorded:

```
Mon 9 Nov 10:37  read 59.1  (on its clock)
    → Guestroom heat when below 60°F: quiet
    → Guestroom cool when above 70°F: quiet
Mon 9 Nov 09:37  read 55  (on its clock)
    → Guestroom heat when below 60°F: quiet (matched by time)
    → Guestroom cool when above 70°F: quiet (matched by time)
```

That's from a copy of the house's own store. Its first two readings came
before looks named theirs. **NOTHING IS WRITTEN.** The match is made each
time the history is read, so a guess never turns into a record. Prahari's
page, Yantra's Watches panel, and `/indriyas N` in a chat each say
*matched by time*.

## Live receipt

All of the above ran with the real `prahari` on a scratch state folder:
the open-meteo address as the call, three watches, a floor set and
removed, a watch removed, a watch moved back off the reading, and a
pushed indriya sent two values with their own times. Above, the outputs
are copied as they came back. The history matched by time was read from
a backup copy of the house's store. The house's own file wasn't opened
for writing.

The first try found two things. *Back to the 5 minutes floor* read
wrong, and now says *back to the floor every call has*. And `prahari
indriya get` on any pushed indriya crashed on its missing call (an older
bug, from [08](08-a-value-sent-in.md)). It now says *check: none, its
value is sent in*. The house's store also showed a read through Dvara
taking a minute before its looks started, so the matching window is
fifteen minutes, not the two first written.

## Tests

`tests/test_paces.py` (31): a watch keeps its wish; removing, ending, or
moving the fastest off slows the reading to the owner's pace or the next
wish, and a paused one still counts; the owner's `--every` lowers faster
wishes; a reading with no known pace isn't slowed, and its first speed-up
remembers one; the agent hears the slow-down; a site is a host
(subdomains covered) or a tool; a new watch or reading under the floor is
refused, setting one slows the rest, a speed-up stops at it and says so,
a fresh read waits for it, and `prahari floor` at the terminal and
`/api/floors` from a page; moving
back keeps memory and the wished pace, never takes someone else's or a
pushed reading's call, and goes alone; a measured time is the age (ISO
or seconds), late values are history and fire nothing, unbelievable
times count as arrival, `push --at`; older looks matched by time, not
past the window, and recorded ones never said as matched; a pushed
indriya shown in full.

Continues [07](07-one-call-by-itself.md) (one call, by itself),
[08](08-a-value-sent-in.md) (a value sent in) and
[09](09-what-happened-to-a-reading.md) (what happened to a reading).
