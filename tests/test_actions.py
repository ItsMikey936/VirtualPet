"""Action rules: gains, costs, cooldowns and the anti-death floor."""

from __future__ import annotations

import pytest

from virtualpet.actions import FeedAction, PlayAction, SleepAction, build_actions
from virtualpet.config import DEFAULT_CONFIG, ActionTuning, Effect, GameConfig
from virtualpet.domain import ActionKind, Pet, StatKind

MAX = 100.0


def make_pet() -> Pet:
    return Pet("Pixel", DEFAULT_CONFIG.stats, DEFAULT_CONFIG.thresholds)


@pytest.fixture
def feed_action() -> FeedAction:
    return FeedAction(DEFAULT_CONFIG.action(ActionKind.FEED))


@pytest.fixture
def play_action() -> PlayAction:
    return PlayAction(DEFAULT_CONFIG.action(ActionKind.PLAY))


@pytest.fixture
def sleep_action() -> SleepAction:
    return SleepAction(DEFAULT_CONFIG.action(ActionKind.SLEEP))


class TestFeed:
    def test_restores_hunger_by_the_configured_gain(self, feed_action) -> None:
        pet = make_pet()
        pet.decrease(StatKind.HUNGER, 50.0)
        result = feed_action.execute(pet, now=0.0)
        assert result.ok
        assert pet.get(StatKind.HUNGER) == pytest.approx(85.0)
        assert result.changes[0].delta == pytest.approx(35.0)

    def test_refused_when_already_full(self, feed_action) -> None:
        result = feed_action.execute(make_pet(), now=0.0)
        assert not result.ok
        assert not result.is_blocked
        assert "stuffed" in result.message


class TestPlay:
    def test_raises_happiness_and_charges_energy_and_hunger(self, play_action) -> None:
        pet = make_pet()
        pet.decrease(StatKind.HAPPINESS, 60.0)
        play_action.execute(pet, now=0.0)
        assert pet.get(StatKind.HAPPINESS) == pytest.approx(68.0)
        assert pet.get(StatKind.ENERGY) == pytest.approx(90.0)
        assert pet.get(StatKind.HUNGER) == pytest.approx(95.0)

    def test_refused_when_happiness_is_full(self, play_action) -> None:
        result = play_action.execute(make_pet(), now=0.0)
        assert not result.ok
        assert "happiness" in result.message


class TestSleep:
    def test_restores_energy_but_takes_hunger_and_happiness(self, sleep_action) -> None:
        pet = make_pet()
        pet.decrease(StatKind.ENERGY, 50.0)
        sleep_action.execute(pet, now=0.0)
        assert pet.get(StatKind.ENERGY) == pytest.approx(90.0)
        assert pet.get(StatKind.HUNGER) == pytest.approx(94.0)
        assert pet.get(StatKind.HAPPINESS) == pytest.approx(98.0)

    def test_refused_when_energy_is_full(self, sleep_action) -> None:
        result = sleep_action.execute(make_pet(), now=0.0)
        assert not result.ok
        assert "awake" in result.message


class TestCooldowns:
    def test_second_use_inside_the_window_is_blocked(self, feed_action) -> None:
        pet = make_pet()
        pet.decrease(StatKind.HUNGER, 50.0)
        assert feed_action.execute(pet, now=0.0).ok
        pet.decrease(StatKind.HUNGER, 50.0)
        blocked = feed_action.execute(pet, now=0.5, last_used_at=0.0)
        assert not blocked.ok
        assert blocked.is_blocked
        assert blocked.blocked_for_s == pytest.approx(1.5)

    def test_allowed_again_once_the_cooldown_expires(self, feed_action) -> None:
        pet = make_pet()
        pet.decrease(StatKind.HUNGER, 50.0)
        feed_action.execute(pet, now=0.0, last_used_at=None)
        pet.decrease(StatKind.HUNGER, 50.0)
        cooldown = feed_action.cooldown_s
        assert feed_action.execute(pet, now=cooldown + 0.01, last_used_at=0.0).ok

    def test_cooldown_remaining_counts_down(self, feed_action) -> None:
        assert feed_action.cooldown_remaining(now=10.0, last_used_at=None) == 0.0
        remaining = feed_action.cooldown_remaining(now=10.0, last_used_at=9.0)
        assert remaining == pytest.approx(feed_action.cooldown_s - 1.0)
        assert feed_action.cooldown_remaining(
            now=99.0, last_used_at=0.0
        ) == pytest.approx(0.0)


class TestAntiDeathFloor:
    @pytest.mark.parametrize("kind", list(ActionKind))
    def test_no_action_can_push_a_stat_to_zero(self, kind: ActionKind) -> None:
        actions = build_actions(DEFAULT_CONFIG)
        pet = make_pet()
        for stat in pet.stats.values():
            stat.value = 3.0
        actions[kind].execute(pet, now=0.0)
        for stat in pet.stats.values():
            assert stat.value >= DEFAULT_CONFIG.action_floor

    def test_spamming_play_forever_never_kills_the_pet(self, play_action) -> None:
        pet = make_pet()
        for _ in range(500):
            for stat in pet.stats.values():
                stat.value = 4.0
            play_action.execute(pet, now=0.0)
        assert not pet.is_dead


class TestBuildActions:
    def test_one_action_per_kind_with_expected_types(self) -> None:
        actions = build_actions(DEFAULT_CONFIG)
        assert set(actions) == set(ActionKind)
        assert isinstance(actions[ActionKind.FEED], FeedAction)
        assert isinstance(actions[ActionKind.PLAY], PlayAction)
        assert isinstance(actions[ActionKind.SLEEP], SleepAction)

    def test_custom_config_is_respected(self) -> None:
        tuning = ActionTuning(
            kind=ActionKind.FEED,
            label="Feed",
            icon="🍖",
            message="Yum!",
            effects=(Effect(StatKind.HUNGER, 99.0),),
            cooldown_s=0.0,
        )
        config: GameConfig = DEFAULT_CONFIG.with_overrides(
            actions={ActionKind.FEED: tuning}
        )
        pet = Pet("Pixel", config.stats, config.thresholds)
        pet.decrease(StatKind.HUNGER, 50.0)
        build_actions(config)[ActionKind.FEED].execute(pet, now=0.0)
        assert pet.get(StatKind.HUNGER) == pytest.approx(MAX)
