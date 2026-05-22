---
description: Register this Claude Code session in the chat directory so other sessions can talk to it
---

Register this session.

Arguments (both optional): `[name] [description]`

If the user provides args, use them verbatim. Otherwise infer from session context:

- **name**: basename of the current working directory, lowercased, spaces → underscores.
- **description**: one sentence on this session's project and focus. Base it on the cwd, any README/CLAUDE.md you've already seen, and recent work in this session. Mention the project/repo and area of expertise.

Don't ask the user to confirm — inferred defaults are good enough to start. If they dislike them, they'll re-register explicitly.

Run:

```
python3 "${CLAUDE_PLUGIN_ROOT}/bin/agent_chat.py" register "<name>" "<description>"
```

After registering, run `/chat:list` so the user sees who else is online.
