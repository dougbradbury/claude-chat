#!/usr/bin/env bash
# SessionEnd hook for claude-chat.
# Reads the hook event JSON from stdin and unregisters this session — but only
# on real exits, not on /clear, /resume, or other in-session events.
# Silent on success; silent on "not registered" (most sessions won't be).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Parse cwd and reason from the hook stdin JSON. Fall back to PWD if jq isn't
# around (in which case we also can't filter by reason, so we err on the side
# of doing nothing).
reason=""
session_cwd=""
if command -v jq >/dev/null 2>&1; then
  payload=$(cat)
  session_cwd=$(printf '%s' "$payload" | jq -r '.cwd // empty')
  reason=$(printf '%s' "$payload" | jq -r '.reason // empty')
fi
session_cwd="${session_cwd:-$PWD}"

# Only fire on actual session exits. /clear, /resume, and ambiguous "other"
# events keep the session registered — the terminal is still open, the user
# just reset context.
case "$reason" in
  prompt_input_exit|logout)
    : ;;
  *)
    exit 0 ;;
esac

# The CLI reads identity from ~/.claude_chat/<cwd_slug>.json based on Path.cwd(),
# so we cd into the session's cwd before invoking it.
if [[ -d "$session_cwd" ]]; then
  cd "$session_cwd"
fi

# Run unregister but don't fail the hook if it errors (e.g. Redis is down,
# or this session was never registered).
python3 "$SCRIPT_DIR/agent_chat.py" unregister >/dev/null 2>&1 || true
