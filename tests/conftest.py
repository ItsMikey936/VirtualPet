"""Shared pytest fixtures and helpers."""

from __future__ import annotations

import pytest

from virtualpet.config import DEFAULT_CONFIG, GameConfig


class FakeClock:
    """A clock the test moves by hand, so the engine stays deterministic."""

    def __init__(self, now: float = 1000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def config() -> GameConfig:
    return DEFAULT_CONFIG
