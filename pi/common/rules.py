"""Rule evaluation with edge triggering and a re-alert cooldown.

Two behaviours matter here and both are deliberate.

Edge triggering: a rule buzzes when it *enters* violation, not on every sample
while it stays violated. Without this, a dry pot buzzes every two seconds
forever, which is useless and annoying.

Cooldown: a rule that stays violated re-alerts once per cooldown period, so a
condition you have not fixed still reminds you. Without it, a plant left dry
overnight would go silent after the first buzz.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .config import Reading, Rule

DEFAULT_COOLDOWN_S = 30 * 60   # 30 minutes


@dataclass
class RuleState:
    """What we remember about one rule between samples."""

    violated: bool = False
    last_alert: float | None = None


@dataclass
class RuleEngine:
    rules: list[Rule]
    cooldown_s: float = DEFAULT_COOLDOWN_S
    _state: dict[int, RuleState] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._state = {rule.number: RuleState() for rule in self.rules}

    def evaluate(self, reading: Reading, now: float | None = None) -> list[Rule]:
        """Return the rules that should buzz for this reading.

        A rule is returned when it has just entered violation, or when it is
        still violated and the cooldown has expired.
        """
        now = time.monotonic() if now is None else now
        to_alert: list[Rule] = []

        for rule in self.rules:
            state = self._state[rule.number]
            violated = rule.violated_by(reading)

            if violated and not state.violated:
                # Entering violation: always alert.
                to_alert.append(rule)
                state.last_alert = now
            elif violated and state.violated:
                # Still violated: re-alert only after the cooldown.
                if state.last_alert is None or now - state.last_alert >= self.cooldown_s:
                    to_alert.append(rule)
                    state.last_alert = now
            # Leaving violation is silent. Clearing a condition should not buzz.

            state.violated = violated

        return to_alert

    def active(self) -> list[Rule]:
        """Rules currently in violation, for status display."""
        return [r for r in self.rules if self._state[r.number].violated]
