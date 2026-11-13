# 14 — A picture, seen

Every pick so far is a pattern run on text: a number, a piece of text, a
value from JSON, a list of items. A camera answers with a picture, and a
picture has no text to run a pattern on. "Tell me when a package is at
the door" was a watch nobody could write.

Continues [06 — one reading, many watches](06-one-reading-many-watches.md)
and [01 — a watch with no model](01-a-watch-with-no-model.md).

## The one pick a model makes

```
prahari indriya add porch-package \
  --check mcp__homeassistant-home__camera_snapshot --args '{"entity_id": "camera.porch"}' \
  --pick '{"see": "Is there a package or a box by the door? Answer yes or no."}' \
  --every 15m
prahari add "Package at the door" --sense porch-package --when '{"contains": "yes"}'
```

`{"see": QUESTION}` takes the picture the check answered with and puts it
to a model that can see, with the question. The model's one-line answer
becomes the value, and from there it's an ordinary reading. A test on it
(`contains yes`) fires on its edge, once each time it becomes true, so a
parcel sitting on the step all afternoon is news once.

**A PICTURE IS THE ONE PICK A MODEL MAKES, AND IT SAYS SO.** Prahari's
first promise was a look with no model (note 01). A camera can't keep that
promise, so `see` breaks it in the open. The card reads *what a model
sees, asked: Is there a package by the door?*, and a person accepting the
watch knows a model looks every fifteen minutes. On this house that model
is a local one, so nothing leaves the computer.

**THE QUESTION IS ASKED BY THE LOOK, NEVER BY THE RECIPE.** `recipe.py`
still runs no model. `looking.Roads` does it: when a watch or a reading
has a `see` pick, the look asks Yantra for its picture back
(`--call-pictures`, or `pictures: true` through Dvara's `/call`). It saves
the picture in the watch's own folder (`seen.jpg`) and asks
`yantra --image seen.jpg` the question, with every tool off and nothing
remembered (the same guards as an `ask` test). The answer then goes on
as what the tool said. Picking, testing and history are all unchanged.

**WHAT'S WRITTEN IN A PICTURE IS NOT AN ORDER.** The prompt says so. A
note taped to the door is part of the picture.

**A LOOK WITH NO PICTURE FAILS IN WORDS.** If the check answered with no
picture (a `get_state` instead of `camera_snapshot`), or the model said
nothing, the look fails with the reason. It's never read as "nothing
there".

`PRAHARI_SEE_MODEL` names the model (`gemma4:12b`). Without it, Yantra's
own model is used, and the house's `qwen3.8-64k` is one Ollama marks
*vision*.

## Where the picture comes from

Setu's Home Assistant connector has a new read tool, `camera_snapshot`
(Setu's own notes). It fetches Home Assistant's camera proxy at 1280 wide,
and Home Assistant scales the frame down itself. It takes `camera.*`
entities only, and checks that the answer really is a picture. Yantra's
`--call` keeps the picture and hands it back inline, as base64 in
`yantra.call.v1`'s `pictures`, but only when asked. A pipe and Dvara's
door carry it the same way, with no shared folder.

## Live receipt

The house's real cameras, through Setu, from a scratch Prahari (its own
state folder, never the house's), `preview` (one look, nothing kept):

```
camera.porch, qwen3.8:latest, "Is there a package or a box on the porch?"
  It sees No, I see a covered table, chairs, and a trash can on the brick patio.

camera.front_yard, qwen3.8:latest, same question
  It sees No, I see only evergreen shrubs, a small tree, grass, and a black fence.
```

Both are right about what's there. Then came a harder question, about the
front yard, where a dog stands by the tree:

```
"Is there an animal in the yard?"
  qwen3.8:latest   No, just trees, shrubs, a grassy lawn, and a black fence.
  gemma4:12b       Yes, a small dog.
  gemma4:26b       Yes, a bird
```

The frame is 640 wide (the camera sends no more), and the dog is small in
it. **The model matters.** `gemma4:12b` got it right, so it's the one to
name in `PRAHARI_SEE_MODEL` for a camera watch. Try a question on
`preview` before trusting it.

**Two things the run found.**

* **Some cameras send their last saved frame, not a new one.** The front
  yard's picture carried the camera's own stamp, *Nov 07 2026 04:43 PM*,
  five days before the run. Home Assistant answers the camera proxy with
  whatever the integration last stored. A reading of a camera that only
  saves a frame on motion says what the last motion looked like.
* **No date is asked of the model.** We tried asking it to read the
  camera's stamp. All three models made one up (*Nov 05 2024*,
  *09/01/2012*, *07-07-2026*). A wrong time on a reading is worse than
  none, so the question is the person's alone.

Setu's connector was also found to show a camera's `access_token` (a live
key to its picture) in `get_state`. It's hidden now.

## What is deliberately not here

* **No fresh frame is forced.** Home Assistant's `camera.snapshot` service
  writes a new picture to a file, but it's a write and needs the control
  level. A reading is a read.
* **No picture is kept with a reading.** Only the answer is kept. The last
  picture stays in the watch's folder (`seen.jpg`) until the next look.
  A history of pictures of your porch is a choice somebody should make on
  purpose.
* **No `see` on a test.** `ask` is a yes/no about text. `see` is the pick
  instead, so a camera's answer can be tested like any other value.

## Tests

`tests/test_seeing.py`: a `see` pick takes a question. Its value is the
model's first line, and a test runs on it. The card says a model looks.
Only a `see` pick asks for a picture, on the direct road
(`--call-pictures`) and the Dvara road (`pictures: true`). The model's
answer becomes what the look said. No picture, or no answer, is a failed
look that says why. A failed look isn't put to a model. The picture goes
with `--image`, the model as named, every tool off, and the picture's own
words are not orders.
