# 02 — A watch for everyone, mail that knocks, and a door to the street

[Note 01](01-a-watch-with-no-model.md) ended with three things left out:
watches for the other people in the house, mail pushed instead of
polled, and an inlet reachable from outside. They turn out to be one
idea seen three times. **A knock, and a look, belong to a person.** Once
that holds all the way down, each of the three is small.

## A look as its person

A look on the direct road is `yantra --call` on this computer, with this
computer's accounts. Those are the owner's. That's why Dvara offered
watches to one person, named: a guest's watch for "new mail from the
bank" would have searched the owner's inbox and told the guest.

So a watch on the Dvara road no longer looks here. Its look goes to
Dvara as its person, `POST /call`, and Dvara builds their agent with
their own Setu folder and runs the one tool with no model
([Dvara's note 56](https://github.com/kunwarmahen/dvara/blob/main/notes/56-a-look-as-them.md)).
The rule for what may run is the same function at both doors, Yantra's
`calling.py`: a tool that reads, or the one call granted word for word.
`Roads` in looking.py picks the door by the watch's road. A Dvara-road
watch on a Prahari with no Dvara is a failed look that says so, never a
look made quietly with the owner's accounts instead.

Two things follow. Dvara now gives the tools to everyone, and its
`--prahari-for` becomes a way to narrow that. And the look is made with
the watch's own agent, not plain Yantra, so a tool only that package
brings is there for its looks too.

## A knock as its person

The inlet had one key. With everyone making watches, that's a leak in
the other direction. Asha's MacroDroid sends "Mum: dinner at 8?", and
the owner's watch for "Mum" fires on it.

**Each person has their own key**, kept in the state file (`inlet_key`),
made the first time it's asked for: `prahari inlet --for asha`, or by
Asha's agent with the new read tool `inlet_address`. A knock is heard
only by the watches of the person whose key it came with. The key kept
in `inlet.token` belongs to this computer's person, who goes by two
names, `local` and Dvara's name for them, so a knock for one is a knock
for both (`Clock.home`). `--new-key` replaces a person's key when a phone
is lost.

## Mail that knocks

A watch on mail looks every 15–30 minutes. A mail server can say "a mail
came" the moment it lands, and Gmail can too. The design question is
what such a knock is *for*. The answer that keeps the recipe generic: a
knock doesn't carry the news, it says **look now**.

**`wake`**. A watch that looks may name a word at the inlet. When that
word knocks (as its person), the watch looks at once with its own check
instead of waiting for its next `every`. The knock's body isn't read.
Whatever sent it can say "something came", but it can't say what, so it
can't put words into the watch or fire it. The `every` stays, as the
look that happens anyway if a push goes missing. A knock while the watch
is looking makes one more look after it, never a pile. Gmail sends
several notifications for one mail.

Two things knock for mail.

**IMAP IDLE (any mail server).** `prahari mailbox add work-mail --server
imap.fastmail.com --user me@…` keeps a folder open while `prahari serve`
runs. IDLE is the IMAP command that lets the server write `* 12 EXISTS`
the moment a mail lands. Python's imaplib has no IDLE before 3.14, so
mailbox.py says it by hand. It waits with `select`, never with a read
that times out, because a socket file whose read timed out can't be
read again. Each new mail is fetched with `BODY.PEEK` for From, To,
Subject, Date and Message-ID only. Nothing of what it says is fetched,
and nothing is marked read. Then it knocks on the mailbox's name, as the
mailbox's person. So a watch can **listen** for it ("tell me when the
bank writes", `--listen work-mail --pick json:from --when 'contains
bank'`), with no tool and no account anywhere but here. Or a watch can
keep its Gmail search and be **woken** by it.

The mailbox's rules are a watch's rules again. The first connection only
learns: it remembers the folder's next UID and knocks for nothing. Mail
that came while the connection was down knocks when it's back, once
each, by UID. A folder whose UIDVALIDITY changed is learned again,
not replayed. The password (an app password, for most services) is kept
in a file of its own, readable by you alone, and never in the SQLite
file. Plain IMAP is refused except to this computer, for a test server.

**Gmail's push.** Gmail's `users.watch` tells a Google Cloud Pub/Sub
topic each time mail arrives. Setu's Gmail connector gained
`watch_mailbox` for it. It's classed as a write, though it changes no
mail, because the topic could be anybody's. The push lasts seven days,
so a watch can carry **`renew`**: the call that keeps the sender
knocking, run when the watch starts and once a day after, on the watch's
own road, granted word for word like its check. A renewal that fails is
`failed`, counted like a broken look, and tried again in an hour,
because a push that stopped is a watch that has quietly gone back to its
six-hourly look. Pub/Sub delivers by pushing to an address, and the
inlet unwraps its envelope: the base64 `data` is the event, and its
`messageId` is the event's id.

That's the one road here that needs a public address. That's the third
thing.

## A door to the street, and only a door

A webhook from a service on the internet (Pub/Sub's push, a tracker,
IFTTT) needs the inlet reachable from outside. Putting `prahari serve`'s
port on the internet would put the page and its API there too, behind
one token.

So **the public road is the inlet alone**. `prahari serve --inlet-port
8783` opens a second listener that answers `POST /inlet/WORD` and
nothing else. The page is a 404, every `/api` path is a 404, whatever
token is offered. It listens on 127.0.0.1, and Tailscale Funnel carries
a public HTTPS name to it, the same road Setu's catalog server uses: no
domain, no open router port, Tailscale holding the certificate.
`deploy/public-inlet-tailscale.sh` does it, on port 8443 so a catalog on
443 keeps its own. The person runs it themselves, since it signs in to
their Tailscale account.

A key that lives in webhook settings on the internet will leak one day,
so the inlet got **a limit on knocks**: sixty a minute per key, then
429. A sender stuck in a loop, or someone who found a key, can't turn
Prahari into a machine that starts a look every second. What a leaked
key can do is what any inlet key can do: knock, and be heard by its own
person's watches. `prahari inlet --for NAME --new-key` replaces it.

## Live receipt

A scratch Dvara on 8798 (two people, `mahen` and `asha`), a scratch
Prahari, page on 8784 and the inlet alone on 8797, and a local IMAP test
server standing in for a mail server. The prices are real, fetched from
Coinbase. No model ran anywhere.

A watch for asha, looked at through Dvara as asha:

```
$ prahari add "BTC under 90k" --check web_fetch --args '{"url": "https://api.coinbase.com/v2/prices/BTC-USD/spot"}' \
      --pick json:data.amount --when 'below 90000' --every 1h --runner dvara --as asha --agent watcher
$ prahari look 9ccf6599
Thu 22 Oct 20:16  fired      81,050.01  then: told
    • the value is now 81,050.01
$ prahari look 9ccf6599
Thu 22 Oct 20:16  quiet      81,050.01
```

(Dvara's log: `POST /call`, `POST /notify`, `POST /call`.)

A mailbox for asha, a watch that listens to it, and a mail landing:

```
$ echo app-password | prahari mailbox add work-mail --server 127.0.0.1 --port 38279 --user asha@example.com --for asha --password-stdin --no-tls
opened INBOX on 127.0.0.1 as asha@example.com; kept as work-mail for asha
$ prahari add "Bank wrote" --listen work-mail --pick json:from --when 'contains bank' --as asha
$ prahari serve --port 8784 --inlet-port 8797 --inlet-public-url https://beast.example.ts.net:8443
inlet alone: https://beast.example.ts.net:8443/inlet/WORD
mailbox work-mail (asha): listening to INBOX since 20:20
fd04124a  Thu 22 Oct 20:20  fired      Bank <alerts@bank.example>  then: told
              • from: Bank <alerts@bank.example> · to: me@example.com · subject: Your statement 2 · …
```

The mail already in the folder was learned and never told. Each mail
that landed after it knocked once, including one that landed while
`serve` was restarting.

Two people, one word, two keys, on the public listener:

```
$ prahari inlet --for asha
for:       asha
send to:   POST http://127.0.0.1:8784/inlet/WORD
   or:     POST https://beast.example.ts.net:8443/inlet/WORD   (from anywhere: the public road)
...
$ curl -X POST "127.0.0.1:8797/inlet/whatsapp?key=$ASHA" -d '{"title":"Mum","text":"Dinner at 8?","id":"n1"}'
{"heard_by": 1}                                   # Mum (asha) fired
$ curl -X POST "127.0.0.1:8797/inlet/whatsapp?key=$MINE" -d '{"title":"Mum","text":"call me","id":"n2"}'
{"heard_by": 1}                                   # Mum (mine) fired
$ curl 127.0.0.1:8797/                            # 404
$ curl 127.0.0.1:8797/api/watches -H "Authorization: Bearer $PAGE_TOKEN"
{"detail": "not found"}
$ (61 knocks in a minute) the 61st: 429
{"detail": "too many knocks: 60 a minute at most"}
```

And Gmail's push, as Pub/Sub delivers it, waking a watch of asha's whose
check is the price:

```
$ curl -X POST "127.0.0.1:8797/inlet/gmail?key=$ASHA" -d '{"message":{"data":"<base64>","messageId":"m-77"},"subscription":"projects/house/subscriptions/prahari"}'
{"heard_by": 1}
$ prahari looks 6c7b5880 --json   →  wake fired 81,137.57 · clock learned 81,112.67
6c7b5880  Thu 22 Oct 20:19  fired      81,137.57  then: told
              • was 81,112.67, now 81,137.57
```

The run found two things, both fixed before this note was written. A
mailbox said it was listening "since 00:17 UTC" on a page that says
every other time in local time. It now says local time. And the page
didn't say whose a watch was, which matters now that the page lists
everybody's. Each watch for someone else now carries a *for asha* tag,
and a woken one carries *woken by: gmail*.

Not run for real yet: Gmail's push against Google (it needs a Pub/Sub
topic in the person's Google Cloud project, and the Funnel name). The
envelope, the wake and the renewal are each tested offline. Also not run
yet: IMAP IDLE against a real mail server, and the Funnel script itself.

## What was deliberately not built

* **Reading the mail in the knock.** A mailbox's knock carries headers,
  enough for "who and about what". The body is the check's job, through
  the person's own accounts, when a watch is woken.
* **A Pub/Sub pull subscription.** Pulling needs a Google credential
  with the Pub/Sub scope, which Setu's Gmail sign-in doesn't ask for, or
  a service account's signed token, which the standard library can't
  sign. A push to the public inlet needs neither.
* **Passwords asked for in the chat.** A mailbox is added at the
  computer (`prahari mailbox add --for NAME`). An agent would carry a
  person's mail password through a model's context and a chat log.
* **The page and API on the public road**, at any token. The page is
  the house's.
