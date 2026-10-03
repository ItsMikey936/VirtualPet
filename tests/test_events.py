"""The random event table and its timing law."""

from __future__ import annotations

import random

import pytest

from virtualpet.config import DEFAULT_CONFIG, EventTuning
from virtualpet.domain import StatKind
from virtualpet.events import EVENTS, EventPool


class TestEventTable:
    def test_has_at_least_six_events(self) -> None:
        assert len(EVENTS) >= 6

    def test_covers_every_stat_with_at_least_two_events(self) -> None:
        for kind in StatKind:
            assert sum(1 for e in EVENTS if e.target is kind) >= 2

    def test_every_event_is_complete(self) -> None:
        for event in EVENTS:
            assert event.id.strip()
            assert event.title.strip()
            assert event.message.strip()
            assert event.icon.strip()
            assert event.penalty > 0.0
            assert event.weight > 0.0

    def test_ids_are_unique(self) -> None:
        ids = [event.id for event in EVENTS]
        assert len(ids) == len(set(ids))


class TestEventPool:
    def test_draw_always_returns_a_known_event(self) -> None:
        pool = EventPool(DEFAULT_CONFIG)
        rng = random.Random(1)
        for _ in range(500):
            assert pool.draw(rng) in EVENTS

    def test_schedule_delay_respects_bounds(self) -> None:
        pool = EventPool(DEFAULT_CONFIG)
        rng = random.Random(2)
        tuning = DEFAULT_CONFIG.events
        for _ in range(1000):
            delay = pool.schedule_delay(rng)
            assert tuning.min_interval_s <= delay <= tuning.max_interval_s

    def test_delays_average_close_to_the_configured_mean(self) -> None:
        pool = EventPool(DEFAULT_CONFIG)
        rng = random.Random(3)
        samples = [pool.schedule_delay(rng) for _ in range(4000)]
        expected = DEFAULT_CONFIG.events.mean_interval_s
        assert sum(samples) / len(samples) == pytest.approx(expected, rel=0.1)

    def test_heavier_events_show_up_more_often(self) -> None:
        pool = EventPool(DEFAULT_CONFIG)
        rng = random.Random(4)
        counts = {event.id: 0 for event in EVENTS}
        for _ in range(4000):
            counts[pool.draw(rng).id] += 1
        # The two heaviest by weight are empty_afternoon (1.2) and ignored (1.1).
        assert counts["bored_afternoon"] > counts["mirror_rivalry"]
        assert counts["ignored"] > counts["zoomies"]

    def test_is_reproducible_for_a_given_seed(self) -> None:
        pool = EventPool(DEFAULT_CONFIG)
        first = [pool.draw(random.Random(9)) for _ in range(20)]
        second = [pool.draw(random.Random(9)) for _ in range(20)]
        assert [event.id for event in first] == [event.id for event in second]

    def test_custom_tuning_changes_the_delay(self) -> None:
        pool = EventPool(
            DEFAULT_CONFIG.with_overrides(
                events=EventTuning(
                    mean_interval_s=4.0, min_interval_s=0.1, max_interval_s=1.0
                )
            )
        )
        rng = random.Random(5)
        assert all(pool.schedule_delay(rng) <= 1.0 for _ in range(200))
