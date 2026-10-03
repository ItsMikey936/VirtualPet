"""The pet's dialogue, bucketed by mood.

Each mood owns several lines. They are served from a shuffled bag, so a line is
never repeated until the whole bucket has been seen. ``{name}`` and ``{stat}``
are resolved without :meth:`str.format` (see :mod:`virtualpet.text`).
"""

from __future__ import annotations

import random
from collections import deque
from collections.abc import Mapping

from .domain import PetState
from .text import render

THRIVING_LINES: tuple[str, ...] = (
    "Everything is perfect right now. Best day ever!",
    "I feel great and I am extremely fluffy.",
    "Let us do that thing again sometime!",
    "I have never been this content.",
    "Life is good: full bowl, sunny window, closed blinds.",
    "You are my favourite human. Do not tell the others.",
    "I am so comfy I could fall asleep standing up.",
    "BEEP. Just kidding. Still very happy though!",
)

OK_LINES: tuple[str, ...] = (
    "Not bad at all. I could get used to this.",
    "Things are fine. Probably fine.",
    "I have a vague feeling I am forgetting something.",
    "I am alright. A little bored, maybe.",
    "Nothing urgent, just checking in on you.",
    "Still here, still quietly waiting for a treat.",
    "The afternoon is going by slowly.",
)

LOW_LINES: tuple[str, ...] = (
    "My {stat} is getting low. Maybe do something about it?",
    "Honestly? My {stat} needs some attention.",
    "I would like to talk about my {stat}.",
    "My {stat} is not doing so great, and neither am I.",
    "Please pay some attention to my {stat}.",
    "Nothing would make me happier than help with my {stat}.",
    "Do not forget about my {stat}!",
    "I keep thinking about my {stat} instead of playing.",
)

CRITICAL_LINES: tuple[str, ...] = (
    "My {stat} is almost gone! HELP!",
    "This is an emergency: my {stat} is nearly empty!",
    "I am not joking, fix my {stat} right now!",
    "Everything hurts because of my {stat}.",
    "My {stat} is at zero and you are still sitting there!",
    "If my {stat} gets any worse I will run away!",
    "Please, please, please. My {stat}!",
    "Last warning about my {stat}!",
)

DEAD_LINES: tuple[str, ...] = (
    "You let me down.",
    "I thought we were friends...",
    "This is goodbye.",
    "I am leaving. Look for me in the park.",
    "I trusted you with my {stat}.",
    "Goodbye. Remember me.",
)

GREETINGS: tuple[str, ...] = (
    "Hi! I am {name}. Feed me, play with me, put me to bed.",
    "Hello! I am {name} and I need you to keep all three bars off zero.",
    "Good to see you! {name} is hungry and not afraid to say so.",
)

DIALOGUE: Mapping[PetState, tuple[str, ...]] = {
    PetState.THRIVING: THRIVING_LINES,
    PetState.OK: OK_LINES,
    PetState.LOW: LOW_LINES,
    PetState.CRITICAL: CRITICAL_LINES,
    PetState.DEAD: DEAD_LINES,
}


class MessageBank:
    """Mood-aware dialogue served without immediate repeats."""

    def __init__(self, dialogue: Mapping[PetState, tuple[str, ...]] = DIALOGUE) -> None:
        self._dialogue = dict(dialogue)
        self._bags: dict[PetState, deque[str]] = {}

    def lines_for(self, state: PetState) -> tuple[str, ...]:
        return self._dialogue.get(state, ())

    def pick(
        self,
        state: PetState,
        rng: random.Random,
        name: str = "your pet",
        stat_label: str = "stats",
    ) -> str:
        """Return one line for ``state``, rendered with name and stat label."""
        lines = self.lines_for(state)
        if not lines:
            return ""
        bag = self._bags.get(state)
        if bag is None or not bag:
            bag = deque(sorted(lines))
            rng.shuffle(bag)
            self._bags[state] = bag
        return render(bag.popleft(), name=name, stat=stat_label)

    def greeting(
        self,
        rng: random.Random,
        name: str = "your pet",
    ) -> str:
        """First thing the pet says when a game starts."""
        return render(rng.choice(GREETINGS), name=name)
