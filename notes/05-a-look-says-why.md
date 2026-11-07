# 05 — A look says why

A watch that never tells you looks exactly like a watch that has nothing
to tell. The guestroom watch — *set the thermostat to heat when it goes
below 60 °F outside* — said `quiet` six times in a row while the
temperature went 63, 62.2, 59.4, 59.3, 57.3, 56.2. Nothing on the page
said why, so from the outside it was a watch that had decided 56.2 was
not below 60.

Continues [04 — a watch has its days](04-a-watch-has-its-days.md) and the
safeguards of [01 — a watch with no model](01-a-watch-with-no-model.md).

## What was wrong

The watch's test was `ask` — a yes/no for a model, asked only about a
value that changed. Every look asked; no answer ever came:

```
asked, no answer: error: --async, --repeat, --all-runs, --case, --failed,
--no-mcp, --kept, --judge-model, --report and --against belong to --eval
```

The question went to Yantra with `--no-mcp`, which is a flag of Yantra's
acceptance suites (`--eval`), not of a session. Yantra turned every
question away before a model saw it. The tests didn't catch it: they ran
a stand-in Yantra that took any flag. So no `ask` watch had ever been
answered. The question now goes with session flags only (`--no-setu
--no-samay --no-sparsh --no-prahari`); it runs in the watch's own empty
folder, where no server is remembered, with every tool off.

The second fault was worse than the first: **NO ANSWER IS NOT A NO.**
A look whose question went unanswered was written down as `quiet`, the
same word as a look that was answered "no", and that hid the first
fault for hours. Now it is `failed`, like a check that failed. Three in a
row pause the watch and tell you, as any broken look does. What it saw is
not kept as seen, so the next look asks about the same value again,
instead of finding it "the same as last time" and never asking.

## Why, on every look

**EVERY LOOK SAYS WHY.** Whatever it ended as, a look keeps one sentence
saying why, in the watch's own words for the thing:

| ended | why |
|---|---|
| learned | *The first look: the temperature is 62.5, which is not what it waits for (is below 60)* |
| fired | *The temperature is 56.2, so it is below 60, and it did not last time* |
| quiet | *The temperature is 55: it still is below 60, as it did last time. It told you when that became true, and tells again only after it has stopped being true in between* |
| quiet | *The outside temperature is 62.2, the same as last time, so the model was not asked* |
| quiet | *… was 63, now 62.2; the model was asked 'has it crossed a line?' about it and said NO* |
| quiet | *3 item(s), none new: each was seen on an earlier look* |
| failed | *… the model was asked … but gave no answer, so nothing was decided. The next look asks again* |
| broken | *The check answered, but the pick found nothing in its answer …* |

It also keeps the start of **what the check answered** (4,000
characters), the raw text the pick read. Most watches that go wrong go
wrong between that text and the pick: a site that moved its price, an
API that renamed a field. Seeing the text is the whole diagnosis.

Where you see it:

* **Prahari's page.** Every look in **Looks** opens on a click: why,
  what went wrong (if anything), how it came (its clock, Look now, a
  knock), when and how long it took, the check it looked with, the pick
  and what it picked out, the test, what happened then (the agent's
  turn, whether a message was sent), the cost and the Dvara run, and
  folded under them, what the check answered and what the agent said.
  Clicking a watch's **last:** line opens its newest look.
* **Yantra's Watches panel.** Each look in a watch's **looks** shows its
  why, and opens to the same details.
* **The terminal.** `prahari looks ID` prints `why:` under every look;
  `--full` adds how it came, the Dvara run, what the check answered and
  what the agent said.
* **Your agent.** `watch_looks` gives it the why, so "why didn't my
  guestroom watch fire?" can be answered in the chat.

Looks made before this have no why. The page says so, and still shows
what they kept, which for the guestroom watch's hidden looks was the
error above.

## Live receipt

The question as the watch now sends it, to the Yantra in the house's
Prahari container, on the value its last look saw:

```
$ yantra --cwd /tmp/asktest --json --unattended --no-skills --no-setu \
    --no-samay --no-sparsh --no-prahari --memory off --learn off \
    --reflect off --prompt "Answer with one word, YES or NO, … Question:
    has the outside temperature crossed a line: below 60°F … <<< 56.2 >>>"
YES
{"format": "yantra.run.v1", "ok": true, "text": "YES", "stop_reason": "end_turn", …}
```

The same question with `--no-mcp`, as it went before, never reached a
model.

## A band is two watches

Fixed, the guestroom watch would still have been the wrong shape. An
`ask` is asked about every change, and on an hourly temperature every
look is a change: below 60 all night, the model says YES each hour and
the thermostat is set to heat each hour, up to the ten a day the limit
allows. A line needs no model, and fires once as it is crossed.

So **A BAND IS TWO WATCHES**: below 60 → heat, above 70 → cool, the same
check, one line each, each with a `then` of its own. "One thing, one
watch" (notes/03) still refuses a second line the *same* way on one
number, which would be the two-flights-watches muddle again, but a line
on the other side is a different thing to do, and is allowed. The agent
is told so in `create_watch`'s description: a number against a line is
never an `ask`.

## What was deliberately not built

* **Keeping the whole answer.** 4,000 characters is enough to see why a
  pick found nothing; a page's full text on every hourly look would
  grow the file for no one.
* **Why on renewals and inlet knocks beyond what they say.** A renewal
  keeps what Gmail answered, as before; a knock's why is the test's,
  like any look.
