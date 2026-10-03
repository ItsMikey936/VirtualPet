"""Dialogue banks: coverage, non-repetition and safe rendering."""

from __future__ import annotations

import random

import pytest

from virtualpet.domain import PetState
from virtualpet.messages import DIALOGUE, GREETINGS, MessageBank
from virtualpet.text import render

MOODS = [PetState.THRIVING, PetState.OK, PetState.LOW, PetState.CRITICAL]


class TestDialogueContent:
    @pytest.mark.parametrize("state", MOODS)
    def test_every_mood_has_several_lines(self, state: PetState) -> None:
        assert len(DIALOGUE[state]) >= 6

    def test_dead_mood_has_lines_too(self) -> None:
        assert len(DIALOGUE[PetState.DEAD]) >= 3

    def test_lines_are_unique_per_mood(self) -> None:
        for state, lines in DIALOGUE.items():
            assert len(set(lines)) == len(lines), state

    def test_low_and_critical_lines_name_the_stat(self) -> None:
        for state in (PetState.LOW, PetState.CRITICAL):
            assert all("{stat}" in line for line in DIALOGUE[state])

    def test_greetings_exist(self) -> None:
        assert len(GREETINGS) >= 3
        assert all("{name}" in line for line in GREETINGS)


class TestMessageBank:
    def test_rendered_line_has_no_placeholders_left(self) -> None:
        bank = MessageBank()
        rng = random.Random(11)
        for state in [*MOODS, PetState.DEAD]:
            for _ in range(10):
                line = bank.pick(state, rng, "Nimbus", "Energy")
                assert "{" not in line and "}" not in line

    def test_low_mood_mentions_the_stat_it_cares_about(self) -> None:
        bank = MessageBank()
        rng = random.Random(12)
        for _ in range(20):
            line = bank.pick(PetState.LOW, rng, "Nimbus", "Hunger")
            assert "Hunger" in line or "{stat}" not in line

    def test_no_immediate_repeats_until_the_bank_is_drained(self) -> None:
        bank = MessageBank()
        rng = random.Random(13)
        for state in MOODS:
            lines = list(DIALOGUE[state])
            drawn = [
                bank.pick(state, rng, "Nimbus", "Energy") for _ in range(len(lines))
            ]
            assert len(set(drawn)) == len(lines)

    def test_cycle_reshuffles_after_the_bank_is_drained(self) -> None:
        bank = MessageBank()
        rng = random.Random(14)
        size = len(DIALOGUE[PetState.CRITICAL])
        first = [bank.pick(PetState.CRITICAL, rng) for _ in range(size)]
        second = [bank.pick(PetState.CRITICAL, rng) for _ in range(size)]
        assert len(set(first)) == size
        assert set(first) == set(second)

    def test_greeting_includes_the_pet_name(self) -> None:
        bank = MessageBank()
        assert "Nimbus" in bank.greeting(random.Random(15), "Nimbus")

    def test_bank_without_lines_for_a_mood_is_safe(self) -> None:
        bank = MessageBank({PetState.THRIVING: ("hi",)})
        assert bank.pick(PetState.OK, random.Random(17)) == ""


class TestRender:
    def test_replaces_every_occurrence(self) -> None:
        assert render("{a}-{a}", a="x") == "x-x"

    def test_ignores_unknown_placeholders(self) -> None:
        assert render("{a}{b}", a="x") == "x{b}"

    def test_is_not_confused_by_format_syntax_in_values(self) -> None:
        assert render("{a}", a="{0}") == "{0}"
        assert render("{a}", a="{a}") == "{a}"
