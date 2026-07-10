#!/usr/bin/env bash
# Install the factory's Claude Code subagents into a target repo.
#
# Usage:
#   ./install-agents.sh /path/to/target-repo [--commit]
#
# Non-destructive: existing agents with the same name are skipped (use
# --force to overwrite). --commit stages and commits the added files.
set -euo pipefail

KIT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/agents"
TARGET="${1:-}"
FORCE=false
COMMIT=false
for arg in "${@:2}"; do
  case "$arg" in
    --force)  FORCE=true ;;
    --commit) COMMIT=true ;;
    *) echo "Unknown option: $arg" >&2; exit 1 ;;
  esac
done

if [[ -z "$TARGET" || ! -d "$TARGET" ]]; then
  echo "Usage: $0 /path/to/target-repo [--force] [--commit]" >&2
  exit 1
fi
if [[ ! -d "$TARGET/.git" ]]; then
  echo "Warning: $TARGET is not a git repo root — installing anyway." >&2
fi

AGENTS_DIR="$TARGET/.claude/agents"
mkdir -p "$AGENTS_DIR"

installed=0 skipped=0
for f in "$KIT_DIR"/*.md; do
  name="$(basename "$f")"
  if [[ -e "$AGENTS_DIR/$name" && "$FORCE" != true ]]; then
    echo "  skip $name (already exists — use --force to overwrite)"
    ((skipped++)) || true
  else
    cp "$f" "$AGENTS_DIR/$name"
    echo "  add  .claude/agents/$name"
    ((installed++)) || true
  fi
done

echo "Done: $installed installed, $skipped skipped."

if [[ "$COMMIT" == true && "$installed" -gt 0 ]]; then
  git -C "$TARGET" add .claude/agents
  git -C "$TARGET" commit -m "chore: add Claude Code subagents (code-explorer, test-writer, code-reviewer)"
  echo "Committed."
fi

echo
echo "Tip: tune the agent files for this repo (real test commands, module"
echo "names, frameworks) — generic agents work, specific agents work better."
