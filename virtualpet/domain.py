"""Core domain model: vitals, the pet and the state machines.

This module knows nothing about tuning values (see :mod:`virtualpet.config`)
and nothing about Streamlit, which keeps the rules easy to test in isolation.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - import cycle guard, typing only
    from .config import StatTuning, Thresholds

MIN_STAT_VALUE = 0.0


class StatKind(Enum):
    """The three vitals the player must keep alive."""

    HUNGER = "hunger"
    ENERGY = "energy"
    HAPPINESS = "happiness"


class ActionKind(Enum):
    """The three interactions the player can trigger."""

    FEED = "feed"
    PLAY = "play"
    SLEEP = "sleep"


class PetState(Enum):
    """Coarse wellbeing buckets, ordered from best to worst."""

    THRIVING = "thriving"
    OK = "ok"
    LOW = "low"
    CRITICAL = "critical"
    DEAD = "dead"


class GameStatus(Enum):
    """Lifecycle of a single playthrough."""

    PLAYING = "playing"
    DEFEAT = "defeat"


class Stat:
    """A single vital, permanently clamped between 0 and its maximum."""

    __slots__ = ("kind", "maximum", "value")

    def __init__(self, kind: StatKind, value: float, maximum: float) -> None:
        self.kind = kind
        self.maximum = maximum
        self.value = self._clamp(value)

    @property
    def ratio(self) -> float:
        """Progress towards the maximum, in the ``0.0``-``1.0`` range."""
        if self.maximum <= MIN_STAT_VALUE:
            return 0.0
        return self.value / self.maximum

    @property
    def is_empty(self) -> bool:
        return self.value <= MIN_STAT_VALUE

    def increase(self, amount: float) -> float:
        """Add ``amount`` (saturating) and return the signed delta applied."""
        before = self.value
        self.value = self._clamp(self.value + amount)
        return self.value - before

    def decrease(self, amount: float, floor: float = MIN_STAT_VALUE) -> float:
        """Subtract ``amount`` (saturating) and return the signed delta applied.

        ``floor`` keeps a value from dropping below it; actions use it so they
        can never be the direct cause of a defeat.
        """
        before = self.value
        safe_floor = min(max(floor, MIN_STAT_VALUE), self.maximum)
        self.value = min(max(self.value - amount, safe_floor), self.maximum)
        return self.value - before

    def _clamp(self, value: float) -> float:
        return min(max(value, MIN_STAT_VALUE), self.maximum)

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"Stat({self.kind.name}={self.value:.1f}/{self.maximum:.0f})"


@dataclass(frozen=True)
class Defeat:
    """Why the pet ran away and how long it lasted."""

    stat: StatKind
    seconds_survived: float
    cause: str
    event_title: str | None = None


class Pet:
    """The creature the player takes care of.

    Owns one :class:`Stat` per :class:`StatKind` and the rules that turn raw
    numbers into a mood.
    """

    def __init__(
        self,
        name: str,
        tunings: Mapping[StatKind, StatTuning],
        thresholds: Thresholds,
    ) -> None:
        self.name = name
        self._tunings = dict(tunings)
        self._thresholds = thresholds
        self._stats = {
            kind: Stat(kind, tuning.start, tuning.maximum)
            for kind, tuning in self._tunings.items()
        }

    @property
    def stats(self) -> Mapping[StatKind, Stat]:
        return self._stats

    @property
    def is_dead(self) -> bool:
        return any(stat.is_empty for stat in self._stats.values())

    def get(self, kind: StatKind) -> float:
        return self._stats[kind].value

    def maximum(self, kind: StatKind) -> float:
        return self._stats[kind].maximum

    def ratio(self, kind: StatKind) -> float:
        return self._stats[kind].ratio

    def increase(self, kind: StatKind, amount: float) -> float:
        """Feed a stat back up; returns the signed delta actually applied."""
        return self._stats[kind].increase(amount)

    def decrease(
        self,
        kind: StatKind,
        amount: float,
        floor: float = MIN_STAT_VALUE,
    ) -> float:
        """Drain a stat; returns the signed delta actually applied."""
        return self._stats[kind].decrease(amount, floor=floor)

    def apply_decay(self, delta_s: float) -> None:
        """Drain every stat proportionally to ``delta_s`` seconds."""
        if delta_s <= MIN_STAT_VALUE:
            return
        for kind, stat in self._stats.items():
            stat.decrease(self._tunings[kind].decay_per_second * delta_s)

    def lowest(self) -> StatKind:
        """Return the stat closest to zero (first kind on a tie)."""
        return min(StatKind, key=lambda kind: self._stats[kind].value)

    def lowest_value(self) -> float:
        return self._stats[self.lowest()].value

    def state(self) -> PetState:
        """Classify the pet's mood from its worst stat."""
        if self.is_dead:
            return PetState.DEAD
        lowest = self.lowest_value()
        if lowest <= self._thresholds.critical:
            return PetState.CRITICAL
        if lowest < self._thresholds.low:
            return PetState.LOW
        if lowest >= self._thresholds.thrive:
            return PetState.THRIVING
        return PetState.OK
