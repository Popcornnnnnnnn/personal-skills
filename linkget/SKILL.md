---
name: linkget
description: "Download offline article archives (X Articles, WeChat, Toutiao, Zhihu, and public web pages) with Markdown, standalone HTML, metadata, and local assets, download social media photos/videos/audio, or extract transcripts/keyframes via the local linkget CLI."
---

# Using `linkget`

Always pass `--non-interactive --json` (or `--stdout` on `read`) and wrap every URL in single quotes (`'...'`) so shell metacharacters (`&`, `?`, `;`) are not expanded. Many agent shells attach a PTY where interactive prompts can block without `--non-interactive`. For native tool calls over stdio JSON-RPC 2.0, run `linkget mcp` (`inspect_url`, `download`, `batch_download`, `list_tasks`, `task_status`, `retry_task`, `clean_stages`, `get_config`).

## 1. Environment & URL Preflight

```sh
linkget doctor --non-interactive --json
linkget inspect 'URL_OR_PATH' --no-network --json
```

`inspect` performs zero downloads and creates no task journals. Check:
- `ok`, `supported`, `site`, `engine`, `canonical_url`
- `supports_article_download`, `supports_article_photos`, `supports_read`, `effective_audio_mode`
- `destination_preview`, `destination_error`
- `tools_missing`, `session_state`, `login_required`

Pass `--as auto|photo|video|article` (or `--article` / `--video`) to `inspect` when previewing a specific save mode, or omit `--no-network` to probe remote metadata on `yt-dlp` routes.

## 2. Download Offline Article Archives & X Article Photos

Supported automatically: X Articles (`/<user>/article/ID` and auto-promoted `/status/ID`), WeChat (`mp.weixin.qq.com`), Toutiao (`/article/`), Zhihu (`zhuanlan.zhihu.com`), Raspberry Pi, and public HTTP(S) web articles. Passing `--as article` (or `--article`) forces an X `/status/ID` post into article mode upfront; `--no-assets` skips downloading embedded images and videos.

```sh
# Download an X Article or public web page into a timestamped subfolder under DIR
linkget 'https://x.com/USER/status/ID' --folder ./articles --non-interactive --json
linkget 'https://example.com/post' --as article --folder ./articles --non-interactive --json
linkget 'https://example.com/post' --no-assets --folder ./articles --non-interactive --json

# Render an X Article offline to a PNG and import into Apple Photos (macOS)
linkget 'https://x.com/USER/article/ID' --photos --non-interactive --json
linkget 'https://x.com/USER/status/ID' --as article --photos --date-now --non-interactive --json

# Or configure defaults once
linkget config --article-folder ~/Articles
linkget config --x-article-photos      # or --no-x-article-photos
linkget config --clear-article-folder
```

**Output bundle (`YYYY-MM-DD-<site-or-handle>-<title-slug>/`, non-overwriting):**
- `article.md` — YAML frontmatter + full Markdown with local `assets/...` links
- `article.html` — standalone responsive light/dark reader page (zero external scripts)
- `content.txt` — plain text
- `content.json` — structured metadata, engagement metrics, author info, and SHA-256 asset manifest
- `assets/` — downloaded cover image (`name=orig` on X), inline images/videos, video posters, and author avatar
- `source/` — `x-article.json` (raw GraphQL payload, zero cookies) or `original.html`

**Constraints & JSON output:**
- Non-X article downloads require a folder (`--folder`, `--article-folder`, `config --article-folder`, or global folder default) and reject `--photos`, `--date-now`, `--live-photos`, `--audio`, `--clip`, `--max-duration`, and `--max-size`.
- X Articles accept `--photos` (and `--date-now` when Photos rendering applies), unless `--no-assets` is set. Explicit `--folder`, `--article-folder`, or `--no-assets` overrides `x_article_photos` back to folder archiving.
- Full X Article `content_state` requires saved `x.com` cookies (`linkget auth x`) or a logged-in BrowserOS Neo / Chrome session; guest access exposes only a preview and returns `login_required`.
- Success JSON includes `article_folder`, `title`, `author`, `assets_downloaded`, and `assets_failed` (or `article_photo` and `article_png` for X Article Photos runs).

## 3. Download Media, Audio & Batches

```sh
# Video/image/article mode overrides (--as auto|photo|video|article, or --video / --photos / --folder / --article-folder)
linkget 'URL' --as video --folder ./downloads --non-interactive --json
linkget 'URL' --folder ./downloads --non-interactive --json

# Audio-only extraction / music track conversion
linkget 'URL' --audio --audio-format mp3 --folder ./music --non-interactive --json

# Clipping & safety caps
linkget 'URL' --clip 0:30-2:00 --max-duration 10m --max-size 100MB --folder ./clips --non-interactive --json

# Concurrent batch (supports mixed URLs; per-item isolation, optional per-run --article-folder)
linkget batch 'URL1' 'URL2' --folder ./downloads --article-folder ./articles --jobs 3 --non-interactive --json
```

Never combine `--photos`, `--date-now`, or `--live-photos` with `--audio` or music-only URLs (`music.youtube.com/watch`, `bilibili.com/audio/au...`, SoundCloud tracks, Bandcamp `/track/`).

## 4. Extract Text, Transcripts & Keyframes (`linkget read`)

```sh
# Foreground JSON or Markdown/plain-text directly to stdout
linkget read 'URL_OR_PATH' --foreground --json
linkget read 'URL_OR_PATH' --stdout --stdout-format md --non-interactive

# Video keyframes (+ optional macOS Vision OCR)
linkget read 'VIDEO_URL_OR_PATH' --frames --max-frames 12 --frame-ocr --foreground --json

# Article reads also save article.html, source/, and local assets/ (skip assets with --no-assets)
linkget read 'https://x.com/USER/status/ID' --folder ./x-read --foreground --json

# Background submit, wait, and fetch
linkget read 'URL_OR_PATH' --json
linkget read wait TASK_ID --timeout 300 --json
linkget read show TASK_ID --format md
```

## 5. Task Management & Guardrails

```sh
linkget tasks --json
linkget retry TASK_ID --json
linkget recover TASK_ID --json
linkget clean --older-than 7d --json          # dry-run preview; pass --apply only to remove old completed stages
```

- **Exit codes:** `0` succeeded, `1` failure (`error` object emitted with `--json`), `2` invalid CLI syntax, `124` `read wait` timeout, `130` cancelled.
- **Safety boundaries:** Never scrape cookies manually, automate logins, or bypass CAPTCHAs; surface `error.next_step` when `login_required` or `website_check` occurs. Never run `rm -rf` on temporary staging directories — use `linkget clean`.
