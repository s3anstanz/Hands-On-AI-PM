#!/usr/bin/env bash
# Regenerate requirements*.txt from uv.lock (CI fails if they drift).
# Run after any dependency change, including Dependabot PRs, whose edits to
# these files don't match uv.lock.
set -euo pipefail
cd "$(dirname "$0")/.."
uv lock --check || uv lock
uv export --no-dev --format requirements-txt -o requirements.txt -q
uv export --no-dev --extra live --format requirements-txt -o requirements-live.txt -q
uv export --all-extras --format requirements-txt -o requirements-dev.txt -q
git status --short -- uv.lock 'requirements*.txt'
