"""Virtual Pet: a single-player tamagotchi built with pure Python + Streamlit.

The game rules live in :mod:`virtualpet.game` and never import Streamlit; the
UI in ``app.py`` only renders state and dispatches actions.
"""

from __future__ import annotations

from .actions import Action, ActionResult, FeedAction, PlayAction, SleepAction
from .config import DEFAULT_CONFIG, ActionTuning, Effect, GameConfig, StatTuning
from .domain import ActionKind, Defeat, GameStatus, Pet, PetState, Stat, StatKind
from .events import EVENTS, Event, EventPool
from .game import Game, LogEntry, TickReport
from .messages import MessageBank

__all__ = [
    "DEFAULT_CONFIG",
    "EVENTS",
    "Action",
    "ActionKind",
    "ActionResult",
    "ActionTuning",
    "Defeat",
    "Effect",
    "Event",
    "EventPool",
    "FeedAction",
    "Game",
    "GameConfig",
    "GameStatus",
    "LogEntry",
    "MessageBank",
    "Pet",
    "PetState",
    "PlayAction",
    "SleepAction",
    "Stat",
    "StatKind",
    "StatTuning",
    "TickReport",
]
