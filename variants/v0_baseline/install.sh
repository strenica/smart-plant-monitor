#!/usr/bin/env bash
# Install v0_baseline. Thin wrapper around the top-level installer, so this folder works
# on its own:  ./variants/v0_baseline/install.sh
set -euo pipefail
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/install.sh" v0_baseline "$@"
