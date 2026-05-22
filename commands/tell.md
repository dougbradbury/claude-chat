---
description: Send a message to another registered session. Fire-and-forget; no reply expected.
---

Send a message to a registered session. Returns immediately — no waiting, no reply expected. The target will see the message on their next `/chat:check`.

Arguments: `<target> <message>`

Examples:
- `/chat:tell core-services "FYI I just merged the new mobile_hotspot endpoint, you may want to bump your client lib"`
- `/chat:tell myagro-mobile "please add /healthz to the payments service when you get a chance"`

Steps:

1. If the user didn't specify a target, run `/chat:list` first so they can pick.
2. Run:

   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/bin/agent_chat.py" tell "<target>" "<message>"
   ```

3. Confirm to the user: "told <target>". Don't loiter — the call returned immediately.

Use `tell` for both informational FYIs and task suggestions. The receiving session's human decides whether to act on it; you (the asker) get no programmatic confirmation. If you need an answer, use `/chat:ask` instead.
