---
disable-model-invocation: true
name: notion-trash
description: "Inspect, trash or restore explicitly selected Notion pages using guarded title/timestamp checks and readback. It never permanently deletes pages."
---

# Notion trash

Use for whole-page trash/restore. Ordinary content edits use the existing Notion connector. Read `notion-writing` and the configured workspace constraints before acting; organizing or deduplicating an archive does not authorize deleting pages.

Prefer an available documented trash/restore connector. The included standard-library helper is an optional Notion API supplement and also exposes a local MCP server. It requires its own user-supplied Notion credential and does not borrow another connector's OAuth token.

1. Inspect the exact selected target and its live title, edit timestamp, parent, children and trash state.
2. Check the user's requested scope and any workspace restriction. Explain a material child-page impact before acting beyond the selected scope.
3. Pass the exact inspected title and timestamp as guards to trash or restore. On a mismatch, re-read; never guess or overwrite a concurrent edit.
4. Read back the resulting state. An unknown mutation outcome requires inspection before retrying.

Run `python3 scripts/notion_trash.py --help` from this skill directory. Initial authorized setup uses `python3 scripts/notion_trash.py setup` in the user's own terminal with a hidden prompt; never ask for a token in chat. The helper validates the credential and stores it privately under the user's configuration directory. Respect normal OS authentication prompts and preserve access boundaries.

Trashing a page is recoverable through Notion's normal restore flow. The helper does not permanently delete content. Some restore operations require Notion's own UI; report that limit rather than broadening access or credentials.

## Local owner context

If `~/.config/personal-skills/profiles/notion-trash/SKILL.md` exists, read it once for this task's private destinations, environment and established constraints. Keep that profile local. Verify changing facts live; a saved profile does not grant new access or authorize an unrelated action. Without a configured profile, resolve the required inputs from the current request and authorized tools; never invent the author's account or destination.
