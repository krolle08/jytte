#!/usr/bin/env bash
# PreToolUse (Edit|Write): refuse to write code in this repo while it is on main.
# Mirrors the gate in twapp and floorballstats, but resolves the branch of the
# repo that owns the file, so an edit in another repo is judged by that repo.
p=$(jq -r '.tool_input.file_path // empty'); [ -z "$p" ] && exit 0
p=$(printf '%s' "$p" | tr '\\' '/')
d=$(dirname "$p"); [ -d "$d" ] || exit 0
top=$(git -C "$d" rev-parse --show-toplevel 2>/dev/null) || exit 0
here=$(git -C "${CLAUDE_PROJECT_DIR:-.}" rev-parse --show-toplevel 2>/dev/null) || exit 0
[ "${top,,}" = "${here,,}" ] || exit 0
case "${p,,}" in "${top,,}"/*) ;; *) exit 0 ;; esac  # Windows paths differ in case
rel=${p:${#top}+1}
echo "$rel" | grep -qE '^(app|scripts|tests|deploy|config)/' || exit 0
b=$(git -C "$top" rev-parse --abbrev-ref HEAD)
case "$b" in
  main|master)
    echo "Branch gate: refusing to write $rel while on '$b'. Branch first: git checkout -b feature/FEAT-NNN-<slug> (or bug/BUG-NNN-<slug>, chore/<slug>)." >&2
    exit 2 ;;
esac
exit 0
