#!/usr/bin/env bash
# Install v3_deepsleep. Thin wrapper around the top-level installer, so this folder works
# on its own:  ./variants/v3_deepsleep/install.sh
set -euo pipefail
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/install.sh" v3_deepsleep "$@"
