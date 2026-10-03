"""Streamlit front-end for Virtual Pet.

This module contains **no game rules**: it renders whatever
:class:`virtualpet.game.Game` holds and forwards player clicks to it. The state
lives in ``st.session_state`` and a single fragment repaints itself once per
second, so the app never blocks and the clock keeps ticking without a rerun.
"""

from __future__ import annotations

import html
import time

import streamlit as st

from virtualpet.config import DEFAULT_CONFIG
from virtualpet.domain import ActionKind, GameStatus, PetState, StatKind
from virtualpet.game import Game

TICK_SECONDS = DEFAULT_CONFIG.tick_s
FLASH_LIFETIME_S = 4.0

MOOD_FACES: dict[PetState, tuple[str, str]] = {
    PetState.THRIVING: ("😄", "Thriving"),
    PetState.OK: ("🙂", "Doing fine"),
    PetState.LOW: ("😟", "Needs you"),
    PetState.CRITICAL: ("😫", "Critical!"),
    PetState.DEAD: ("💀", "Gone"),
}

BADGE_COLOURS: dict[str, str] = {
    "good": "#1f9d55",
    "ok": "#4a90d9",
    "low": "#e6a23c",
    "critical": "#d64545",
}

STYLES = """
<style>
.pet-face { font-size: 5rem; line-height: 1; text-align: center; margin: 0; }
.pet-meta { text-align: center; font-size: 0.95rem; opacity: 0.75; margin-top: .2rem;}
.badge {
    display: inline-block; padding: 1px 8px; border-radius: 999px;
    font-size: 0.72rem; font-weight: 700; color: #fff; margin-left: 6px;
}
.divider-note { font-size: 0.75rem; opacity: 0.6; }
</style>
"""


def format_duration(seconds: float) -> str:
    """Render a survival time as ``m:ss`` (or ``h:mm:ss`` past an hour)."""
    total = int(max(0.0, seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def severity_of(game: Game, kind: StatKind) -> str:
    """Bucket a single stat for colouring, worst-first."""
    thresholds = game.config.thresholds
    value = game.pet.get(kind)
    if value <= thresholds.critical:
        return "critical"
    if value < thresholds.low:
        return "low"
    if value >= thresholds.thrive:
        return "good"
    return "ok"


def badge(text: str, colour: str) -> str:
    return (
        f'<span class="badge" style="background:{BADGE_COLOURS[colour]}">{text}</span>'
    )


def get_game() -> Game:
    """Fetch (or create) the game kept in the session state."""
    if "game" not in st.session_state:
        st.session_state.game = Game(seed=st.session_state.get("seed") or None)
    return st.session_state.game


def set_flash(text: str) -> None:
    st.session_state["flash"] = (text, time.monotonic())


def read_flash() -> str | None:
    """Return the last action feedback, but only while it is still fresh."""
    entry = st.session_state.get("flash")
    if not entry:
        return None
    text, stamp = entry
    if time.monotonic() - stamp > FLASH_LIFETIME_S:
        return None
    return text


def render_header(game: Game) -> None:
    state = game.pet.state()
    face, mood = MOOD_FACES[state]
    st.markdown(f'<p class="pet-face">{face}</p>', unsafe_allow_html=True)
    st.markdown(
        f'<p class="pet-meta">'
        f"<strong>{html.escape(game.pet.name)}</strong> · {mood} · "
        f"alive for {format_duration(game.current_elapsed_s())}"
        "</p>",
        unsafe_allow_html=True,
    )


def render_stats(game: Game) -> None:
    columns = st.columns(3)
    for column, kind in zip(columns, StatKind, strict=True):
        tuning = game.config.stat(kind)
        value = game.pet.get(kind)
        severity = severity_of(game, kind)
        with column:
            st.markdown(f"### {tuning.icon} {tuning.label}")
            st.progress(
                value / tuning.maximum if tuning.maximum else 0.0,
                text=f"{value:.0f} / {tuning.maximum:.0f}",
            )
            st.markdown(badge(severity.upper(), severity), unsafe_allow_html=True)


def render_actions(game: Game) -> None:
    columns = st.columns(3)
    for column, kind in zip(columns, ActionKind, strict=True):
        action = game.actions[kind]
        remaining = game.cooldown_remaining(kind)
        label = f"{action.icon} {action.label}"
        if remaining > 0.05:
            label = f"{label} ({remaining:.0f}s)"
        with column:
            if st.button(
                label,
                key=f"action-{kind.value}",
                disabled=game.is_over or remaining > 0.05,
                use_container_width=True,
            ):
                result = game.perform(kind)
                if result.ok:
                    deltas = ", ".join(
                        f"{game.config.icon(change.kind)} {change.delta:+.0f}"
                        for change in result.changes
                    )
                    set_flash(f"{deltas}  ·  {result.message}")
                else:
                    set_flash(result.message)


def render_dialogue(game: Game, just_spoke: bool) -> None:
    st.markdown("#### 💬 The pet says")
    if just_spoke:
        st.success(f"**{game.last_speech}**")
    else:
        st.info(game.last_speech or "...")
    if game.last_event is not None:
        event = game.last_event
        st.warning(
            f"{event.icon} **{event.title}** — {event.message} "
            f"(-{event.penalty:.0f} {game.config.label(event.target)})"
        )


def render_log(game: Game) -> None:
    with st.expander("History"):
        if not game.log:
            st.caption("Nothing has happened yet.")
        for entry in reversed(game.log):
            prefix = format_duration(entry.at_s)
            st.markdown(f"`{prefix}` {entry.text}")


def render_game_over(game: Game) -> None:
    death = game.death
    if death is None:  # pragma: no cover - defensive
        return
    st.markdown("---")
    st.error(
        f"💀 **{game.pet.name} ran away.** "
        f"{game.config.label(death.stat)} hit zero "
        f"after **{format_duration(death.seconds_survived)}**."
    )
    cause = (
        f"Caused by: {death.event_title}."
        if death.event_title
        else "Caused by plain neglect: the bars were left to drain."
    )
    st.caption(cause)
    if st.button("🔄 Play again", type="primary", use_container_width=True):
        st.session_state.pop("flash", None)
        game.restart()
        set_flash(f"{game.pet.name} is back. Do not let it hit zero!")


@st.fragment(run_every=TICK_SECONDS)
def live(game: Game) -> None:
    """Everything that repaints on its own, once per tick."""
    report = game.advance()
    render_header(game)

    flash = read_flash()
    if flash:
        st.caption(flash)

    render_stats(game)
    render_actions(game)
    render_dialogue(game, report.speech is not None)
    if game.is_over:
        render_game_over(game)
    else:
        st.markdown(
            "<p class='divider-note'>Keep every bar above zero. "
            "Random events will not wait for you.</p>",
            unsafe_allow_html=True,
        )
    render_log(game)


def render_sidebar(game: Game) -> None:
    with st.sidebar:
        st.header("⚙️ Settings")
        name = st.text_input(
            "Pet name",
            value=game.pet.name,
            key="pet_name",
            help="Applied when you start a new pet.",
        )
        seed = st.number_input(
            "Random seed",
            min_value=0,
            max_value=999_999,
            value=0,
            step=1,
            help="0 means a fresh random run. Same seed, same events.",
        )
        if st.button("🎲 New pet", use_container_width=True):
            st.session_state.pop("flash", None)
            game.name = name.strip() or DEFAULT_CONFIG.name
            game.restart(seed=seed or None)
            set_flash(f"{game.pet.name} is ready. Good luck!")
        st.divider()
        st.caption(
            "Status: "
            + (
                GameStatus.DEFEAT.value.capitalize()
                if game.is_over
                else GameStatus.PLAYING.value.capitalize()
            )
        )
        st.caption(f"Survived: {format_duration(game.current_elapsed_s())}")


def main() -> None:
    st.set_page_config(
        page_title="Virtual Pet",
        page_icon="🐾",
        layout="centered",
    )
    st.markdown(STYLES, unsafe_allow_html=True)
    game = get_game()
    render_sidebar(game)
    st.title("🐾 Virtual Pet")
    st.caption("Keep the pet fed, rested and happy. Let a bar hit zero and it leaves.")
    live(game)


if __name__ == "__main__":
    main()
