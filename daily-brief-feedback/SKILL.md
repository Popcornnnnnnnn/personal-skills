---
name: daily-brief-feedback
description: "Capture explicit human feedback on a daily brief or one exact item, preserving the original wording and avoiding invented preference labels."
---

# Daily brief feedback

Capture only feedback from the current authorized conversation. Do not monitor unrelated chats or treat an assistant suggestion, quoted source, or synthetic test as human feedback.

1. Identify the exact report/item from its canonical source URL or an unambiguous current-chat reference. An unclear target remains unresolved.
2. Keep the exact human quote and an available message locator. Several evaluations in one message can use separate quote spans; do not invent extra messages.
3. Separate item interest/disinterest/parking from length, depth, style, claimed factual corrections, and workflow requests. “Too shallow” is not disinterest; a report-wide comment does not label every item.
4. Read the configured feedback schema and current index before writing. If no storage contract is configured, return the proposed observation and report that it is unsaved.
5. For authorized persistence, use a stable observation identity, conditional writes and bounded conflict reconciliation. Keep immutable observations separate from a derived index. Verify both after saving; a saved observation with a failed index update is pending consumption.

Preserve editorial coverage and existing evaluation gates. A preference proposal does not automatically activate a strategy. This skill does not change reading dispositions, Notion fields, schedules, source cleanup, access, spending or messaging permissions. Acknowledge the exact feedback and target briefly.

## Local owner context

If `~/.config/personal-skills/profiles/daily-brief-feedback/SKILL.md` exists, read it once for this task's private destinations, environment and established constraints. Keep that profile local. Verify changing facts live; a saved profile does not grant new access or authorize an unrelated action. Without a configured profile, resolve the required inputs from the current request and authorized tools; never invent the author's account or destination.
