#!/bin/sh
# n8n workflow auto-import on container start.
#
# Runs in parallel to n8n itself (forked via the entrypoint), waits for
# n8n's HTTP API to come up, then imports every JSON file under
# /workflows/ via the n8n CLI. Idempotent: re-importing an existing
# workflow updates it in place; new workflows are created.
#
# Workflow files in this repo are the source of truth (F5 Q4 = b).
# Editing loop:
#   1. Iterate visually in the n8n UI
#   2. Click Export -> overwrite the JSON in deploy/n8n/workflows/
#   3. Commit
#   4. On the home server, rolling-restart the n8n pod -> re-import.

set -e

WORKFLOWS_DIR="/workflows"
N8N_URL="http://localhost:5678"
MAX_WAIT=120
WAITED=0

# Wait for n8n's HTTP server to respond
echo "[init] waiting for n8n at ${N8N_URL}..."
until wget -q -O - "${N8N_URL}/healthz" >/dev/null 2>&1; do
    sleep 2
    WAITED=$((WAITED + 2))
    if [ "${WAITED}" -ge "${MAX_WAIT}" ]; then
        echo "[init] timed out waiting for n8n after ${MAX_WAIT}s; skipping import"
        exit 0
    fi
done
echo "[init] n8n up after ${WAITED}s"

# Give the API another second to fully settle
sleep 2

if [ ! -d "${WORKFLOWS_DIR}" ]; then
    echo "[init] no workflows directory at ${WORKFLOWS_DIR}; nothing to import"
    exit 0
fi

count=0
for f in "${WORKFLOWS_DIR}"/*.json; do
    [ -f "$f" ] || continue
    name=$(basename "$f")
    echo "[init] importing ${name}"
    # The `--separate` flag plus `--input=<file>` is the canonical
    # CLI-import form. Returns non-zero on parse errors but not on
    # "already exists" (n8n upserts by id).
    if n8n import:workflow --input="${f}" 2>&1 | sed 's/^/[n8n-import] /'; then
        count=$((count + 1))
    else
        echo "[init] WARN failed to import ${name}; continuing"
    fi
done
echo "[init] imported ${count} workflows"
