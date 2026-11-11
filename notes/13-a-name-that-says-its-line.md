# 13 — A name that says its line

The guestroom has two watches on one reading: *heat below 60*, *cool
above 70*. Moving the cool one to 80 was always possible: `prahari edit
ID --when 'above 80'`, or Yantra's watches panel. But a watch is known
by its words, not its test. Its name was *Cool the guestroom above 70*,
what you asked was *turn the AC on when the guestroom is above 70*, and
the thing it watched was *guestroom at 70*. After the edit the watch
acted at 80 and said 70 in every list, every chat line that named it,
and every notification it sent.

And Prahari's own page couldn't change a watch at all, except how often
it looked.

## Mend, on Prahari's page

Each watch now has **Mend** beside Looks. It opens the watch's own words
in boxes, in the short forms Prahari reads (`number`, `above 80`, `1h`):
its name, what it's for, the thing it watches, its check and how often
(for a watch that looks itself), its pick and test, its then, and how
many times a day. **Save changes** sends only the boxes that differ, so a
new name keeps what the watch saw, and a new pick or test starts it over.
A watch that listens or senses a reading says so in place of the check:
its call isn't its own to change. The page refreshes every 15 seconds,
and a form being typed in is left alone until it's saved or closed.

## The number goes with the line

**THE TEST CHANGED, THE NAME DID NOT.** Wherever a mend moves the test's
number, its words are checked for the old one:

* **On a page** (Prahari's Mend, Yantra's watches panel), the name,
  what it's for and the thing follow the test box as you type. 70 in
  the test becomes 80, and so does every 70 in those boxes, before
  anything is saved. You see it and can change it back. A box you typed
  in yourself is yours and isn't touched.
* **From the terminal**, `prahari edit` says which words still say the
  old test and what they would say. `--carry-words` changes them in the
  same mend.
* **From a chat**, `update_watch` takes `carry_words: true`, or the new
  words themselves. Yantra's prompt tells the agent to send the words
  with the line in one call. When it doesn't, the answer it gets back
  names the stale words, so it can offer them.
* **From Dvara**, `/watches when 2 above 80` carries the words, since a
  chat command has no boxes to show first.

**OFFERED, OR ASKED FOR, NEVER GUESSED BEHIND YOUR BACK.** A swap is
textual: every standalone 70 becomes 80. *Bedroom 2* with a test of
`above 2` would become *Bedroom 3*. So a plain `prahari edit` only says
what it would change. It changes the words when the mend asks for it,
or when a page shows the new words before Save.

Only the test's and the pick's numbers are swapped. A word changed in
the same mend is the person's and is left alone. Words that never said
the old test (already stale from an earlier mend) are left as they are,
and the mend says so instead of pretending.

## Live receipt

Against a scratch state folder:

```
$ prahari add "Cool the guestroom above 70" --asked "turn the AC on when the guestroom is above 70" \
    --thing "guestroom at 70" --check web_fetch --args '{"url":"https://example.com"}' \
    --pick number --when 'above 70' --every 1h
added b208bcf3: Cool the guestroom above 70 -- every hour, looks at example.com (with web_fetch); tells you when guestroom at 70 is above 70 (once each time it becomes true)

$ prahari edit b208bcf3 --when 'above 80'
updated b208bcf3: Cool the guestroom above 70 -- every hour, looks at example.com (with web_fetch); tells you when guestroom at 70 is above 80 (once each time it becomes true)
  its words still say the old test (name "Cool the guestroom above 70" -> "Cool the guestroom above 80"; asked "turn the AC on when the guestroom is above 70" -> "turn the AC on when the guestroom is above 80"; thing "guestroom at 70" -> "guestroom at 80"); change them too with name, asked, thing

$ prahari edit b208bcf3 --when 'above 82' --carry-words      # first version: silent
$ prahari edit b208bcf3 --when 'above 85' --carry-words      # fixed
updated b208bcf3: Cool the guestroom above 70 -- ... tells you when guestroom at 70 is above 85 ...
  its words don't say its old test (above 82), so they were left as they are; give a new name, asked or thing to change them
```

That was a bug found by this run. The words still said 70 from the
plain mend before, the old test was 80, so there was nothing to carry,
and the first version said nothing at all. Now it says so.
With the words put right, the next mend carries them:

```
$ prahari edit b208bcf3 --when 'above 80' --carry-words
updated b208bcf3: Cool the guestroom above 80 -- ... tells you when guestroom temperature is above 80 ...
  its name, asked now say the new test too
```

The terminal keeps `above 80` as 80.0. The words say 80, because numbers
are compared and written the way a person writes them.

On Prahari's page (headless Chromium, the same folder), **Mend**, then
`above 78` in the test box: the name box read *Cool the guestroom above
78* and the asked box *turn the AC on when the guestroom is above 78*
before Save. After Save the row read the new name and *…is above 78*.
No page errors.

## Where else

* Yantra's watches panel form gains *the thing it watches* and the same
  carrying; what Prahari said back shows in its toast.
* `PATCH /api/watches/ID` returns `notes` beside the card.
* This continues [03 — a watch says what it is for](03-a-watch-says-what-it-is-for.md):
  the words a watch is known by are as much the watch as its test.
