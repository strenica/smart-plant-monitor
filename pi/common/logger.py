"""events_log.txt writer.

The format is fixed by the project spec:

    Mon Oct 21 14:04:30 CEST 2024: air_humidity = 48
    Mon Oct 21 14:04:30 CEST 2024: air_temperature = 13
    Mon Oct 21 14:04:31 CEST 2024: buzzer 2

Note the timezone between the time and the year. `time.ctime()` does not
include it, so the stamp is built with strftime instead.
"""

from __future__ import annotations

import time
from pathlib import Path

STAMP_FORMAT = "%a %b %d %H:%M:%S %Z %Y"


def stamp(when: float | None = None) -> str:
    """Format a timestamp the way the spec shows it."""
    return time.strftime(STAMP_FORMAT, time.localtime(when))


class EventLog:
    """Append-only event log. Flushes every line so it can be tailed live."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("a", buffering=1)

    def _write(self, text: str) -> None:
        self._fh.write(text + "\n")
        self._fh.flush()

    def measurement(self, field: str, value: float) -> None:
        """Log one sensor value. Integers print without a decimal point."""
        if float(value).is_integer():
            self._write(f"{stamp()}: {field} = {int(value)}")
        else:
            self._write(f"{stamp()}: {field} = {value:g}")

    def buzzer(self, times: int) -> None:
        """Log a buzz action. `times` is the rule number that fired."""
        self._write(f"{stamp()}: buzzer {times}")

    def note(self, text: str) -> None:
        """Anything else worth recording, such as a startup marker."""
        self._write(f"{stamp()}: {text}")

    def close(self) -> None:
        self._fh.close()

    def __enter__(self) -> "EventLog":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
