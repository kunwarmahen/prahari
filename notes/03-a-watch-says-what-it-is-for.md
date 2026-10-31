# 03 — A watch says what it is for

A watch is written by an agent, in a conversation, often by voice, and
then it is quiet for days. When it speaks again, the person has only
what it says to go by. So what it says has to carry what it is for.

Continues [01 — a watch with no model](01-a-watch-with-no-model.md).

## How a person loses track

A person asked a kitchen speaker for a flight to Phoenix, heard the
fares, and said yes to "want me to keep an eye on the price?" — and
then "yes, yes, yes" to whatever came next. Two watches were made, on
the same Google Flights page, with the same pick. Neither had a name, so
both were called after the tool they looked with. A day later the list
said:

```
browser_open watch (id 9b904bc4)
every 6 hours, looks with browser_open; tells you when the number is below 571 …
browser_open watch (id 3ed2b4d6)
every 6 hours, looks with browser_open; tells you when the number changes.
```

and a message came:

```
browser_open watch:
• the number is now 58
```

The person read 58 as the temperature outside. Everything the watch
said was true, and none of it said what the watch was for: not the
page, not what the number was, not what they had asked.

## What a watch carries now

**ASKED IS THE PERSON'S OWN WORDS.** A watch keeps what was asked for,
as it was said — "keep an eye on the nonstop to Phoenix and tell me if
it gets cheaper" — and says it first wherever it is shown: the list,
the page, and every message it sends. It is the one line the person
recognises without having to decode a recipe, because they said it.

**THE THING IS NAMED.** A pick takes "the number"; the watch can say
what that number is — "the fare", "the temperature", "BTC's price" —
and its messages say *the fare is now 58*.

**WHERE, NOT WITH WHAT.** The sentence says the page it looks at
(`looks at google.com/travel/flights (with browser_open)`), or the
search it makes (`looks with mcp__gmail__search_threads for
'from:bank'`). The tool comes after, for whoever mends it.

**EVERY MESSAGE SAYS WHY IT CAME.** Its last lines are the person's
words and the watch in one line, with its id to mend it by:

```
You asked: "keep an eye on the nonstop to Phoenix"
(tells you when the fare is below 571; looks at google.com/travel/flights every 6 hours · watch 9b904bc4)
```

**AN AGENT MUST SAY WHAT IT IS MAKING.** `create_watch` refuses a call
with no `name` or no `asked`, and says what to give. By hand, on the
command line or the page, both stay optional: the person writing it is
the one who will read it. A watch with no name is named by its page and
its line — `google.com/travel/flights: the number is below 571` — never
by its tool.

**ONE THING, ONE WATCH.** A second watch on the same call and the same
pick, for the same person, is refused, naming the one there is; the
preview says so before anything is looked at, so the agent offers to
mend that one instead. Another test on the same number is a change to
the watch, not a second watch: two watches on one fare, under names
nobody chose, is exactly how the person above stopped knowing which was
which. A different number on the same page (the bid, not the last
price) is a different pick, and allowed.

## Live receipt

The real `prahari`, a scratch state, Coinbase's public price through
Yantra's `web_fetch`:

```
$ prahari add "BTC under 200k" --check web_fetch \
    --args '{"url": "https://api.coinbase.com/v2/prices/BTC-USD/spot"}' \
    --pick json:data.amount --when 'below 200000' --every 1h \
    --thing "BTC's price" --asked "tell me if bitcoin is under 200 thousand dollars"
added d14a1709: BTC under 200k -- every hour, looks at api.coinbase.com/v2/prices (with web_fetch); tells you when BTC's price is below 200,000 (once each time it becomes true)
$ prahari add "BTC moves" --check web_fetch \
    --args '{"url": "https://api.coinbase.com/v2/prices/BTC-USD/spot"}' \
    --pick json:data.amount --when changed --every 1h
error: local already has a watch on exactly this: d14a1709 (BTC under 200k) -- every hour, looks at api.coinbase.com/v2/prices (with web_fetch); tells you when BTC's price is below 200,000 (once each time it becomes true). Mend that one (its test, how often) instead of making a second; ask the person first
$ prahari look d14a1709
Fri 30 Oct 10:37  fired      76,491.46  then: told
    • BTC's price is now 76,491.46
```

and what it sent:

```
BTC under 200k:
• BTC's price is now 76,491.46
You asked: "tell me if bitcoin is under 200 thousand dollars"
(tells you when BTC's price is below 200,000; looks at api.coinbase.com/v2/prices every hour · watch d14a1709)
```

## Their words, not the model's

Made through an agent on `qwen3.8`, the same watch's `asked` came back
as *"notify me when Bitcoin falls below $200,000"* for *"tell me if it
goes under 200 thousand dollars"*. The sense was right and the words
were not theirs, and every message prints them after *You asked:*. Two
changes. `asked` now tells the model to copy the message word for word,
the one where they asked rather than their yes, with that very
rewording as the example of what not to write. And `preview_watch`
takes `asked` and reads it back as the messages will begin, so the
person hears their own words, or someone else's, before they agree.

The same request again on `qwen3.8-64k:latest`, through Yantra with a
scratch Prahari, after the change:

```
→ mcp__prahari__preview_watch()
The trial look works. Here's the watch, in words:

> **Every 30 minutes, it opens Bitcoin's price page (TradingView) and tells
> you when the spot price falls below $70,000** — once each time it drops
> under the line.

It sees **$77,424** right now, so no match yet. Its messages will begin:
*"You asked: 'tell me if bitcoin goes under 70 thousand dollars'"*
```

Word for word, and said to the person before the yes.

Prahari can't check the words itself: the conversation never reaches
it, and the message that asked is not the last one (the last is the
yes). Having Yantra fill `asked` from the conversation would have to
guess which message that was, which is the model's job done worse.

When a watch begins and when it is over — a fare after Saturday, a
flight once it lands — is [note 04](04-a-watch-has-its-days.md).

## What was deliberately not built

* **Renaming old watches.** A watch made before keeps its name and has
  no `asked`; inventing words the person never said would be worse than
  none. Its messages still say where it looks and when it tells.
* **Refusing a watch on the same page with another pick.** The bid and
  the last price are two things; only the same call and the same pick
  is one.
* **The spoken yes.** At a speaker the person cannot see the card, and
  several yeses in a row can each approve something. That belongs to the
  speaker's side, which should read the watch aloud before the yes.
