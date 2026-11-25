#!/usr/bin/env bash
# Install the final build. Thin wrapper around the top-level installer, so this
# folder works on its own:  ./variants/final/install.sh
set -euo pipefail
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/install.sh" final "$@"
