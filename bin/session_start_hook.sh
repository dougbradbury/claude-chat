#!/usr/bin/env bash
# SessionStart hook for claude-chat.
# Reads the hook event JSON from stdin, extracts cwd, registers this session
# with inferred defaults (name = cwd basename, description = "agent in <cwd>").
# Silent on success; silent on failure (Redis down, name collision with another
# session in a different cwd, etc.) — auto-registration is best-effort.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if command -v jq >/dev/null 2>&1; then
  payload=$(cat)
  session_cwd=$(printf '%s' "$payload" | jq -r '.cwd // empty')
fi
session_cwd="${session_cwd:-$PWD}"

if [[ -d "$session_cwd" ]]; then
  cd "$session_cwd"
fi

python3 "$SCRIPT_DIR/agent_chat.py" register >/dev/null 2>&1 || true
