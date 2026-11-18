#!/usr/bin/env bash
# Source this before building:  . tools/idf_env.sh
#
# ESP-IDF's export.sh looks for a Python virtual environment matching the
# system python3. When the system python is upgraded, the existing venv no
# longer matches and export.sh fails with "virtual environment not found" even
# though the venv itself still works. Point it at whatever venv is actually
# installed instead of reinstalling the whole toolchain.

if [ -z "${IDF_PYTHON_ENV_PATH:-}" ]; then
  for candidate in "$HOME"/.espressif/python_env/idf*_env; do
    if [ -x "$candidate/bin/python" ]; then
      IDF_PYTHON_ENV_PATH="$candidate"
    fi
  done
  export IDF_PYTHON_ENV_PATH
fi

IDF_PATH="${IDF_PATH:-$HOME/esp/esp-idf}"
export IDF_PATH

# shellcheck disable=SC1091
. "$IDF_PATH/export.sh" >/dev/null
