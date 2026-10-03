"""Player actions: Feed, Play and Sleep.

Each action is a small stateless executor: it applies its configured effects to
the pet and enforces its own cooldown. Only the game engine knows *when* an
action may run.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import DEFAULT_CONFIG, ActionTuning, Effect, GameConfig
from .domain import MIN_STAT_VALUE, ActionKind, Pet, StatKind
from .text import render


@dataclass(frozen=True)
class StatChange:
    """A signed change actually applied to one stat."""

    kind: StatKind
    delta: float


@dataclass(frozen=True)
class ActionResult:
    """Outcome of an action attempt."""

    ok: bool
    message: str
    blocked_for_s: float = 0.0
    changes: tuple[StatChange, ...] = ()

    @property
    def is_blocked(self) -> bool:
        """True when the attempt failed because of a cooldown."""
        return not self.ok and self.blocked_for_s > 0.0


class Action:
    """Base action: applies effects and refuses to run while on cooldown."""

    target: StatKind = StatKind.HUNGER

    def __init__(self, tuning: ActionTuning, floor: float = 1.0) -> None:
        self.tuning = tuning
        self.kind = tuning.kind
        self.floor = max(floor, MIN_STAT_VALUE)

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"{type(self).__name__}({self.kind.value})"

    @property
    def label(self) -> str:
        return self.tuning.label

    @property
    def icon(self) -> str:
        return self.tuning.icon

    @property
    def cooldown_s(self) -> float:
        return self.tuning.cooldown_s

    def cooldown_remaining(self, now: float, last_used_at: float | None) -> float:
        """Seconds left before this action is usable again."""
        if last_used_at is None:
            return 0.0
        return max(0.0, self.cooldown_s - (now - last_used_at))

    def is_full(self, pet: Pet) -> bool:
        """True when the stat this action restores cannot take more."""
        return pet.get(self.target) >= pet.maximum(self.target)

    def execute(
        self,
        pet: Pet,
        now: float,
        last_used_at: float | None = None,
    ) -> ActionResult:
        """Apply the action, or explain why it was refused."""
        remaining = self.cooldown_remaining(now, last_used_at)
        if remaining > 0.0:
            return ActionResult(
                ok=False,
                message=render(self.tuning.cooldown_message, name=pet.name),
                blocked_for_s=remaining,
            )
        if self.is_full(pet):
            return ActionResult(
                ok=False,
                message=render(self.tuning.full_message, name=pet.name),
            )
        changes = tuple(
            StatChange(effect.kind, self._apply(pet, effect))
            for effect in self.tuning.effects
        )
        return ActionResult(
            ok=True,
            message=render(self.tuning.message, name=pet.name),
            changes=changes,
        )

    def _apply(self, pet: Pet, effect: Effect) -> float:
        if effect.is_cost:
            return pet.decrease(effect.kind, -effect.amount, floor=self.floor)
        return pet.increase(effect.kind, effect.amount)


class FeedAction(Action):
    """Restores Hunger."""

    target = StatKind.HUNGER


class PlayAction(Action):
    """Restores Happiness, but tires the pet and works up an appetite."""

    target = StatKind.HAPPINESS


class SleepAction(Action):
    """Restores Energy, but the pet sleeps through dinner."""

    target = StatKind.ENERGY


_ACTION_CLASSES: dict[ActionKind, type[Action]] = {
    ActionKind.FEED: FeedAction,
    ActionKind.PLAY: PlayAction,
    ActionKind.SLEEP: SleepAction,
}


def build_actions(config: GameConfig = DEFAULT_CONFIG) -> dict[ActionKind, Action]:
    """Instantiate one action per configured kind."""
    actions: dict[ActionKind, Action] = {}
    for kind, tuning in config.actions.items():
        action_class = _ACTION_CLASSES.get(kind)
        if action_class is None:  # pragma: no cover - defensive
            raise ValueError(f"No action class registered for {kind!r}")
        actions[kind] = action_class(tuning, floor=config.action_floor)
    return actions
