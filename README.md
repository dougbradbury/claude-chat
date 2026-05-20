# claude-chat

Cross-session messaging for [Claude Code](https://claude.com/claude-code). Run several Claude Code sessions in different repos, then `/tell`, `/ask`, and `/check` between them instead of copy-pasting through your shell.

Two sessions exchanging notes:

```
session A (in field_application)        session B (in core_services)
─────────────────────────────────       ───────────────────────────────────
/ask core-services "What auth header
does POST /v1/farmers expect?"
  → waiting…
                                        /check
                                          → 1 question from field_application
                                          (Claude reads its repo, answers)
                                        agent_chat.py answer …
  → "Bearer token, see auth.py:42"
```

## What it gives you

- **`/ask <target> <question>`** — block until the other session answers.
- **`/tell <target> <message>`** — fire-and-forget. Recipient sees it on next `/check`.
- **`/check`** — drain inbox; answer pending questions, surface tells and any late answers.
- **`/chat-register`**, **`/chat-list`**, **`/chat-unregister`** — manage the session directory.
- A `SessionEnd` hook unregisters you when the session closes.

Messages travel through a small local Redis (Docker container, bound to `127.0.0.1` only).

## Requirements

- macOS or Linux (untested on Windows).
- [Claude Code](https://docs.claude.com/en/docs/claude-code).
- Python 3.10+ with `pip`.
- Docker (for the bundled Redis container) or any Redis ≥ 6 reachable at `127.0.0.1:6380`.

## Install (plugin)

This repo is its own Claude Code marketplace. In any Claude Code session, add the marketplace and install the plugin:

```
/plugin marketplace add https://github.com/dougbradbury/claude-chat
/plugin install claude-chat@claude-chat
```

Then install the Python dependencies and start Redis. From the plugin install directory (Claude Code will print the path after install — typically `~/.claude/plugins/marketplaces/claude-chat/`):

```
pip install -r requirements.txt
docker compose up -d
```

Restart Claude Code so it picks up the new slash commands and `SessionEnd` hook, then in any session:

```
/chat-register
/chat-list
```

## Install (manual, no plugin)

If you prefer not to use the plugin system:

```
git clone https://github.com/dougbradbury/claude-chat ~/.local/share/claude-chat
cd ~/.local/share/claude-chat
pip install -r requirements.txt
docker compose up -d
```

Then copy or symlink the slash commands and wire up the hook. Inside each command's markdown, replace `${CLAUDE_PLUGIN_ROOT}` with the absolute path to your install (e.g. `~/.local/share/claude-chat`):

```
mkdir -p ~/.claude/commands
for f in commands/*.md; do
  sed "s|\${CLAUDE_PLUGIN_ROOT}|$HOME/.local/share/claude-chat|g" "$f" > ~/.claude/commands/"$(basename "$f")"
done
```

Add this to `~/.claude/settings.json` (merge with existing `hooks` if any):

```json
{
  "hooks": {
    "SessionEnd": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "$HOME/.local/share/claude-chat/bin/session_end_hook.sh"
          }
        ]
      }
    ]
  }
}
```

## How it works

- A Redis HASH at `agents:registry` lists registered sessions (name, description, cwd).
- Each session has an inbox LIST at `agent:<name>:requests`. `tell` and `ask` push into the target's inbox.
- `ask` then `BLPOP`s on a per-request reply slot at `agent:<asker>:replies:<request_id>` and waits indefinitely. The recipient's `answer` command pushes the reply into that slot.
- If `ask` is interrupted (Esc), it leaves a pending entry in `agent:<asker>:pending`. A later `/check` drains any answers that arrived after the interrupt and surfaces them as `kind: late_answer`.
- Identity is per-cwd: a local file in `~/.claude_chat/<cwd_slug>.json` records the name this session registered under. Different sessions in different project directories get separate identities automatically.
- A `SessionEnd` hook reads the session's `cwd` from stdin and unregisters cleanly. Hard kills (`kill -9`, OS crash) won't fire the hook, so the registry may occasionally contain a dead session — `/chat-unregister` it manually, or restart the Redis container to reset.

## Safety

- The bundled Redis container binds to `127.0.0.1:6380` only. Don't expose 6380 to other interfaces.
- No authentication: localhost binding is the trust boundary.
- No persistence: a container restart wipes the registry and all in-flight messages. Sessions just re-register on their next `/chat-register`.
- Message size is capped at 16 KB per item to avoid context-window blowouts on the receiving side.

## Configuration

Environment variables (set in your shell or `.env`):

- `CLAUDE_CHAT_REDIS_HOST` (default `127.0.0.1`)
- `CLAUDE_CHAT_REDIS_PORT` (default `6380`)

## License

MIT — see [LICENSE](LICENSE).
