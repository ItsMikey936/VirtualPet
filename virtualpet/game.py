"""The rules engine.

:class:`Game` is pure Python: it never imports Streamlit and it never blocks.
Time is *injected*, which makes the whole simulation deterministic under test
and lets the UI decide how often to ask for an update.
"""

from __future__ import annotations

import math
import random
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

from .actions import Action, ActionResult, build_actions
from .config import DEFAULT_CONFIG, GameConfig
from .domain import ActionKind, Defeat, GameStatus, Pet, PetState
from .events import Event, EventPool
from .messages import MessageBank

CAUSE_DECAY = "decay"
CAUSE_EVENT = "event"


@dataclass(frozen=True)
class LogEntry:
    """One line of the game's history."""

    kind: str  # "action" | "event" | "speech" | "system"
    text: str
    at_s: float


@dataclass(frozen=True)
class TickReport:
    """What changed while the clock moved forward."""

    elapsed_s: float = 0.0
    events: tuple[Event, ...] = ()
    speech: str | None = None
    game_over: bool = False
    death: Defeat | None = None


@dataclass
class Game:
    """One playthrough of Virtual Pet."""

    config: GameConfig = DEFAULT_CONFIG
    name: str = DEFAULT_CONFIG.name
    seed: int | None = None
    clock: Callable[[], float] = time.monotonic

    rng: random.Random = field(init=False, repr=False)
    pool: EventPool = field(init=False, repr=False)
    messages: MessageBank = field(init=False, repr=False)
    actions: dict[ActionKind, Action] = field(init=False, repr=False)
    pet: Pet = field(init=False, repr=False)
    status: GameStatus = field(init=False, default=GameStatus.PLAYING)
    death: Defeat | None = field(init=False, default=None)
    log: deque[LogEntry] = field(init=False, repr=False)
    last_speech: str = field(init=False, default="")
    last_event: Event | None = field(init=False, default=None)
    started_at: float = field(init=False, default=0.0)
    elapsed_s: float = field(init=False, default=0.0)
    _last_advance_at: float = field(init=False, default=0.0, repr=False)
    _next_event_at: float = field(init=False, default=0.0, repr=False)
    _next_speech_at: float = field(init=False, default=0.0, repr=False)
    _cooldowns: dict[ActionKind, float] = field(
        init=False, default_factory=dict, repr=False
    )

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)
        self.pool = EventPool(self.config)
        self.messages = MessageBank()
        self.actions = build_actions(self.config)
        self.log = deque(maxlen=self.config.log_size)
        self._reset(self.clock())

    # ------------------------------------------------------------------ setup

    def _reset(self, now: float) -> None:
        """Start a brand new playthrough, reusing this object."""
        self.pet = Pet(self.name, self.config.stats, self.config.thresholds)
        self.status = GameStatus.PLAYING
        self.death = None
        self.last_event = None
        self._cooldowns.clear()
        self.log.clear()
        self.started_at = now
        self.elapsed_s = 0.0
        self._last_advance_at = now
        self._next_event_at = now + self.pool.schedule_delay(self.rng)
        state = self.pet.state()
        self._next_speech_at = now + self.config.speech.interval_for(state)
        self.last_speech = self.messages.greeting(self.rng, self.pet.name)
        self._log("speech", self.last_speech, now)

    def restart(self, seed: int | None = None) -> None:
        """Reset the game in place, optionally with a new random seed."""
        if seed is not None:
            self.seed = seed
            self.rng = random.Random(seed)
        self._reset(self.clock())

    # ------------------------------------------------------------------ state

    @property
    def is_over(self) -> bool:
        return self.status is GameStatus.DEFEAT

    def current_elapsed_s(self) -> float:
        """Survival time so far; frozen once the pet has run away."""
        if self.death is not None:
            return self.death.seconds_survived
        return max(0.0, self.clock() - self.started_at)

    def cooldown_remaining(self, kind: ActionKind) -> float:
        action = self.actions[kind]
        return action.cooldown_remaining(self.clock(), self._cooldowns.get(kind))

    # ------------------------------------------------------------------- loop

    def advance(self, now: float | None = None) -> TickReport:
        """Move the simulation forward to ``now`` (defaults to the clock).

        Idempotent with respect to time: calling it twice with the same ``now``
        applies nothing twice, and the amount of work depends on the elapsed
        seconds rather than on the number of calls.
        """
        if now is None:
            now = self.clock()
        if self.is_over:
            return TickReport(
                elapsed_s=self.elapsed_s, game_over=True, death=self.death
            )

        delta = min(max(now - self._last_advance_at, 0.0), self.config.catch_up_cap_s)
        self._last_advance_at = now
        self.elapsed_s = now - self.started_at

        self.pet.apply_decay(delta)
        death = self._check_death(now, CAUSE_DECAY)

        events: list[Event] = []
        budget = self.config.max_events_per_advance
        while death is None and now >= self._next_event_at:
            event = self.pool.draw(self.rng)
            self.pet.decrease(event.target, event.penalty)
            self.last_event = event
            self._log(
                "event",
                f"{event.icon} {event.title} — {event.message}",
                now,
            )
            events.append(event)
            self._next_event_at += self.pool.schedule_delay(self.rng)
            if len(events) >= budget:
                # A long stall must not turn into a wall of events.
                self._next_event_at = now + self.pool.schedule_delay(self.rng)
            death = self._check_death(now, CAUSE_EVENT, event=event)

        speech: str | None = None
        if death is None and now >= self._next_speech_at:
            state = self.pet.state()
            speech = self.messages.pick(
                state,
                self.rng,
                self.pet.name,
                self.config.label(self.pet.lowest()),
            )
            self.last_speech = speech
            self._log("speech", speech, now)
            self._next_speech_at = now + self.config.speech.interval_for(state)

        return TickReport(
            elapsed_s=self.elapsed_s,
            events=tuple(events),
            speech=speech,
            game_over=death is not None,
            death=death,
        )

    def perform(self, kind: ActionKind) -> ActionResult:
        """Run a player action against the pet."""
        if self.is_over:
            return ActionResult(ok=False, message="The pet is gone. Start a new game.")
        action = self.actions[kind]
        now = self.clock()
        result = action.execute(self.pet, now, self._cooldowns.get(kind))
        if result.ok:
            self._cooldowns[kind] = now
            self._log("action", f"{action.icon} {result.message}", now)
            # An action can never kill (floors), but the mood may have changed.
            self._check_death(now, f"action:{kind.value}")
        return result

    # ---------------------------------------------------------------- helpers

    def _check_death(
        self,
        now: float,
        cause: str,
        event: Event | None = None,
    ) -> Defeat | None:
        """Freeze the game as soon as any stat touches zero."""
        if self.death is not None:
            return self.death
        for kind in self.pet.stats:
            if self.pet.get(kind) > 0.0:
                continue
            self.status = GameStatus.DEFEAT
            self.death = Defeat(
                stat=kind,
                seconds_survived=now - self.started_at,
                cause=(
                    f"{CAUSE_EVENT}:{event.id}"
                    if cause == CAUSE_EVENT and event is not None
                    else cause
                ),
                event_title=event.title if event is not None else None,
            )
            self._next_event_at = math.inf
            self._next_speech_at = math.inf
            self.last_speech = self.messages.pick(
                PetState.DEAD, self.rng, self.pet.name, self.config.label(kind)
            )
            self._log("system", self.last_speech, now)
            return self.death
        return None

    def _log(self, kind: str, text: str, at: float) -> None:
        self.log.append(LogEntry(kind=kind, text=text, at_s=at - self.started_at))


__all__ = ["CAUSE_DECAY", "CAUSE_EVENT", "Game", "LogEntry", "TickReport"]
