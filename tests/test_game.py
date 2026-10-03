"""Engine behaviour: clock, decay, events, dialogue, defeat and restart."""

from __future__ import annotations

import pytest

from virtualpet.config import DEFAULT_CONFIG, EventTuning, GameConfig, SpeechTuning
from virtualpet.domain import ActionKind, GameStatus, PetState, StatKind
from virtualpet.game import CAUSE_DECAY, Game

MAX = 100.0
MAX_VALUE = DEFAULT_CONFIG.stat(StatKind.HUNGER).maximum
SILENT = SpeechTuning(
    intervals_s={
        PetState.THRIVING: 10_000.0,
        PetState.OK: 10_000.0,
        PetState.LOW: 10_000.0,
        PetState.CRITICAL: 10_000.0,
        PetState.DEAD: 0.0,
    }
)
NO_EVENTS = EventTuning(
    mean_interval_s=1_000.0, min_interval_s=1_000.0, max_interval_s=1_000.0
)
RARE_EVENTS = EventTuning(
    mean_interval_s=60.0, min_interval_s=10.0, max_interval_s=150.0
)


def run_for(game: Game, clock, seconds: float, step: float = 1.0) -> None:
    """Advance the simulation in fixed steps, like the Streamlit fragment."""
    elapsed = 0.0
    while elapsed < seconds:
        clock.advance(step)
        game.advance()
        elapsed += step


@pytest.fixture
def game(clock) -> Game:
    return Game(seed=42, clock=clock)


class TestSetup:
    def test_starts_playing_with_full_stats(self, game: Game) -> None:
        assert game.status is GameStatus.PLAYING
        assert not game.is_over
        for kind in StatKind:
            assert game.pet.get(kind) == MAX_VALUE
        assert game.pet.state() is PetState.THRIVING

    def test_greets_the_player_on_creation(self, game: Game) -> None:
        assert game.last_speech
        assert game.pet.name in game.last_speech
        assert game.log[0].kind == "speech"

    def test_same_seed_gives_the_same_run(self, clock) -> None:
        first, second = Game(seed=99, clock=clock), Game(seed=99, clock=clock)
        clock.advance(240.0)
        first.advance()
        second.advance()
        assert [e.kind for e in first.log] == [e.kind for e in second.log]


class TestClock:
    def test_advance_is_idempotent_for_the_same_timestamp(self, game, clock) -> None:
        clock.advance(10.0)
        game.advance(now=clock())
        hunger_after_first = game.pet.get(StatKind.HUNGER)
        for _ in range(5):
            game.advance(now=clock())
        assert game.pet.get(StatKind.HUNGER) == pytest.approx(hunger_after_first)

    def test_decay_matches_the_elapsed_seconds(self, game, clock) -> None:
        tuning = DEFAULT_CONFIG.stat(StatKind.HUNGER)
        clock.advance(60.0)
        game.advance()
        assert game.pet.get(StatKind.HUNGER) <= MAX_VALUE - tuning.decay_per_minute

    def test_stepping_matches_one_big_jump(self, clock) -> None:
        """Same elapsed time must produce the same state, however it is chunked.

        Dialogue is silenced because :meth:`MessageBank.pick` consumes random
        numbers: how many times the pet chats shifts the RNG stream, and with it
        the events. Only the *timing* must be chunk-independent.
        """
        config: GameConfig = DEFAULT_CONFIG.with_overrides(speech=SILENT)
        stepped = Game(config=config, seed=5, clock=clock)
        for _ in range(120):
            clock.advance(1.0)
            stepped.advance()
        clock2 = type(clock)()
        jumpy = Game(config=config, seed=5, clock=clock2)
        clock2.advance(120.0)
        jumpy.advance()
        for kind in StatKind:
            assert stepped.pet.get(kind) == pytest.approx(jumpy.pet.get(kind))

    def test_long_stalls_are_capped(self, clock) -> None:
        """A tab left open overnight must not be punished as if it were play."""
        config: GameConfig = DEFAULT_CONFIG.with_overrides(
            events=NO_EVENTS, speech=SILENT
        )
        game = Game(config=config, clock=clock)
        before = game.pet.get(StatKind.ENERGY)
        clock.advance(DEFAULT_CONFIG.catch_up_cap_s + 600.0)
        game.advance()
        drained = before - game.pet.get(StatKind.ENERGY)
        expected = DEFAULT_CONFIG.stat(StatKind.ENERGY).decay_per_second * (
            DEFAULT_CONFIG.catch_up_cap_s
        )
        assert drained == pytest.approx(expected, rel=1e-6)
        assert not game.is_over

    def test_events_follow_the_clock_not_the_rerun_count(self, clock) -> None:
        """Ten updates per second must equal a single update after ten seconds."""
        config: GameConfig = DEFAULT_CONFIG.with_overrides(speech=SILENT)
        fast = Game(config=config, seed=3, clock=clock)
        for _ in range(600):
            clock.advance(0.1)
            fast.advance()
        clock2 = type(clock)()
        slow = Game(config=config, seed=3, clock=clock2)
        clock2.advance(60.0)
        slow.advance()
        assert fast.elapsed_s == pytest.approx(60.0)
        assert fast.death is None and slow.death is None
        for kind in StatKind:
            assert fast.pet.get(kind) == pytest.approx(slow.pet.get(kind), abs=0.01)


class TestActions:
    def test_feed_restores_hunger(self, game) -> None:
        game.pet.decrease(StatKind.HUNGER, 40.0)
        result = game.perform(ActionKind.FEED)
        assert result.ok
        assert game.pet.get(StatKind.HUNGER) == pytest.approx(95.0)

    def test_cooldown_blocks_immediate_repeats(self, game, clock) -> None:
        game.pet.decrease(StatKind.HUNGER, 40.0)
        assert game.perform(ActionKind.FEED).ok
        game.pet.decrease(StatKind.HUNGER, 40.0)
        blocked = game.perform(ActionKind.FEED)
        assert blocked.is_blocked
        assert game.cooldown_remaining(ActionKind.FEED) > 0.0
        clock.advance(DEFAULT_CONFIG.action(ActionKind.FEED).cooldown_s + 0.1)
        assert game.perform(ActionKind.FEED).ok

    def test_no_combination_of_actions_can_kill_the_pet(self, game) -> None:
        """Hammer every action forever: the pet must never run away."""
        for _ in range(2000):
            for kind in StatKind:
                game.pet.decrease(kind, 6.0)
            for action in ActionKind:
                game.perform(action)
        assert not game.is_over

    def test_actions_are_logged(self, game) -> None:
        game.pet.decrease(StatKind.HUNGER, 40.0)
        game.perform(ActionKind.FEED)
        assert game.log[-1].kind == "action"

    def test_actions_are_refused_after_defeat(self, game) -> None:
        game.pet.decrease(StatKind.HUNGER, MAX_VALUE)
        game.advance()
        result = game.perform(ActionKind.FEED)
        assert not result.ok
        assert "gone" in result.message


class TestEvents:
    def test_events_fire_and_reduce_the_targeted_stat(self, game, clock) -> None:
        fired = []
        for _ in range(400):
            clock.advance(1.0)
            fired.extend(game.advance().events)
        assert fired
        for event in fired:
            assert event.penalty > 0.0
        assert any(e.kind == "event" for e in game.log)

    def test_event_frequency_tracks_the_configured_mean(self, game, clock) -> None:
        count = 0
        for _ in range(600):
            clock.advance(1.0)
            count += len(game.advance().events)
        expected = 600.0 / DEFAULT_CONFIG.events.mean_interval_s
        assert 0.4 * expected <= count <= 2.0 * expected

    def test_last_event_is_exposed_for_the_ui(self, game, clock) -> None:
        assert game.last_event is None
        for _ in range(400):
            clock.advance(1.0)
            game.advance()
            if game.last_event is not None:
                break
        assert game.last_event is not None

    def test_a_stall_cannot_flood_the_log(self, clock) -> None:
        game = Game(seed=8, clock=clock)
        clock.advance(DEFAULT_CONFIG.catch_up_cap_s + 1000.0)
        report = game.advance()
        assert len(report.events) <= DEFAULT_CONFIG.max_events_per_advance


class TestDialogue:
    def test_pet_talks_on_the_configured_cadence(self, game, clock) -> None:
        interval = DEFAULT_CONFIG.speech.interval_for(PetState.THRIVING)
        quiet = [game.advance(now=clock()).speech for _ in range(int(interval))]
        assert all(line is None for line in quiet[: int(interval) - 1])
        clock.advance(interval)
        assert game.advance().speech

    def test_critical_mood_speaks_often_and_names_the_stat(self, game, clock) -> None:
        game.pet.decrease(StatKind.ENERGY, MAX_VALUE - 10.0)
        clock.advance(50.0)
        report = game.advance()
        assert game.pet.state() is PetState.CRITICAL
        assert not game.is_over
        assert report.speech is not None
        assert "{" not in report.speech

    def test_speech_never_contains_placeholders(self, game, clock) -> None:
        for _ in range(300):
            clock.advance(2.0)
            game.advance()
            assert "{" not in game.last_speech


class TestDefeat:
    def test_neglect_ends_the_game_with_the_failing_stat(self, game, clock) -> None:
        run_for(game, clock, 900.0)
        assert game.is_over
        assert game.status is GameStatus.DEFEAT
        assert game.death is not None
        assert game.death.stat in StatKind
        assert game.death.seconds_survived > 0.0
        assert game.pet.get(game.death.stat) == 0.0

    def test_survival_time_freezes_after_defeat(self, game, clock) -> None:
        run_for(game, clock, 900.0)
        frozen = game.current_elapsed_s()
        clock.advance(300.0)
        game.advance()
        assert game.current_elapsed_s() == pytest.approx(frozen)

    def test_advance_is_a_no_op_after_defeat(self, game, clock) -> None:
        run_for(game, clock, 900.0)
        snapshot = tuple(game.pet.stats[kind].value for kind in StatKind)
        report = game.advance()
        assert report.game_over
        assert tuple(game.pet.stats[kind].value for kind in StatKind) == snapshot

    def test_surviving_for_an_hour_is_possible(self, clock) -> None:
        """A player who reacts should comfortably outlive a careless one."""
        config: GameConfig = DEFAULT_CONFIG.with_overrides(events=RARE_EVENTS)
        game = Game(config=config, seed=11, clock=clock)
        for _ in range(3600):
            clock.advance(1.0)
            game.advance()
            worst = game.pet.lowest()
            if game.pet.ratio(worst) < 0.5:
                action = {
                    StatKind.HUNGER: ActionKind.FEED,
                    StatKind.ENERGY: ActionKind.SLEEP,
                    StatKind.HAPPINESS: ActionKind.PLAY,
                }[worst]
                game.perform(action)
        assert not game.is_over
        assert game.current_elapsed_s() == pytest.approx(3600.0)

    def test_neglect_survives_several_minutes_first(self, game, clock) -> None:
        run_for(game, clock, 180.0)
        assert not game.is_over


class TestRestart:
    def test_restart_resets_stats_clock_and_log(self, game, clock) -> None:
        run_for(game, clock, 400.0)
        game.restart()
        assert not game.is_over
        for kind in StatKind:
            assert game.pet.get(kind) == MAX_VALUE
        assert game.current_elapsed_s() < 1.0
        assert game.death is None
        assert game.last_event is None
        assert all(e.kind in {"speech", "system"} for e in game.log)

    def test_restart_can_reseed(self, game) -> None:
        game.restart(seed=123)
        assert game.seed == 123
        assert game.last_speech

    def test_playable_again_after_restart(self, game, clock) -> None:
        run_for(game, clock, 900.0)
        game.restart()
        game.pet.decrease(StatKind.HUNGER, 40.0)
        assert game.perform(ActionKind.FEED).ok
        clock.advance(2.0)
        assert not game.advance().game_over


class TestPacing:
    def test_decay_alone_empties_a_stat_in_a_reasonable_window(self, clock) -> None:
        game = Game(seed=1, clock=clock)
        minutes = MAX_VALUE / DEFAULT_CONFIG.stat(StatKind.HUNGER).decay_per_minute
        game.pet.apply_decay(minutes * 60.0)
        assert game.pet.get(StatKind.HUNGER) == pytest.approx(0.0)
        assert 2.0 < minutes < 12.0

    def test_decay_cause_is_recorded_when_no_event_kills(self, clock) -> None:
        game = Game(config=DEFAULT_CONFIG.with_overrides(events=NO_EVENTS), clock=clock)
        for _ in range(1200):
            clock.advance(1.0)
            game.advance()
            if game.is_over:
                break
        assert game.death is not None
        assert game.death.cause == CAUSE_DECAY
        assert game.death.event_title is None
