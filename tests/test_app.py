"""Smoke tests for the Streamlit layer.

``AppTest`` runs the real script headlessly, so these assert that the UI
renders, that the buttons are wired to the engine and that the game over screen
appears when the pet runs away.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from virtualpet.domain import ActionKind, Pet, StatKind

pytest.importorskip("streamlit")

from streamlit.testing.v1 import AppTest

APP_PATH = str(Path(__file__).resolve().parents[1] / "app.py")


@pytest.fixture
def app() -> AppTest:
    return AppTest.from_file(APP_PATH, default_timeout=20).run()


def _game(app: AppTest):
    return app.session_state["game"]


def _drain(app: AppTest, seconds: float) -> None:
    """Wipe the pet's vitals the way neglect would."""
    game = _game(app)
    for kind in StatKind:
        game.pet.decrease(kind, seconds)


class TestRendering:
    def test_renders_without_errors(self, app: AppTest) -> None:
        assert not app.exception

    def test_shows_three_stat_bars_with_their_values(self, app: AppTest) -> None:
        bars = app.get("progress")
        assert len(bars) == 3
        assert [bar.proto.text for bar in bars] == ["100 / 100"] * 3
        assert all(bar.proto.value >= 99 for bar in bars)

    def test_bar_follows_the_current_value(self, app: AppTest) -> None:
        _drain(app, 40.0)
        app.run()
        bars = app.get("progress")
        assert bars[0].proto.text == "60 / 100"
        assert bars[0].proto.value == pytest.approx(60, abs=1)

    def test_shows_the_three_actions(self, app: AppTest) -> None:
        labels = [button.label for button in app.button]
        for action in ("Feed", "Play", "Sleep"):
            assert any(action in label for label in labels)

    def test_shows_the_latest_pet_message(self, app: AppTest) -> None:
        speech = _game(app).last_speech
        assert speech
        assert any(speech in str(block.value) for block in app.info)

    def test_starts_with_a_full_pet(self, app: AppTest) -> None:
        for kind in StatKind:
            assert _game(app).pet.get(kind) == pytest.approx(100.0, abs=0.5)


class TestInteraction:
    def test_clicking_an_action_moves_the_stats(self, app: AppTest) -> None:
        _drain(app, 40.0)
        app.run()
        app.button(key="action-feed").click().run()
        assert not app.exception
        assert _game(app).pet.get(StatKind.HUNGER) == pytest.approx(95.0, abs=0.5)

    def test_clicking_play_trades_energy_for_happiness(self, app: AppTest) -> None:
        _drain(app, 40.0)
        app.run()
        app.button(key="action-play").click().run()
        game = _game(app)
        assert game.pet.get(StatKind.HAPPINESS) == pytest.approx(88.0, abs=0.5)
        assert game.pet.get(StatKind.ENERGY) == pytest.approx(50.0, abs=0.5)

    def test_action_is_disabled_right_after_being_used(self, app: AppTest) -> None:
        _drain(app, 40.0)
        app.run()
        app.button(key="action-feed").click().run()
        app.run()  # the cooldown shows up on the next repaint
        button = app.button(key="action-feed")
        assert button.disabled
        assert "s)" in button.label

    def test_a_new_pet_resets_everything(self, app: AppTest) -> None:
        _drain(app, 60.0)
        app.run()
        app.sidebar.button[0].click().run()
        assert not app.exception
        for kind in StatKind:
            assert _game(app).pet.get(kind) == pytest.approx(100.0, abs=0.5)

    def test_a_new_pet_applies_the_typed_name(self, app: AppTest) -> None:
        app.sidebar.text_input(key="pet_name").set_value("Pixel").run()
        app.sidebar.button[0].click().run()
        assert _game(app).pet.name == "Pixel"


class TestGameOver:
    def test_shows_the_survival_time_and_a_restart_button(self, app: AppTest) -> None:
        _drain(app, 100.0)
        app.run()
        errors = [str(error.value) for error in app.error]
        assert any("ran away" in message for message in errors)
        assert any("Play again" in label for label in (b.label for b in app.button))

    def test_restart_button_brings_the_pet_back(self, app: AppTest) -> None:
        _drain(app, 100.0)
        app.run()
        restart = next(b for b in app.button if "Play again" in b.label)
        restart.click().run()
        app.run()
        assert not _game(app).is_over
        assert _game(app).pet.get(StatKind.HUNGER) == pytest.approx(100.0, abs=0.5)

    def test_actions_are_disabled_after_defeat(self, app: AppTest) -> None:
        _drain(app, 100.0)
        app.run()
        for kind in ActionKind:
            assert app.button(key=f"action-{kind.value}").disabled


class TestHelpers:
    def test_format_duration(self) -> None:
        from app import format_duration

        assert format_duration(0) == "0:00"
        assert format_duration(65) == "1:05"
        assert format_duration(3725) == "1:02:05"

    def test_severity_of_uses_the_configured_thresholds(self) -> None:
        from app import severity_of
        from virtualpet.game import Game

        game = Game(seed=1, clock=lambda: 0.0)
        for value, expected in [
            (100.0, "good"),
            (50.0, "ok"),
            (20.0, "low"),
            (5.0, "critical"),
        ]:
            game.pet = Pet(game.pet.name, game.config.stats, game.config.thresholds)
            game.pet.decrease(StatKind.HUNGER, 100.0 - value)
            assert severity_of(game, StatKind.HUNGER) == expected
