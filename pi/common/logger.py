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
    """Append-only event log. Flushes every line so it can be tailed live.

    With `max_lines` set the file is trimmed to that many lines on open, and
    again whenever it has doubled, so a long run cannot fill the card. Trimming
    keeps the newest lines, because the interesting end of a log is the end.
    """

    def __init__(self, path: str | Path, max_lines: int | None = None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_lines = max_lines
        self._count = 0
        if max_lines:
            self._trim()
        self._fh = self.path.open("a", buffering=1)

    def _trim(self) -> None:
        """Keep only the newest max_lines lines."""
        if not self.path.exists():
            self._count = 0
            return

        lines = self.path.read_text(errors="replace").splitlines()
        if len(lines) > self.max_lines:
            lines = lines[-self.max_lines:]
            self.path.write_text("\n".join(lines) + "\n")
        self._count = len(lines)

    def _write(self, text: str) -> None:
        self._fh.write(text + "\n")
        self._fh.flush()
        self._count += 1

        if self.max_lines and self._count >= self.max_lines * 2:
            # Trim in batches rather than on every line: rewriting the file is
            # O(size), and doing it per write would dominate the cost.
            self._fh.close()
            self._trim()
            self._fh = self.path.open("a", buffering=1)

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
