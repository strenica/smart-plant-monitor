"""Parsing for configuration.txt and the ESP32's reading lines.

configuration.txt holds one rule per line:

    1: air_humidity > 50
    2: air_temperature < 15
    3: soil_humidity < 300

The rule number is the buzz count: rule 2 buzzes twice. That is the spec's
encoding, not a design choice of ours.

The ESP32 sends one reading per line over UART2:

    t=5280 soil=1000 adc=2428 air_t=20.5 air_h=51
    t=7330 soil=1000 adc=2429 air=ERR

`air=ERR` means the DHT11 has not produced a value yet, which happens for the
first second after boot and whenever the sensor is unplugged.
"""

from __future__ import annotations

import operator
import re
from dataclasses import dataclass

# The three fields a rule may test, mapped to the names used in
# configuration.txt. Keeping this explicit means a typo in the config file is
# reported rather than silently ignored.
FIELDS = ("air_humidity", "air_temperature", "soil_humidity")

OPS = {
    "<": operator.lt,
    ">": operator.gt,
    "<=": operator.le,
    ">=": operator.ge,
}

_RULE_RE = re.compile(
    r"^\s*(?P<number>\d+)\s*:\s*(?P<field>[a-z_]+)\s*(?P<op><=|>=|<|>)\s*(?P<threshold>-?\d+(?:\.\d+)?)\s*$"
)

_READING_RE = re.compile(
    r"t=(?P<ms>\d+)\s+soil=(?P<soil>\d+)\s+adc=(?P<adc>\d+)"
    r"(?:\s+air_t=(?P<t>-?\d+(?:\.\d+)?)\s+air_h=(?P<h>-?\d+(?:\.\d+)?)|\s+air=ERR)?"
)


@dataclass(frozen=True)
class Rule:
    """One line of configuration.txt."""

    number: int      # also the buzz count
    field: str
    op: str
    threshold: float

    def violated_by(self, reading: "Reading") -> bool:
        value = reading.value_of(self.field)
        if value is None:
            # No measurement for this field yet. A missing value is not a
            # violation; buzzing because the DHT11 has not warmed up would be
            # a false alarm.
            return False
        return OPS[self.op](value, self.threshold)

    def __str__(self) -> str:
        return f"{self.number}: {self.field} {self.op} {self.threshold:g}"


@dataclass(frozen=True)
class Reading:
    """One sample from the ESP32."""

    uptime_ms: int
    soil: int
    adc: int
    air_temp: float | None
    air_humidity: float | None

    def value_of(self, field: str) -> float | None:
        if field == "air_humidity":
            return self.air_humidity
        if field == "air_temperature":
            return self.air_temp
        if field == "soil_humidity":
            return float(self.soil)
        raise KeyError(f"unknown field {field!r}")


_TIMING_RE = re.compile(r"^(?P<key>[a-z_]+)\s*=\s*(?P<value>-?\d+(?:\.\d+)?)$")

# Every interval configuration.txt may set, in seconds. Anything else is
# rejected rather than ignored, so a typo is reported instead of silently
# leaving the compiled default in place.
TIMING_KEYS = (
    "sample_interval",   # how often the ESP32 samples
    "image_interval",    # how often the Pi takes a picture (V1)
    "heartbeat",         # how often the Pi photographs when nothing happens (V2)
    "adaptive_fast",     # interval while the readings are moving (V2, V3)
    "adaptive_slow",     # interval after three quiet samples (V2, V3)
)


@dataclass(frozen=True)
class Timing:
    """Intervals from configuration.txt. None means "use the variant default"."""

    sample_interval: float | None = None
    image_interval: float | None = None
    heartbeat: float | None = None
    adaptive_fast: float | None = None
    adaptive_slow: float | None = None


def parse_timing(text: str) -> Timing:
    """Read the `key = value` lines from configuration.txt.

    Rule lines are ignored here; parse_config handles those. Both live in the
    same file because there is only one thing to edit when tuning the system.
    """
    values: dict[str, float] = {}

    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue

        match = _TIMING_RE.match(line)
        if not match:
            continue   # a rule line

        key = match["key"]
        if key not in TIMING_KEYS:
            raise ValueError(
                f"line {lineno}: unknown setting {key!r}, "
                f"expected one of {', '.join(TIMING_KEYS)}"
            )
        values[key] = float(match["value"])

    return Timing(**values)


def parse_config(text: str) -> list[Rule]:
    """Parse configuration.txt. Blank lines and # comments are skipped.

    Raises ValueError on a malformed line, naming the line number, because a
    silently ignored rule is a rule that never fires.
    """
    rules: list[Rule] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue

        match = _RULE_RE.match(line)
        if not match:
            if _TIMING_RE.match(line):
                continue   # a timing setting, handled by parse_timing
            raise ValueError(f"line {lineno}: cannot parse {raw!r}")

        field = match["field"]
        if field not in FIELDS:
            raise ValueError(
                f"line {lineno}: unknown field {field!r}, expected one of {', '.join(FIELDS)}"
            )

        rules.append(
            Rule(
                number=int(match["number"]),
                field=field,
                op=match["op"],
                threshold=float(match["threshold"]),
            )
        )

    return rules


def parse_reading(line: str) -> Reading | None:
    """Parse one line from the ESP32. Returns None if it is not a reading."""
    match = _READING_RE.search(line)
    if not match:
        return None

    temp = match["t"]
    hum = match["h"]
    return Reading(
        uptime_ms=int(match["ms"]),
        soil=int(match["soil"]),
        adc=int(match["adc"]),
        air_temp=float(temp) if temp is not None else None,
        air_humidity=float(hum) if hum is not None else None,
    )
