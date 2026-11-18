#!/usr/bin/env bash
# Install v2_adaptive. Thin wrapper around the top-level installer, so this folder works
# on its own:  ./variants/v2_adaptive/install.sh
set -euo pipefail
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/install.sh" v2_adaptive "$@"
