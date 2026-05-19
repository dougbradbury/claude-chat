---
description: Ask another registered session a question. Blocks until they answer.
---

Ask a registered session a question. The call blocks indefinitely until they answer. The user can cancel by interrupting (Esc). If the target answers after a cancel, the answer surfaces on the next `/check` as `kind: late_answer`.

Arguments: `<target> <question>`

Example: `/ask core-services "What auth header does POST /v1/farmers expect?"`

Steps:

1. If the user didn't specify a target, run `/chat-list` first so they can see who's available, then ask which to query.
2. Tell the user "asking <target>, waiting…" so they know what's happening — the target needs to switch to their session and run `/check` for the question to be seen.
3. Run:

   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/bin/agent_chat.py" ask "<target>" "<question>"
   ```

   Pass the Bash `timeout` parameter at a large value (e.g. 1800000 = 30 min) since `ask` has no internal timeout. If the user really wants longer, they can re-ask.

4. When the answer comes back, present it verbatim to the user and use it to continue the task at hand.
5. If the user interrupts the call (Esc), tell them the question is still queued and the answer (if any) will appear on the next `/check`.
