---
name: telegram-digest
description: Read-only Telegram group and channel summarizer backed by tdl. Exports chat history, downloads shared photos and image screenshots for visual inspection, and synthesizes cited key-point digests.
---

# Telegram Digest

Run `python3 scripts/tg_fetch.py ...` from this skill directory (or pass its absolute script path). Never invoke `tdl forward`, `tdl up`, or send/modify anything in Telegram.

## 1. Preflight & Auth

```sh
python3 scripts/tg_fetch.py doctor --live
```

If `ok` is `false` or `authenticated` is `false`, ask the user to run `tdl login -T qr` in an interactive terminal (Ghostty on macOS) and scan the QR code from Telegram (`Settings -> Devices -> Link Desktop Device`). Never ask for SMS/OTP codes or 2FA passwords in chat. Pass `--proxy <url>` (or set `TDL_PROXY` / `ALL_PROXY` / `HTTPS_PROXY`) if Telegram requires a proxy on the current network.

## 2. Resolve & Fetch

```sh
# Find chat ID/title when ambiguous
python3 scripts/tg_fetch.py list --query '<group_name>'

# Export last 24h (default) + up to 20 most-recent images
python3 scripts/tg_fetch.py fetch --chat '<name_or_id>' --hours 24

# Alternative windows and options
python3 scripts/tg_fetch.py fetch --chat '<name_or_id>' --last 200
python3 scripts/tg_fetch.py fetch --chat '<name_or_id>' --since 2026-11-25T00:00:00
python3 scripts/tg_fetch.py fetch --chat '<name_or_id>' --topic 42 --max-images 25
python3 scripts/tg_fetch.py fetch --chat '<name_or_id>' --hours 24 --no-images
```

If `fetch` exits with multiple matching `candidates`, show them and ask which chat to summarize. Exports default to `/tmp/telegram-digest/<timestamp>-<chat>/`—never commit exports or `~/.tdl/` data.

## 3. Inspect & Summarize

1. Read `transcript.md` from the returned `manifest.json` (`transcript_path`).
2. Inspect relevant downloaded images (`images[].path`) in parallel with `read_file`, prioritizing screenshots, charts, error logs, slides, and diagrams over stickers or casual memes.
3. Deliver a concise, topic-grouped digest covering key takeaways/decisions, shared links/resources, visual findings from inspected screenshots, and open questions or action items. Cite `#msg_id` and timestamps for claims, and report the exact window, `images_omitted`, and `skipped_media_counts` honestly.
