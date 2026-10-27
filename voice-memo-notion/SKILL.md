---
name: voice-memo-notion
description: "Turn selected Apple Voice Memos into Chinese, timestamped notes using a configured transcription service, preserving source evidence and verifying the saved result."
---

# Voice Memos to Notion

The author's default is Chinese notes with anonymous speaker separation, source timestamps and clear uncertainty. Requires authorized Voice Memos access, a configured ASR account/runtime and an authorized Notion destination. A request to handle a recording does not enable daily collection or source cleanup.

1. Refresh the available recordings, match the requested title/time and obtain the selected audio through the documented tool. Confirm the file is actually readable. Distinguish iCloud materialization from OS permission failures; use the normal permission/export path rather than reading around a restriction.
2. Use `scripts/transcribe.py` with the configured interpreter (`requests`, FFmpeg and ffprobe are required). Its default prints a plan and performs no upload. Verify the selected interval, fingerprint and reusable result before `--execute`.
3. Before a new cloud task, confirm the user's service, upload scope and cost policy. The author's preference is free-only processing: check the provider console's current quota/free-only setting and stop if unavailable. A historical price or client-side estimate is not a billing guarantee.
4. Credentials come from the user's environment or configured OS credential store. Account endpoint and Keychain labels come from local settings, never this repository. Do not print keys or export browser authentication. Initial credential setup must follow the host's normal user-authentication flow.
5. Resume pending work by its existing job identity. An unknown submission outcome requires reconciliation before another submission. Preserve private job state, strip signed URLs from artifacts and prevent concurrent duplicate runs.

Keep the complete timestamped transcript separate from edited notes. Speaker IDs apply only within the recording; do not infer people or carry mappings across recordings. Summarize topics, supported decisions and action items with source timestamps. Preserve unclear owners, dates, overlap and garbled speech explicitly; suggestions are not commitments. Keep receipts, task IDs and cost accounting in operational records, not routine reader prose.

Before saving, follow `notion-writing`, verify the configured archive and deduplicate by recording/run identity. Read back the saved title, destination, body, transcript coverage and retained source links. Saving notes does not authorize uploading the original audio to Notion or deleting the recording.

Scheduled processing is a separate configured mode; see [scheduled.md](references/scheduled.md). No recording, scheduling, permission or billing operation is executed by installing this skill.

## Local owner context

If `~/.config/personal-skills/profiles/voice-memo-notion/SKILL.md` exists, read it once for this task's private destinations, environment and established constraints. Keep that profile local. Verify changing facts live; a saved profile does not grant new access or authorize an unrelated action. Without a configured profile, resolve the required inputs from the current request and authorized tools; never invent the author's account or destination.
