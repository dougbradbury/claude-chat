#!/usr/bin/env bash
# SessionEnd hook for claude-chat.
# Reads the hook event JSON from stdin, extracts cwd, unregisters this session.
# Silent on success; silent on "not registered" (most sessions won't be).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Parse cwd from the hook stdin JSON. Fall back to PWD if jq isn't around.
if command -v jq >/dev/null 2>&1; then
  payload=$(cat)
  session_cwd=$(printf '%s' "$payload" | jq -r '.cwd // empty')
fi
session_cwd="${session_cwd:-$PWD}"

# The CLI reads identity from ~/.claude_chat/<cwd_slug>.json based on Path.cwd(),
# so we cd into the session's cwd before invoking it.
if [[ -d "$session_cwd" ]]; then
  cd "$session_cwd"
fi

# Run unregister but don't fail the hook if it errors (e.g. Redis is down,
# or this session was never registered).
python3 "$SCRIPT_DIR/agent_chat.py" unregister >/dev/null 2>&1 || true
