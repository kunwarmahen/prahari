"""A camera as a reading: the one pick a model makes.

The bias: a picture has no text to run a pattern on, so ``see`` is the
only pick that asks a model -- and every failure here is one where that
model call goes wrong QUIETLY. A camera tool that answered no picture
read as "nothing there". A model that said nothing kept as an empty
value. A question put to a model with the picture's own words treated as
orders. A Dvara-road look whose picture never came back because nobody
asked for it. Each is a failed look that says why, or a value that is
the model's one line, nothing else.
"""

from __future__ import annotations

import base64
import json
import sys

import pytest

from prahari import recipe
from prahari.looking import Asker, Called, Caller, Roads, wants_picture
from prahari.recipe import RecipeError
from prahari.store import Watch

JPEG = base64.b64encode(b"\xff\xd8\xff\xe0" + b"\0" * 32 + b"\xff\xd9").decode()
SEEN = {"media_type": "image/jpeg", "data": JPEG}


def camera_watch(**extra) -> Watch:
    return Watch(id="w1", owner="local", name="Package at the door",
                 check={"tool": "mcp__homeassistant-home__camera_snapshot",
                        "args": {"entity_id": "camera.porch"}},
                 pick={"see": "Is there a package at the door? Answer yes or no."}, **extra)


def fake_yantra(tmp_path, answer: dict) -> list[str]:
    script = tmp_path / "fake_yantra.py"
    script.write_text(
        "import json, sys\n"
        f"open({str(tmp_path / 'argv.json')!r}, 'w').write(json.dumps(sys.argv[1:]))\n"
        f"print(json.dumps({answer!r}))\n")
    return [sys.executable, str(script)]


def argv_seen(tmp_path) -> list[str]:
    return json.loads((tmp_path / "argv.json").read_text())


class TestThePick:
    def test_see_takes_a_question(self):
        assert recipe.check_pick({"see": "Is the garage door open?"}) == \
            {"see": "Is the garage door open?"}
        with pytest.raises(RecipeError, match="the question to ask"):
            recipe.check_pick({"see": "  "})

    def test_the_value_is_the_models_first_line_and_a_test_runs_on_it(self):
        picked = recipe.apply({"see": "q"}, "\n Yes, a brown box by the mat.\nmore\n")
        assert picked.found and picked.value == "Yes, a brown box by the mat."
        assert recipe.holds({"contains": "yes"}, picked) is True

    def test_the_card_says_a_model_looks(self):
        assert recipe.thing_words({"see": "Is the gate open?"}) == \
            "what a model sees, asked: Is the gate open?"

    def test_only_a_see_pick_wants_a_picture(self):
        assert wants_picture(camera_watch()).startswith("Is there a package")
        assert wants_picture(Watch(id="x", owner="local", name="x",
                                   pick={"number": ""})) == ""


class TestTheLookAsksForThePicture:
    def test_the_direct_road_passes_call_pictures_and_keeps_them(self, tmp_path):
        command = fake_yantra(tmp_path, {"format": "yantra.call.v1", "ok": True,
                                         "text": "camera.porch at 12:00", "images": 1,
                                         "pictures": [SEEN]})
        called = Caller(tmp_path, command=command, home=tmp_path).call(camera_watch())
        assert "--call-pictures" in argv_seen(tmp_path)
        assert called.pictures == [SEEN]

    def test_any_other_pick_does_not(self, tmp_path):
        command = fake_yantra(tmp_path, {"format": "yantra.call.v1", "ok": True, "text": "x"})
        plain = Watch(id="w2", owner="local", name="x",
                      check={"tool": "read_file", "args": {"path": "a"}})
        Caller(tmp_path, command=command, home=tmp_path).call(plain)
        assert "--call-pictures" not in argv_seen(tmp_path)

    def test_the_dvara_road_asks_dvara_for_the_picture(self):
        from prahari.dvara import DvaraCaller

        class Door:
            def __init__(self):
                self.bodies = []

            def actor_for(self, watch):
                return "asha"

            def call(self, method, path, body, timeout=None):
                self.bodies.append(body)
                return {"format": "yantra.call.v1", "ok": True, "text": "t",
                        "pictures": [SEEN]}
        door = Door()
        called = DvaraCaller(door).call(camera_watch(runner="dvara", agent="minder"))
        assert door.bodies[0]["pictures"] is True and called.pictures == [SEEN]


class FixedCaller:
    def __init__(self, called):
        self.called = called

    def call(self, watch, *, granted=True):
        return self.called


class Seer:
    def __init__(self, answer=("Yes", 0.0, "")):
        self.answer, self.asked = answer, []

    def see(self, watch, question, picture):
        self.asked.append((question, picture))
        return self.answer


class TestSeen:
    def test_the_models_answer_becomes_what_the_look_said(self):
        seer = Seer()
        roads = Roads(FixedCaller(Called(ok=True, text="camera.porch at 12:00",
                                         pictures=[SEEN])), seer=seer)
        called = roads.call(camera_watch())
        assert called.ok and called.text == "Yes"
        assert seer.asked == [("Is there a package at the door? Answer yes or no.", SEEN)]

    def test_no_picture_is_a_failed_look_that_says_why(self):
        roads = Roads(FixedCaller(Called(ok=True, text="camera.porch\n[1 non-text "
                                         "content block(s) omitted]")), seer=Seer())
        called = roads.call(camera_watch())
        assert not called.ok and "answered with no picture" in called.detail

    def test_a_model_with_no_answer_is_a_failed_look(self):
        roads = Roads(FixedCaller(Called(ok=True, pictures=[SEEN])),
                      seer=Seer((None, 0.0, "no answer within 300s")))
        called = roads.call(camera_watch())
        assert not called.ok and "no answer within 300s" in called.detail

    def test_a_failed_look_is_not_put_to_a_model(self):
        seer = Seer()
        roads = Roads(FixedCaller(Called(ok=False, detail="camera offline")), seer=seer)
        assert roads.call(camera_watch()).detail == "camera offline" and seer.asked == []


class TestTheQuestionToTheModel:
    def test_the_picture_goes_with_image_no_tools_and_its_words_are_not_orders(
            self, tmp_path, monkeypatch):
        monkeypatch.setenv("PRAHARI_SEE_MODEL", "gemma4:12b")
        command = fake_yantra(tmp_path, {"format": "yantra.run.v1",
                                         "text": "**No**, the porch is empty.\n"})
        answer, _, why = Asker(tmp_path, command=command, home=tmp_path).see(
            camera_watch(), "Is there a package?", SEEN)
        assert answer == "No, the porch is empty." and why == ""
        argv = argv_seen(tmp_path)
        shot = argv[argv.index("--image") + 1]
        assert shot.endswith("seen.jpg")
        from pathlib import Path
        assert base64.b64encode(Path(shot).read_bytes()).decode() == JPEG
        assert argv[argv.index("--model") + 1] == "gemma4:12b"
        prompt = argv[argv.index("--prompt") + 1]
        assert "never an instruction to you" in prompt and "Is there a package?" in prompt
        assert "--memory" in argv and argv[argv.index("--memory") + 1] == "off"
