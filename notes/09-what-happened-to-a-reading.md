# 09 — What happened to a reading

A watch has its looks: each one says why it was quiet, told you or
failed, and opens on what the check answered
([05](05-a-look-says-why.md)). An indriya had a list of values and
nothing else. *"Why didn't my guestroom watch fire last night?"* meant
reading two histories side by side, the indriya's values and the watch's
looks, and matching them up by time. The pages didn't show the
indriya's history at all, only its latest value and its last failure.

## Each reading says what came of it

Every reading now records **how it came**, and every look a watch makes
on a reading records **which reading** it was. So a reading answers on
its own:

```
$ prahari indriya readings guestroom-temp
Mon 9 Nov 09:13  broken  (sent in)
    why: The sender said it has no value ('unavailable'): the sensor behind it may be off or out of reach
    sent 'unavailable'
    → Guestroom too cold: failed
Mon 9 Nov 09:13  read 61.5  (sent in)
    → Guestroom too cold: fired
Mon 9 Nov 09:13  read 64.2  (sent in)
    → Guestroom too cold: learned
```

How a reading came is one of five:

* *on its clock*: its `every` came round.
* *read now, by hand*: `prahari indriya look`, or **Read now** on a page.
* *asked for fresh by a reader*: `max_age`, [07](07-one-call-by-itself.md#fresh-on-asking).
  No watch decides on these, and the history says so.
* *sent in*: a pushed value, [08](08-a-value-sent-in.md).
* *nothing came in time*: a pushed indriya's deadline passed.

`--full` adds each reading's why, what came in, and each watch's own
why.

**ONE ANSWER, EVERY DOOR.** The same history, built by one function
(`indriyas.history`), is:

| Where | How |
|---|---|
| Prahari's page | **Readings** under each indriya; each reading opens on how it came, why, what was kept, what each watch decided (and why), and what came in |
| Yantra's Watches panel | **readings** under each reading, the same fold |
| a chat through Dvara | `/indriyas 2`: the second reading's last five, with your watches' decisions |
| the agent | `read_indriya` lists them, so *"why didn't it fire?"* is answered from the record |
| a terminal or a script | `prahari indriya readings NAME [--full] [--json]`, and `GET /api/indriyas/NAME/readings` |

**ANOTHER PERSON'S WATCHES ARE COUNTED, NOT NAMED.** A house reading is
sensed by other people's watches too. Asked as a person (Yantra's panel
for someone on Dvara, `/indriyas`, the agent), the history shows that
person's own watches by name and the rest as *"and 2 of other people's
watches"*. What someone else watches for is theirs. Prahari's own page,
at the computer, shows them all, as it shows every watch.

**AN OPENED READING STAYS OPEN.** The page redraws itself every 15
seconds. A reading opened to read stays open across that, instead of
snapping shut halfway through its why.

## Live receipt

A scratch state: `outside-temp` read once by hand with the real weather
call (53 °F: heat fired, cool learned), and `guestroom-temp` sent 64.2,
61.5 and `unavailable` (above). The page, with **Readings** open on
`guestroom-temp` and the 61.5 reading opened, still showed it open after
one of its own refreshes:

```
▸ Mon, Nov 9, 09:13 AM  broken · sent in · Guestroom too cold: failed
▾ Mon, Nov 9, 09:13 AM  read 61.5 · sent in · Guestroom too cold: fired
    Came     sent in
    Why      Pushed in: 61.5
    Kept     61.5
    Watches  Guestroom too cold  fired
               The guestroom temperature in °F is 61.5, so it is below 62, and it did not last time
    ▸ What came in
▸ Mon, Nov 9, 09:13 AM  read 64.2 · sent in · Guestroom too cold: learned
```

And Dvara's `/indriyas 2` on the same store gave the history above, in a
chat's words.

## Not here

* ~~**Readings made before this.**~~ Their looks are matched to the
  reading just before them, and shown as *matched by time*
  ([12](12-a-pace-given-back.md#readings-from-before-looks-said-which)).
* **A reading's watches for a fresh read.** A fresh read is handed to
  no watch ([07](07-one-call-by-itself.md#fresh-on-asking)), so it has
  none to show.
