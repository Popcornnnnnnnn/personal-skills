# Tool Prerequisites & Private Configuration

Per-skill external dependencies and private settings layout for `personal-skills`.

## Private Owner Profiles & Settings

- **Private skill profiles:** Store machine-specific destinations, Notion IDs, account names, and local rules in `~/.config/personal-skills/profiles/<skill>/SKILL.md` with owner-only permissions. Fresh installs have no preauthorized accounts, cleanup scopes, or schedules.
- **Adapter settings (`~/.config/personal-skills/settings.json`):** Non-secret adapter routing (keep API keys/secrets in environment variables or macOS Keychain, never in JSON or Git):

| Section | Required values when that adapter is used |
| --- | --- |
| `voice_memo_notion` | Official `origin`; `keychain_account` for Keychain use; optional `keychain_service` and a checked price estimate |
| `saved_content_review.accounts` | Intended `xhs`, `douyin`, and `bilibili` account identities |
| `shop_search` | Optional `python` interpreter and existing `jd_client_dir` |
| `tell_dot` | Verified `workspace_id`, `recipient_user_id`, and direct-message `conversation_id` |

## Per-Skill External Dependencies

- **`agent-browser` / `google-flow`:** Require a separately installed **BrowserOS neo** connection and active browser login sessions (`flow.google.com` / `flowmusic.app` for `google-flow`).
- **`iphone-wireless`:** Requires macOS with full Xcode, a pre-signed WebDriverAgent runner with Wi-Fi debugging enabled ("Connect via network" in Xcode), `appium` (`xcuitest` driver), `@wdio/mcp`, and `~/.local/bin/iphone-wireless`.
- **`notion-trash`:** Optional separate credentialed supplement with guarded trash/restore verification.
- **`shop-search`:** Needs a configured `cn_scraper_mcp` runtime (or explicit legacy JD bridge); no cookies ship in this repository.
- **`voice-memo-notion`:** Needs authorized audio access, Python `requests`, `ffmpeg`/`ffprobe`, and a configured transcription service (local planning vs task-authorized upload).
- **`learn`:** Optional `jsonschema` validator.
- **`tell-dot`:** Prefers direct Slack tools; optional bridge uses an already configured Codex CLI / Slack connection.
- **`english-learning`:** Python 3 collector (`scripts/collect.py`), optional image generation, authorized Notion connector, and private destination IDs in its profile.
- **`social-publish`:** Includes an offline Xiaohongshu preflight script (`scripts/check_xiaohongshu.py`; optional `--ocr` uses macOS Vision via `swift`).
- **`x-search`:** Python 3 and a SocialData API key (`SOCIALDATA_API_KEY` or macOS Keychain profile).
