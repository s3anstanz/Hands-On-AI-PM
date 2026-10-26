#!/usr/bin/env bash
# pre-push hook (via pre-commit): branch protection isn't available on this
# repo's plan, so refuse pushes to main locally. Merge through a PR instead.
set -euo pipefail
case "${PRE_COMMIT_REMOTE_BRANCH:-}" in
  refs/heads/main | main)
    echo "Refusing to push to main. Open a PR from a branch instead." >&2
    exit 1
    ;;
esac
