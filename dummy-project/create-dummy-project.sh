#!/usr/bin/env bash
# Generate the ChatDock dummy target project with Claude Code, install the
# subagents, and push it to GitHub. Run this ON THE VM.
#
# Usage:
#   ./create-dummy-project.sh <github-owner>/<repo-name> [target-dir]
# Example:
#   ./create-dummy-project.sh bob/chatdock ~/chatdock
set -euo pipefail

REPO="${1:-}"
TARGET_DIR="${2:-$HOME/chatdock}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SPEC="$SCRIPT_DIR/DUMMY_PROJECT_SPEC.md"
KIT="$SCRIPT_DIR/../target-repo-kit/install-agents.sh"

if [[ -z "$REPO" ]]; then
  echo "Usage: $0 <owner>/<repo> [target-dir]" >&2; exit 1
fi
command -v claude >/dev/null || { echo "claude not found" >&2; exit 1; }
command -v gh >/dev/null     || { echo "gh not found" >&2; exit 1; }
[[ -f "$SPEC" ]]             || { echo "Spec not found: $SPEC" >&2; exit 1; }

mkdir -p "$TARGET_DIR" && cd "$TARGET_DIR"
git init -q 2>/dev/null || true

echo "==> Generating ChatDock with Claude Code (this takes a while)..."
claude -p "Read the specification below and build the complete project in the
current directory. Follow it exactly — architecture, tests, CI, and CLAUDE.md
files are all required. Verify the definition of done yourself as far as
possible in this environment (run backend tests, frontend lint/tsc/build;
run docker compose if docker is available). Fix anything that fails.

$(cat "$SPEC")" \
  --dangerously-skip-permissions --max-turns 250

echo "==> Installing Claude Code subagents..."
bash "$KIT" "$TARGET_DIR"

echo "==> Committing and pushing to GitHub..."
git add -A
git commit -m "ChatDock: containerized messaging app (agent-factory dummy target)" -q
gh repo create "$REPO" --private --source=. --push

echo
echo "==> Done. Next steps:"
echo "  1. Check CI is green:   gh run watch --repo $REPO"
echo "  2. Point the factory at it:  set GITHUB_REPO=$REPO, DEFAULT_BRANCH=main,"
echo "     SANDBOX_URL=http://<VM-IP>:3000 in agent-factory/.env"
echo "  3. Smoke-test manually: cd $TARGET_DIR && docker compose up -d --build"
echo "     then open http://<VM-IP>:3000 and log in as alice / demo1234"
echo "  4. Fire your first task in Slack:"
echo "     build: add an email invite feature — a logged-in user can enter an"
echo "     email address, the app creates an invite record and shows pending"
echo "     invites; actually sending email can be mocked with a log line."
