"""Placeholder rendering for pet dialogue.

The pet name comes from the player, so ``str.format`` is deliberately avoided:
a pet called ``"{0}"`` would raise ``IndexError``. Plain ``str.replace`` is
predictable and injection-proof.
"""

from __future__ import annotations


def render(template: str, **values: str) -> str:
    """Replace every ``{key}`` placeholder in ``template`` with ``values[key]``."""
    for key, value in values.items():
        template = template.replace("{" + key + "}", value)
    return template
