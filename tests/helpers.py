"""Fakes for the tests: a caller that answers what it is told to, a runner
that records the prompt it was given, a notifier that keeps what it was
asked to send, an asker with a fixed answer, and a clock you move by hand.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from prahari.clock import Clock
from prahari.looking import Called, TurnResult
from prahari.store import Store

START = datetime(2026, 10, 22, 9, 0, tzinfo=UTC)


class Hands:
    """The time, moved by hand."""

    def __init__(self, at: datetime = START) -> None:
        self.at = at

    def __call__(self) -> datetime:
        return self.at

    def move(self, **step) -> None:
        self.at += timedelta(**step)


class FakeCaller:
    """Answers each look with the next of ``answers`` (the last repeats)."""

    def __init__(self, *answers: Called | str) -> None:
        self.answers = [a if isinstance(a, Called) else Called(ok=True, text=a)
                        for a in answers]
        self.calls: list[tuple[dict, bool]] = []

    def say(self, *answers: Called | str) -> None:
        self.answers = [a if isinstance(a, Called) else Called(ok=True, text=a)
                        for a in answers]

    def call(self, watch, *, granted: bool = True) -> Called:
        self.calls.append((dict(watch.check), granted))
        if len(self.answers) > 1:
            return self.answers.pop(0)
        return self.answers[0]


class FakeRunner:
    def __init__(self, result: TurnResult | None = None) -> None:
        self.result = result or TurnResult(ok=True, text="Done: told them.")
        self.prompts: list[str] = []

    def run(self, watch, prompt: str) -> TurnResult:
        self.prompts.append(prompt)
        return self.result


class FakeNotifier:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send(self, watch, text: str) -> bool:
        self.sent.append((watch.id, text))
        return True


class FakeAsker:
    def __init__(self, yes: bool | None = True) -> None:
        self.yes = yes
        self.asked: list[str] = []

    def ask(self, watch, question: str, shown: str):
        self.asked.append(shown)
        return self.yes, 0.0, "" if self.yes is not None else "no answer"


def make_clock(tmp_path, caller, *, runner=None, asker=None, notifier=None, now=None):
    store = Store(tmp_path / "prahari.sqlite3")
    clock = Clock(store, caller, {"direct": runner or FakeRunner()}, asker=asker,
                  notifier=notifier if notifier is not None else FakeNotifier(),
                  now=now or Hands(), workers=2)
    return store, clock
