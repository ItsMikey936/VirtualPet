"""Random events that chip away at the pet's vitals.

Events are drawn at random but *scheduled by clock*: :meth:`EventPool.schedule_delay`
draws from an exponential distribution, so the number of events depends on the
elapsed time, not on how often the UI reran.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .config import DEFAULT_CONFIG, GameConfig
from .domain import StatKind


@dataclass(frozen=True)
class Event:
    """One bad thing that happens to the pet."""

    id: str
    title: str
    icon: str
    message: str
    target: StatKind
    penalty: float
    weight: float = 1.0


EVENTS: tuple[Event, ...] = (
    Event(
        id="squirrel",
        title="Squirrel Sighting",
        icon="🐿️",
        message="A squirrel crossed the garden and now dinner is the only topic.",
        target=StatKind.HUNGER,
        penalty=18.0,
        weight=1.0,
    ),
    Event(
        id="empty_bowl",
        title="The Empty Bowl",
        icon="🥣",
        message="The bowl has been empty for a while and the sound is unbearable.",
        target=StatKind.HUNGER,
        penalty=12.0,
        weight=1.2,
    ),
    Event(
        id="trash_heist",
        title="Trash Heist",
        icon="🗑️",
        message="The pet raided the kitchen bin and found only wrappers.",
        target=StatKind.HUNGER,
        penalty=10.0,
        weight=0.8,
    ),
    Event(
        id="spice",
        title="The Spicy Counter",
        icon="🌶️",
        message="Something spicy was left on the counter. The pet licked it.",
        target=StatKind.HUNGER,
        penalty=15.0,
        weight=0.7,
    ),
    Event(
        id="zoomies",
        title="3 AM Zoomies",
        icon="🌙",
        message="It is three in the morning and the pet is convinced it is party time.",
        target=StatKind.ENERGY,
        penalty=20.0,
        weight=0.8,
    ),
    Event(
        id="thunderstorm",
        title="Thunderstorm",
        icon="⛈️",
        message="Thunder rolled in and the pet refused to close its eyes.",
        target=StatKind.ENERGY,
        penalty=16.0,
        weight=0.9,
    ),
    Event(
        id="neighbor_dog",
        title="Barking Neighbor",
        icon="🐕",
        message="The neighbour's dog barked for two hours straight.",
        target=StatKind.ENERGY,
        penalty=14.0,
        weight=1.0,
    ),
    Event(
        id="sugar_crash",
        title="Sugar Crash",
        icon="🍬",
        message="Far too many treats and not enough energy to keep up.",
        target=StatKind.ENERGY,
        penalty=12.0,
        weight=0.9,
    ),
    Event(
        id="lost_toy",
        title="The Lost Squeaky Toy",
        icon="🧸",
        message="The favourite squeaky toy vanished somewhere under the couch.",
        target=StatKind.HAPPINESS,
        penalty=16.0,
        weight=1.0,
    ),
    Event(
        id="ignored",
        title="Ignored Command",
        icon="🚪",
        message="You looked busy. The pet sat by the door and sighed.",
        target=StatKind.HAPPINESS,
        penalty=13.0,
        weight=1.1,
    ),
    Event(
        id="bored_afternoon",
        title="Same Sunny Window",
        icon="🪟",
        message="Third afternoon in a row on the very same windowsill.",
        target=StatKind.HAPPINESS,
        penalty=11.0,
        weight=1.2,
    ),
    Event(
        id="mirror_rivalry",
        title="Mirror Rivalry",
        icon="🪞",
        message="The pet argued with its own reflection for ten minutes.",
        target=StatKind.HAPPINESS,
        penalty=15.0,
        weight=0.7,
    ),
)


class EventPool:
    """Weighted collection of events plus their timing law."""

    def __init__(
        self,
        config: GameConfig = DEFAULT_CONFIG,
        events: tuple[Event, ...] = EVENTS,
    ) -> None:
        self.config = config
        self.events = tuple(events)

    def draw(self, rng: random.Random) -> Event:
        """Pick one event at random, honouring the configured weights."""
        weights = [event.weight for event in self.events]
        return rng.choices(self.events, weights=weights, k=1)[0]

    def schedule_delay(self, rng: random.Random) -> float:
        """Seconds until the next event (exponential law, clamped)."""
        tuning = self.config.events
        mean = max(tuning.mean_interval_s, 0.001)
        delay = rng.expovariate(1.0 / mean)
        return min(max(delay, tuning.min_interval_s), tuning.max_interval_s)
