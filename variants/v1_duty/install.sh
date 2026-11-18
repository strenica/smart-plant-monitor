#!/usr/bin/env bash
# Install v1_duty. Thin wrapper around the top-level installer, so this folder works
# on its own:  ./variants/v1_duty/install.sh
set -euo pipefail
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/install.sh" v1_duty "$@"
