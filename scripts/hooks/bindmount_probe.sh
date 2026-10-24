#!/usr/bin/env bash
# SessionStart: run the bind-mount probe from CLAUDE.md ("RESOLVED: bind-mounted
# file edits now reach the containers"). Docker Desktop once served a stale copy
# of every edited file; the symptom is silent, so check it before it costs a session.
# Silent when the container is down or the probe passes. Never blocks.
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
export MSYS_NO_PATHCONV=1  # Git Bash would rewrite /jytte/... into a Windows path
docker inspect -f '{{.State.Running}}' jytte 2>/dev/null | grep -q true || exit 0
f=config/zz-probe.txt
[ -e "$f" ] && exit 0  # someone else's probe or file: never overwrite
trap 'rm -f "$f"' EXIT
printf 'v1\n' > "$f"
a=$(docker exec jytte cat /jytte/$f 2>/dev/null)
printf 'v2-EDITED-LONGER\n' > "$f"
sleep 1
b=$(docker exec jytte cat /jytte/$f 2>/dev/null)
if [ "$b" != "v2-EDITED-LONGER" ]; then
  echo "WARNING bind-mount probe failed: the jytte container sees '${b:-nothing}' after an edit. Edits to config/*.yml and other mounted files will NOT reach the container. Fix: restart Docker Desktop (check docker ps first, it stops every container). See CLAUDE.md."
fi
exit 0
