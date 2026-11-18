"""Shared helpers for the Pi side of the plant monitor."""

# Exit code a variant uses to tell the supervisor "the ESP32 was reset, so run
# the camera preview instead of me". Anything else means the variant stopped
# for its own reasons and the supervisor should not restart it.
SETUP_EXIT = 42
