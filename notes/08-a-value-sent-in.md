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

The address and key come from `prahari inlet` (or, for someone else in
the house, `prahari inlet --for NAME`; their agent's `create_indriya`
answer has them too). In Home Assistant's `configuration.yaml`:

```yaml
rest_command:
  prahari_guestroom:
    url: "http://linux-al-ml-beast.singhs:8782/inlet/indriya/guestroom-temp?key=YOUR_INLET_KEY"
    method: POST
    content_type: "application/json"
    payload: '{"value": "{{ states(''sensor.guestroom_temperature'') }}"}'

automation:
  - alias: "Guestroom temperature to Prahari"
    triggers:
      - trigger: state
        entity_id: sensor.guestroom_temperature
      - trigger: time_pattern
        minutes: "/20"          # also every 20 minutes, so a steady room isn't "silent"
    actions:
      - action: rest_command.prahari_guestroom
```

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

Not run for real: a real Home Assistant. curl stands in for its
`rest_command`, sending the same body to the same address.

## Not here

* **A value with its own time.** A sender that queued values while the
  network was down gets each one stamped with when it *arrived*, not
  when it was measured.
* **Several values in one push.** One indriya, one value. A sensor
  with temperature and humidity is two indriyas, or one with a pick
  that a sensing watch picks from (the humidity watch's trick in
  [06](06-one-reading-many-watches.md)).
