#!/usr/bin/env bash
#
# check_feature_folded.sh [base-ref]
# ----------------------------------
# Fails a PR that changes a work-item folder under docs/features/ without
# also changing that item's page in docs/source/features/, which is what
# fold_feature.py writes. The fold belongs in the same PR as the change, so it
# is reviewed with it and lands on the target branch at merge.
#
# Deliberately cheap: bash and git only, no Python, no Sphinx build. It checks
# that the page moved with the folder, not that the page is current; running
# `fold_feature.py --check` is the stronger test for a machine that has the
# skill installed.
#
# Copied from the sphinx-docs skill (scripts/check_feature_folded.sh) into
# each repo's tools/. Edit it there in the skill, then copy again.
#
# Bypass: the literal token [no-doc-fold] in a commit message on the branch,
# or in the PR body via the PR_BODY env var (ADO: $(System.PullRequest.Description)).
#
# Base ref: $1, else origin/<target> from $SYSTEM_PULLREQUEST_TARGETBRANCH or
# $GITHUB_BASE_REF, else origin/dev, else origin/main, else main.
#
# --staged: compare the index with HEAD instead. This is the mode for a
# pre-merge-commit hook: git runs that hook before it writes MERGE_HEAD, so
# the merge result is only visible in the index. Bypass there with
# SKIP=fold-check git merge ...
#
# Exit: 0 pass or nothing to check, 1 a folder changed without its page.

set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

if [ ! -d docs/source ]; then
    echo "check_feature_folded: no docs/source in this repo; skipping" >&2
    exit 0
fi

if [ "${1:-}" = "--staged" ]; then
    CHANGED="$(git diff --cached --name-only HEAD)"
else
    TIP="HEAD"
    BASE="${1:-}"
    if [ -z "$BASE" ]; then
        tgt="${SYSTEM_PULLREQUEST_TARGETBRANCH:-${GITHUB_BASE_REF:-}}"
        tgt="${tgt#refs/heads/}"
        for c in ${tgt:+origin/$tgt} origin/dev origin/main refs/heads/main; do
            if git rev-parse -q --verify "$c" >/dev/null; then BASE="$c"; break; fi
        done
    fi
    MB="$(git merge-base "$TIP" "$BASE" 2>/dev/null || true)"
    if [ -z "$MB" ]; then
        echo "check_feature_folded: no merge base between $TIP and ${BASE:-?}; skipping" >&2
        exit 0
    fi
    if git log --format=%B "$MB..$TIP" | grep -Fq "[no-doc-fold]" \
       || printf '%s' "${PR_BODY:-}" | grep -Fq "[no-doc-fold]"; then
        echo "check_feature_folded: [no-doc-fold] present; bypass OK" >&2
        exit 0
    fi
    CHANGED="$(git diff --name-only "$MB" "$TIP")"
fi

IDS="$(printf '%s\n' "$CHANGED" \
    | sed -nE 's#^docs/features/((JAVA-)?FEAT-[0-9]+)-[^/]+/.*#\1#p' | sort -u)"
if [ -z "$IDS" ]; then
    echo "check_feature_folded: no feature folder changed; nothing to check" >&2
    exit 0
fi

FAIL=0
for id in $IDS; do
    page="docs/source/features/$id.rst"
    if printf '%s\n' "$CHANGED" | grep -qxF "$page"; then
        echo "check_feature_folded: $id folded ($page)" >&2
    else
        echo "check_feature_folded: FAIL - docs/features/$id-*/ changed but $page did not." >&2
        FAIL=1
    fi
done
if [ "$FAIL" = 1 ]; then
    echo "Fold it: python <sphinx-docs-skill>/scripts/fold_feature.py --repo . --item docs/features/<folder>" >&2
    echo "or ask Claude to run the fold-feature sub-skill. Add [no-doc-fold] to the PR body if the change is a typo." >&2
    exit 1
fi
exit 0
