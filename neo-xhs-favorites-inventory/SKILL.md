---
name: neo-xhs-favorites-inventory
description: "Inventory Xiaohongshu favorites through BrowserOS neo, reconcile accessible records and count gaps, and preserve per-item reading coverage. Cleanup requires its own valid authorization."
---

# Xiaohongshu favorites inventory

Requires the separately installed BrowserOS neo skill and MCP connection, and the intended account's existing login. Follow `agent-browser` for browser selection and task-tab cleanup. Read the tools currently exposed by the host rather than copying an older browser API.

1. Verify the live profile and active Favorites tab before collecting. Restrict reads to the intended account/tab.
2. Enumerate virtualized cards and available pagination, deduplicating stable note IDs. Record the displayed total, accessible unique count, pagination end and any inaccessible records separately.
3. Read each accessible note's text and relevant images/video. Source metadata and observed subtitles can improve coverage; absent subtitles or inaccessible media remain explicit limitations. Never export cookies or unrelated page state.
4. Canonical note URLs identify sources; observed access URLs may carry required parameters and belong only in scoped execution evidence. Do not invent missing IDs from a count gap.
5. Prepare an inventory with source links, content summaries and per-item coverage. A final pagination flag means that endpoint ended; it does not prove unseen items were deleted.

Invalid-item cleanup is separate from inventory. Use [the cleanup criteria](../saved-content-review/references/platforms.md) only when the current task or verified owner profile actually authorizes it. Counts, timeouts, login failures and inaccessible content alone do not establish invalidity. Preserve before/after evidence and report removals separately from archived sources. Close task-created tabs after saving the result.

## Local owner context

If `~/.config/personal-skills/profiles/neo-xhs-favorites-inventory/SKILL.md` exists, read it once for this task's private destinations, environment and established constraints. Keep that profile local. Verify changing facts live; a saved profile does not grant new access or authorize an unrelated action. Without a configured profile, resolve the required inputs from the current request and authorized tools; never invent the author's account or destination.
