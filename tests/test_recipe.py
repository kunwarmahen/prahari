"""The recipe's form: picks and tests, checked and applied.

The bias these tests encode: A RECIPE A MODEL GOT SLIGHTLY WRONG MUST
FAIL LOUDLY, NOT WATCH FOREVER IN SILENCE. ``{"belw": 50}`` or a pick of
items tested with ``below`` would never fire; each is refused with the
keys that exist. And a pick that finds nothing says so (``found`` is
False), which is how a check that broke is told from a quiet one.
"""

from __future__ import annotations

import pytest

from prahari import recipe
from prahari.recipe import RecipeError

GMAIL = """thread 1a16 · Thu, 22 Oct 2026 12:09 · from Bank <alerts@bank.example> · UNREAD
  subject: Your statement is ready
thread 2b27 · Wed, 21 Oct 2026 08:01 · from Shop <hi@shop.example>
  subject: Order shipped"""


class TestPicks:
    def test_the_first_number(self):
        got = recipe.apply({"number": ""}, "Price: $1,047.10 today")
        assert got.found and got.value == 1047.10

    def test_a_number_a_pattern_finds(self):
        got = recipe.apply({"number": r"Last\s*([\d.,]+)"}, "Open 51.2\nLast 47.10\nHigh 52")
        assert got.value == 47.10

    def test_a_pattern_that_finds_a_place_takes_the_number_after_it(self):
        assert recipe.apply({"number": "Last"}, "Open 51\nLast: 47.1").value == 47.1

    def test_no_number_is_not_found(self):
        assert not recipe.apply({"number": ""}, "sign in to continue").found

    def test_text_and_its_group(self):
        assert recipe.apply({"text": r"status: (\w+)"}, "status: shipped").value == "shipped"

    def test_json_paths(self):
        text = '{"quote": {"last": "47.10"}, "items": [{"id": 1}, {"id": 2}]}'
        assert recipe.apply({"json": "quote.last"}, text).value == 47.10
        assert recipe.apply({"json": "items[*].id"}, text).value == [1, 2]
        assert recipe.apply({"json": "items[1].id"}, text).value == 2
        assert not recipe.apply({"json": "quote.open"}, text).found

    def test_json_after_a_line_of_words(self):
        assert recipe.apply({"json": "a"}, 'found 1:\n{"a": "x"}').value == "x"

    def test_items_by_their_key_with_the_line_below(self):
        got = recipe.apply({"items": r"thread (\w+)"}, GMAIL)
        assert [i.key for i in got.items] == ["1a16", "2b27"]
        assert "Your statement is ready" in got.items[0].line

    def test_no_items_is_still_found(self):
        """An inbox with nothing matching is not a broken check."""
        got = recipe.apply({"items": r"thread (\w+)"}, "No threads.")
        assert got.found and got.items == []

    def test_items_from_a_json_list(self):
        got = recipe.apply({"items_json": "messages[*]", "key": "id"},
                           '{"messages": [{"id": "a", "s": "hi"}, {"id": "b"}]}')
        assert [i.key for i in got.items] == ["a", "b"]

    def test_the_whole_text(self):
        assert recipe.apply({}, "  hello  ").value == "hello"
        assert not recipe.apply({}, "   ").found


class TestTests:
    @pytest.mark.parametrize("when,value,expect", [
        ({"below": 50}, 47.1, True), ({"below": 50}, 50.0, False),
        ({"at_most": 50}, 50.0, True), ({"above": 50}, 51.0, True),
        ({"at_least": 50}, 49.9, False)])
    def test_numbers(self, when, value, expect):
        assert recipe.holds(when, recipe.Picked(found=True, value=value)) is expect

    def test_text(self):
        said = recipe.Picked(found=True, value="Mum: are you coming?")
        assert recipe.holds({"contains": "mum"}, said) is True
        assert recipe.holds({"lacks": "dad"}, said) is True
        assert recipe.holds({"matches": r"coming\?$"}, said) is True
        assert recipe.holds({"equals": "mum"}, said) is False

    def test_tests_about_change_are_the_clocks(self):
        assert recipe.holds({"changed": True}, recipe.Picked(found=True, value=1)) is None


class TestMistakesAreLoud:
    def test_an_unknown_test_names_the_known_ones(self):
        with pytest.raises(RecipeError, match="unknown key.*belw.*known: below"):
            recipe.check_when({"belw": 50}, {"number": ""})

    def test_two_tests_at_once(self):
        with pytest.raises(RecipeError, match="exactly one test"):
            recipe.check_when({"below": 50, "above": 10}, {"number": ""})

    def test_a_number_test_needs_a_number(self):
        with pytest.raises(RecipeError, match="is a number"):
            recipe.check_when({"below": "fifty"}, {"number": ""})
        with pytest.raises(RecipeError, match="compares a number"):
            recipe.check_when({"below": 50}, {"text": ""})

    def test_new_needs_items(self):
        with pytest.raises(RecipeError, match="needs items"):
            recipe.check_when({"new": True}, {"number": ""})

    def test_items_are_not_compared_with_a_number(self):
        with pytest.raises(RecipeError, match="tested with new, any or ask"):
            recipe.check_when({"contains": "x"}, {"items": "x"})

    def test_a_bad_pattern_says_so(self):
        with pytest.raises(RecipeError, match="not a pattern"):
            recipe.check_pick({"items": "thread (\\w+"})

    def test_an_unknown_pick(self):
        with pytest.raises(RecipeError, match="unknown key.*price"):
            recipe.check_pick({"price": ""})


class TestEvery:
    def test_short_forms(self):
        assert recipe.every("30m").total_seconds() == 1800
        assert recipe.every("3 hours").total_seconds() == 3 * 3600
        assert recipe.every("1d").days == 1

    def test_a_floor_and_a_ceiling(self):
        with pytest.raises(RecipeError, match="more often than every 5 minutes"):
            recipe.every("1m")
        with pytest.raises(RecipeError, match="Samay"):
            recipe.every("30d")

    def test_nonsense(self):
        with pytest.raises(RecipeError, match="how often to look"):
            recipe.every("sometimes")


class TestShortForms:
    def test_picks(self):
        assert recipe.pick_from_text("number") == {"number": ""}
        assert recipe.pick_from_text(r"items:thread (\w+)") == {"items": r"thread (\w+)"}
        assert recipe.pick_from_text("items_json:messages[*]:id") == {
            "items_json": "messages[*]", "key": "id"}
        assert recipe.pick_from_text("") == {}

    def test_whens(self):
        assert recipe.when_from_text("below 1,200", {"number": ""}) == {"below": 1200.0}
        assert recipe.when_from_text("new", {"items": "x"}) == {"new": True}
        assert recipe.when_from_text("contains Mum", {"json": "title"}) == {
            "contains": "Mum"}
        assert recipe.when_from_text("ask is it an invoice?", {}) == {
            "ask": "is it an invoice?"}

    def test_the_sentence(self):
        said = recipe.sentence({"tool": "web_fetch"}, "", {"number": ""}, {"below": 50},
                               "3h")
        assert said == ("every 3 hours, looks with web_fetch; tells you when the number "
                        "is below 50 (once each time it becomes true)")
        assert recipe.sentence({}, "whatsapp", {"json": "title"}, {"contains": "Mum"},
                               "") == "when whatsapp sends something, if the value says 'Mum'"
