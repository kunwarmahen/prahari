# 10 — Then, a routine

A watch that fires either tells the person what it saw, or asks the
agent to do something (`then`), a turn with nobody watching. Some things
to do are more than a sentence: *when the porch gets cold, read the
forecast, and if tonight goes below freezing ask me before telling the
house to bring the plants in.* Written as a `then`, that's a prompt the
model is trusted to carry out the same way every time, with a yes/no in
the middle it can't really stop for.

[Vidhi](https://github.com/kunwarmahen/vidhi) keeps exactly that: steps
a person drew once, which can fetch, ask the model, ask the person and
wait for the answer, and tell them. So a watch can start one.

Continues [08](08-a-value-sent-in.md) and [09](09-what-happened-to-a-reading.md).

## `routine`

```bash
prahari add "Porch is cold" --sense porch-temp --when 'below 60' --routine coat-check
#   then: starts the routine coat-check (Vidhi)
```

`--routine` on `add` and `edit`, and `routine` on `create_watch` and
`update_watch`.

**STARTING IS ALL PRAHARI DOES.** When the watch fires, `vidhi start
coat-check --as <the watch's person> --by prahari:<its id>` adds a run
to Vidhi's state folder, and Vidhi's server runs it. The look's `turn`
is `routine`, and its reply which run it started.

**WHAT IT SAW GOES IN AS `found`.** `--found` carries the value itself
(`58`, not *the porch temperature is now 58*), or, for a watch on `new`,
each new item. A routine that has an input called `found` gets it as
`{{inputs.found}}`; one that hasn't simply runs with its own inputs.

**THE ROUTINE TELLS THE PERSON; THE WATCH DOESN'T.** A watch that started
its routine sends nothing itself, or the person would hear twice. One
whose routine didn't start (paused, removed, too many runs open) sends
its usual line and *(The routine coat-check didn't start: …)*, and the
look is `failed` with the reason.

**THEN OR A ROUTINE, NEVER BOTH.** A fire that did two different things
would leave the person unable to say which one did what. Giving a `then`
to a watch with a routine takes the routine away.

## Live receipt

A scratch Prahari and a scratch Vidhi (`vidhi serve` running), a pushed
reading, and a routine with a `found` input:

```
$ prahari indriya add porch-temp --pushed --thing "the porch temperature in °F" --every 1h
$ prahari add "Porch is cold" --sense porch-temp --when 'below 60' --routine coat-check
$ prahari indriya push porch-temp 64
6e04d8ad  Mon 9 Nov 11:39  learned    64
$ prahari indriya push porch-temp 58
6e04d8ad  Mon 9 Nov 11:39  fired      58  then: routine
              why: The porch temperature in °F is 58, so it is below 60, and it did not last time

$ vidhi runs --limit 1
5ca4159f  coat-check  done  2/5 steps  by prahari:6e04d8ad
inputs: {'found': '58', 'line': 60}
```

The first run passed *"the porch temperature in °F is now 58"* as
`found`, the line the watch would have sent. A routine wants the number;
it's the value now.

## Not here

* **Inputs from the watch beyond `found`.** One value goes in; a routine
  that wants more reads it itself (a `read` step on the same indriya).
