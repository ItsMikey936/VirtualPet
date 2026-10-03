"""Rules for a single vital and for the pet as a whole."""

from __future__ import annotations

from dataclasses import replace

import pytest

from virtualpet.config import DEFAULT_CONFIG, Thresholds
from virtualpet.domain import Pet, PetState, Stat, StatKind

MAX = 100.0


def make_pet(name: str = "Pixel", thresholds: Thresholds | None = None) -> Pet:
    return Pet(
        name,
        DEFAULT_CONFIG.stats,
        thresholds or DEFAULT_CONFIG.thresholds,
    )


class TestStat:
    def test_starts_at_configured_value(self) -> None:
        assert Stat(StatKind.HUNGER, 100.0, MAX).value == MAX

    def test_clamps_above_maximum(self) -> None:
        assert Stat(StatKind.HUNGER, 180.0, MAX).value == MAX

    def test_clamps_below_zero(self) -> None:
        assert Stat(StatKind.HUNGER, -40.0, MAX).value == 0.0

    def test_increase_is_saturating(self) -> None:
        stat = Stat(StatKind.HUNGER, 80.0, MAX)
        assert stat.increase(50.0) == pytest.approx(20.0)
        assert stat.value == MAX

    def test_decrease_is_saturating_at_zero(self) -> None:
        stat = Stat(StatKind.HUNGER, 5.0, MAX)
        assert stat.decrease(500.0) == pytest.approx(-5.0)
        assert stat.value == 0.0

    def test_decrease_respects_a_floor(self) -> None:
        stat = Stat(StatKind.HUNGER, 4.0, MAX)
        stat.decrease(100.0, floor=1.0)
        assert stat.value == pytest.approx(1.0)

    def test_ratio_and_is_empty(self) -> None:
        stat = Stat(StatKind.HUNGER, 25.0, MAX)
        assert stat.ratio == pytest.approx(0.25)
        assert not stat.is_empty
        stat.value = 0.0
        assert stat.is_empty

    def test_never_exceeds_bounds_under_repeated_churn(self) -> None:
        stat = Stat(StatKind.ENERGY, 50.0, MAX)
        for _ in range(200):
            stat.increase(35.0)
            stat.decrease(80.0)
        assert 0.0 <= stat.value <= MAX


class TestPet:
    def test_all_stats_start_at_full(self) -> None:
        pet = make_pet()
        for kind in StatKind:
            assert pet.get(kind) == MAX
        assert pet.state() is PetState.THRIVING

    def test_decay_is_proportional_to_elapsed_time(self) -> None:
        pet = make_pet()
        tuning = DEFAULT_CONFIG.stat(StatKind.HUNGER)
        pet.apply_decay(60.0)
        assert pet.get(StatKind.HUNGER) == pytest.approx(MAX - tuning.decay_per_minute)
        pet.apply_decay(30.0)
        assert pet.get(StatKind.HUNGER) == pytest.approx(
            MAX - tuning.decay_per_minute * 1.5
        )

    def test_decay_ignores_negative_or_zero_delta(self) -> None:
        pet = make_pet()
        pet.apply_decay(0.0)
        pet.apply_decay(-10.0)
        assert pet.get(StatKind.HUNGER) == MAX

    def test_lowest_reports_the_worst_stat(self) -> None:
        pet = make_pet()
        pet.increase(StatKind.HUNGER, -30.0)
        pet.increase(StatKind.ENERGY, -70.0)
        assert pet.lowest() is StatKind.ENERGY
        assert pet.lowest_value() == pytest.approx(30.0)

    @pytest.mark.parametrize(
        ("hunger", "expected"),
        [
            (100.0, PetState.THRIVING),
            (70.0, PetState.THRIVING),
            (69.9, PetState.OK),
            (30.0, PetState.OK),
            (29.9, PetState.LOW),
            (12.1, PetState.LOW),
            (12.0, PetState.CRITICAL),
            (0.0, PetState.DEAD),
        ],
    )
    def test_state_transitions(self, hunger: float, expected: PetState) -> None:
        pet = make_pet()
        pet.decrease(StatKind.HUNGER, MAX - hunger)
        assert pet.state() is expected

    def test_dead_when_any_stat_hits_zero(self) -> None:
        pet = make_pet()
        pet.decrease(StatKind.HAPPINESS, MAX)
        assert pet.is_dead
        assert pet.state() is PetState.DEAD

    def test_custom_thresholds_are_honoured(self) -> None:
        thresholds = replace(DEFAULT_CONFIG.thresholds, low=80.0, critical=50.0)
        pet = make_pet(thresholds=thresholds)
        pet.decrease(StatKind.HUNGER, 25.0)
        assert pet.state() is PetState.LOW
