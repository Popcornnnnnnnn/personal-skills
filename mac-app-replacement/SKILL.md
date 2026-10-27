---
disable-model-invocation: true
name: mac-app-replacement
description: "Install or replace a macOS app and verify cleanup of confirmed obsolete copies with the same bundle identity. Use for app replacement, not routine builds."
---

# macOS App Replacement

Use the repository's existing build and installation flow. Inspect scripts for UI activation before running them; apply the current task's focus constraint rather than a universal no-focus rule.

- After installation or replacement, check for old copies with the same bundle ID in install locations, build outputs, backups, and Trash. Remove only confirmed obsolete copies.
- If a rollback copy is needed, keep it as an archive until verification, then delete it. Do not retain versioned app backups or temporary candidate builds unless requested.
- Verify the installed path, bundle identity, version, and relevant runtime behavior. Build success alone does not prove the installed app works.
- Check Spotlight and LaunchServices registrations after cleanup. Neither alone proves what the user's launcher shows.
- Complete visual checks when the authorized task and tools permit them. If the user required no focus and no isolated graphical session is verified, mark that check unverified, request only the necessary user check, and continue independent work.
- Follow the user's scope and tool-specific confirmation rules for deletion and system changes.

## Local owner context

If `~/.config/personal-skills/profiles/mac-app-replacement/SKILL.md` exists, read it once for this task's private destinations, environment and established constraints. Keep that profile local. Verify changing facts live; a saved profile does not grant new access or authorize an unrelated action. Without a configured profile, resolve the required inputs from the current request and authorized tools; never invent the author's account or destination.
