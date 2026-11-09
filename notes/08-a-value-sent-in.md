# 08 — A value sent in

An indriya so far *read* something: a weather address, a page, a mail
search. But the guestroom has a thermometer of its own, in Home
Assistant, and it knows the room's temperature better than any page
Prahari could fetch. Reading Home Assistant on a timer would mean
Prahari asking every few minutes about a number that changes a few
times an hour. Home Assistant can say it itself, the moment it changes.

Continues [07 — one call, by itself](07-one-call-by-itself.md) and the
inlet's rules from [02](02-a-watch-for-everyone.md).

## A pushed indriya

```bash
prahari indriya add guestroom-temp --pushed --thing "the guestroom temperature in °F" --every 30m
#   added indriya guestroom-temp: keeps the guestroom temperature in °F, pushed in to the
#   inlet as guestroom-temp (a value expected at least every 30 minutes)
#   send it values: POST http://…:8782/inlet/indriya/guestroom-temp   with {"value": 68.2}
prahari add "Guestroom too cold" --sense guestroom-temp --when 'below 62'
```

It makes no call. A value sent to `POST /inlet/indriya/guestroom-temp`
is picked (`{"value": …}` by default; a bare number is taken as the
value), kept, and handed to every watch that senses it. Each watch
judges it exactly as it would a reading the clock took: the first one
learns, a line fires on its edge, `ask` asks. `prahari indriya push
guestroom-temp 61.5` does the same from the terminal, so you can try it
before Home Assistant is set up.

**A KNOCK REACHES ONLY ITS OWN.** The value comes with an inlet key, and
the name is looked for only among the indriyas of that key's person, as
a knock on `/inlet/whatsapp` is heard only by their watches. Another
person's `pool-temp` answers *"no indriya pool-temp to push to, for this
key"*, the same as a name that doesn't exist: a leaked key can't learn
what other people keep, and can't feed their watches a number. A
pushed indriya can't be read on asking (`read now`, `max_age`): its
value is the last one that came. An indriya that reads takes no pushes.

## Silence is said

A thermometer that stops sending looks, to the watch, exactly like a
room that never got cold. That's the failure this note is built
against.

**ITS EVERY IS A DEADLINE.** For a pushed indriya, `every` is how often a
value is *expected* at least. Each value moves the deadline on. When the
deadline passes with nothing sent, the clock records a failed reading,
*nothing pushed in for an hour*. Each watch shows it on its own looks
(*"Its indriya guestroom-temp got no value from its sender…"*), counted
once against the indriya. Three in a row pause it, and the owner is told
which watches went quiet, as with any indriya that keeps failing.

**"UNAVAILABLE" IS NOT A TEMPERATURE.** When a sensor drops off the
network, Home Assistant sends the word `unavailable` (or `unknown`)
where the number was. Kept as the value, a watch on *below 62* would
read it as "not below 62" and stay quiet for ever. So those words, and
an empty value, are a broken reading, counted the same way.

**THE SENDER COMING BACK STARTS IT AGAIN.** An indriya paused because
nothing came, or nothing usable came, resumes on the next value that
arrives. One paused by hand, or for being unused, stays paused and
says so (409), because that pause was someone's choice.

## From Home Assistant

Sarathi's tutorial (Step 8, *A number Home Assistant already knows*)
walks through this a step at a time, with what to do when it doesn't
arrive. In short:

1. Make the reading: `prahari indriya add guestroom-temp --pushed
   --thing "the guestroom temperature in °F" --every 30m`.
2. Get the address and key: `prahari inlet` (for someone else in the
   house, `prahari inlet --for NAME`; their agent's `create_indriya`
   answer has them too). The reading's address is the inlet's with
   `indriya/guestroom-temp` for `WORD`, and `?key=…` on the end.
3. In Home Assistant, keep that address in `secrets.yaml`, since it
   holds the key:

```yaml
# secrets.yaml
prahari_guestroom_url: "http://linux-al-ml-beast.singhs:8782/inlet/indriya/guestroom-temp?key=YOUR_INLET_KEY"
```

```yaml
# configuration.yaml (then check the configuration, and restart)
rest_command:
  prahari_guestroom:
    url: !secret prahari_guestroom_url
    method: POST
    content_type: "application/json"
    payload: '{"value": "{{ states(''sensor.guestroom_temperature'') }}"}'
```

4. Try it once: **Developer tools → Actions → RESTful Command:
   prahari_guestroom → Perform action**, then `prahari indriya readings
   guestroom-temp` shows it arrived.
5. The automation (**Settings → Automations & scenes → Create → Edit in
   YAML**):

```yaml
alias: Guestroom temperature to Prahari
triggers:
  - trigger: state
    entity_id: sensor.guestroom_temperature
  - trigger: time_pattern
    minutes: "/20"          # also every 20 minutes, so a steady room isn't "silent"
actions:
  - action: rest_command.prahari_guestroom
mode: queued
```

What Home Assistant's log says back: `401` is a wrong key, `404` a name
that isn't this key's person's, `409` a reading paused by hand.

The second trigger matters. A room that holds at 66 °F for two hours
sends nothing on *state change*, and that would look like silence. So
send on a timer as well, more often than the indriya's `every`.

## Live receipt

A scratch state, a real `prahari serve` (on a spare port), and curl
sending exactly what the `rest_command` above sends:

```
$ prahari indriya add guestroom-temp --pushed --thing "the guestroom temperature in °F" --every 30m
$ prahari add "Guestroom too cold" --sense guestroom-temp --when 'below 62'
$ curl -X POST "$INLET/indriya/guestroom-temp?key=$KEY" -H 'Content-Type: application/json' \
    -d '{"value": "64.2"}'
{"pushed": "guestroom-temp"}
… the same with "61.5", then "unavailable"
$ curl -X POST "$INLET/indriya/guestroom-temp?key=wrong" -d '1'
{"detail": "missing or wrong inlet key"}
$ curl -X POST "$INLET/indriya/pool-temp?key=$KEY" -d '1'
{"detail": "no indriya pool-temp to push to, for this key"}

$ prahari looks 89508dd8
Mon 9 Nov 08:43  failed     why: Its indriya guestroom-temp could not read (broken) …
Mon 9 Nov 08:43  fired      61.5  then: told
    • the guestroom temperature in °F is now 61.5
Mon 9 Nov 08:43  learned    64.2
```

64.2 taught the watch, 61.5 fired it, and `unavailable` was a miss, said
on the watch and not kept as the temperature. That run's wording for a
pushed miss (*"could not read"*) was wrong for something that is sent
rather than read. It now says *"got no value from its sender (The
sender said it has no value ('unavailable') …)"*. Silence past the
deadline was tested on a clock moved by hand (`tests/test_pushed.py`);
nobody waited an hour.

Then for real: the house's Home Assistant, set up by Sarathi's tutorial
Step 8, sends `guestroom-temp` from its own `rest_command`, and the
guestroom watches sense it.

## Not here

* **A value with its own time.** A sender that queued values while the
  network was down gets each one stamped with when it *arrived*, not
  when it was measured.
* **Several values in one push.** One indriya, one value. A sensor
  with temperature and humidity is two indriyas, or one with a pick
  that a sensing watch picks from (the humidity watch's trick in
  [06](06-one-reading-many-watches.md)).
