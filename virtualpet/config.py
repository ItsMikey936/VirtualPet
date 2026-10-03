"""Every tunable number of Virtual Pet.

No other module defines gameplay constants: decay rates, action gains,
cooldowns, event cadence, dialogue cadence and mood thresholds all live here,
so the game can be rebalanced without touching a line of logic.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace

from .domain import ActionKind, PetState, StatKind

SECONDS_PER_MINUTE = 60.0


@dataclass(frozen=True)
class Effect:
    """A signed change to one stat produced by an action."""

    kind: StatKind
    amount: float

    @property
    def is_cost(self) -> bool:
        return self.amount < 0


@dataclass(frozen=True)
class StatTuning:
    """Definition of one vital."""

    kind: StatKind
    label: str
    icon: str
    start: float = 100.0
    maximum: float = 100.0
    decay_per_minute: float = 10.0

    @property
    def decay_per_second(self) -> float:
        return self.decay_per_minute / SECONDS_PER_MINUTE


@dataclass(frozen=True)
class ActionTuning:
    """Everything needed to run one action."""

    kind: ActionKind
    label: str
    icon: str
    message: str
    effects: tuple[Effect, ...]
    cooldown_s: float = 0.0
    cooldown_message: str = "Not yet!"
    full_message: str = "Nothing to do right now."


@dataclass(frozen=True)
class Thresholds:
    """Mood boundaries, expressed on the lowest stat."""

    thrive: float = 70.0
    low: float = 30.0
    critical: float = 12.0


@dataclass(frozen=True)
class SpeechTuning:
    """How often the pet talks, per mood."""

    intervals_s: Mapping[PetState, float] = field(
        default_factory=lambda: {
            PetState.THRIVING: 45.0,
            PetState.OK: 35.0,
            PetState.LOW: 20.0,
            PetState.CRITICAL: 10.0,
            PetState.DEAD: 0.0,
        }
    )

    def interval_for(self, state: PetState) -> float:
        return self.intervals_s.get(state, 30.0)


@dataclass(frozen=True)
class EventTuning:
    """Random event cadence. Delays are drawn from an exponential law."""

    mean_interval_s: float = 35.0
    min_interval_s: float = 6.0
    max_interval_s: float = 120.0


_DEFAULT_STATS: dict[StatKind, StatTuning] = {
    StatKind.HUNGER: StatTuning(
        kind=StatKind.HUNGER,
        label="Hunger",
        icon="🍖",
        decay_per_minute=12.0,
    ),
    StatKind.ENERGY: StatTuning(
        kind=StatKind.ENERGY,
        label="Energy",
        icon="⚡",
        decay_per_minute=10.5,
    ),
    StatKind.HAPPINESS: StatTuning(
        kind=StatKind.HAPPINESS,
        label="Happiness",
        icon="🎾",
        decay_per_minute=10.0,
    ),
}

_DEFAULT_ACTIONS: dict[ActionKind, ActionTuning] = {
    ActionKind.FEED: ActionTuning(
        kind=ActionKind.FEED,
        label="Feed",
        icon="🍖",
        message="Yum! {name} inhales the food.",
        effects=(Effect(StatKind.HUNGER, 35.0),),
        cooldown_s=2.0,
        cooldown_message="{name} is still chewing. One moment.",
        full_message="{name} is stuffed and refuses seconds.",
    ),
    ActionKind.PLAY: ActionTuning(
        kind=ActionKind.PLAY,
        label="Play",
        icon="🎾",
        message="{name} chases the squeaky ball around the room.",
        effects=(
            Effect(StatKind.HAPPINESS, 28.0),
            Effect(StatKind.ENERGY, -10.0),
            Effect(StatKind.HUNGER, -5.0),
        ),
        cooldown_s=5.0,
        cooldown_message="{name} is out of breath. Catch your breath.",
        full_message="{name} is already at peak happiness.",
    ),
    ActionKind.SLEEP: ActionTuning(
        kind=ActionKind.SLEEP,
        label="Sleep",
        icon="💤",
        message="{name} curls up and starts to snore.",
        effects=(
            Effect(StatKind.ENERGY, 40.0),
            Effect(StatKind.HUNGER, -6.0),
            Effect(StatKind.HAPPINESS, -2.0),
        ),
        cooldown_s=8.0,
        cooldown_message="{name} is too wired to fall asleep yet.",
        full_message="{name} is wide awake and refuses to nap.",
    ),
}


@dataclass(frozen=True)
class GameConfig:
    """Single source of truth for the whole game balance."""

    name: str = "Nimbus"
    stats: Mapping[StatKind, StatTuning] = field(
        default_factory=lambda: dict(_DEFAULT_STATS)
    )
    actions: Mapping[ActionKind, ActionTuning] = field(
        default_factory=lambda: dict(_DEFAULT_ACTIONS)
    )
    thresholds: Thresholds = field(default_factory=Thresholds)
    speech: SpeechTuning = field(default_factory=SpeechTuning)
    events: EventTuning = field(default_factory=EventTuning)

    # A player action may push a stat down to this value but never below it:
    # only decay and random events are allowed to end the game.
    action_floor: float = 1.0
    # How often the UI asks the engine for an update.
    tick_s: float = 1.0
    # A session break longer than this is forgiven (tab closed, laptop asleep).
    catch_up_cap_s: float = 300.0
    # Safety valve: never flood the log after a long stall.
    max_events_per_advance: int = 8
    log_size: int = 12

    def stat(self, kind: StatKind) -> StatTuning:
        return self.stats[kind]

    def action(self, kind: ActionKind) -> ActionTuning:
        return self.actions[kind]

    def label(self, kind: StatKind) -> str:
        return self.stat(kind).label

    def icon(self, kind: StatKind) -> str:
        return self.stat(kind).icon

    def with_overrides(self, **overrides: object) -> GameConfig:
        """Return a copy with some fields replaced."""
        return replace(self, **overrides)  # type: ignore[arg-type]


DEFAULT_CONFIG = GameConfig()
