---
name: google-flow
description: "Use Google Flow (video, images, storyboards, custom creative tools) and Google Flow Music (Lyria songs, remixes, stems, music videos, Spaces) through BrowserOS neo with verified login, credit, and download checks."
---

# Google Flow & Google Flow Music

Drive **Google Flow** (`https://flow.google.com/`) for AI video, images, storyboards, characters, and custom creative tools, and **Google Flow Music** (`https://www.flowmusic.app/`) for AI songs, conversational music production, audio remixes, stems, Veo music videos, and interactive Spaces.

## Routing and account safety

- Follow `agent-browser` and `browseros-neo`: operate inside **BrowserOS neo** using the user's authenticated profile in a task-owned tab (`tabs` action `"new"` or `browser.open(...)`).
- Never install or invoke unofficial Playwright/CDP scraper MCPs that automate consumer Google logins via `navigator.webdriver` workarounds, and never export cookies, credentials, or session storage.
- Never change billing, upgrade/cancel subscriptions, enable marketing/research opt-ins, or publish creations publicly unless the user explicitly asks.

## Preflight before generating

1. If `~/.config/personal-skills/profiles/google-flow/SKILL.md` exists, read it once for the authorized Google account and standing credit rules.
2. Open the target studio (`https://flow.google.com/` or `https://www.flowmusic.app/`) and check sign-in status:
   - In **Google Flow**, open `Account details` to confirm the active email, plan badge (`PRO` / `ULTRA` / Free), and current **Google Flow credits** balance + reset date. When multiple Google accounts are signed in, open the intended `/u/<N>/` index or use `Account details` -> `Switch account`.
   - In **Google Flow Music**, open `Settings menu` (or `https://www.flowmusic.app/settings`) to confirm the active email/handle, plan tier (`Free` / `Starter` / `Plus` / `Member`), and available **credits**. To switch Google accounts in Flow Music, use `Settings menu` -> `Log out` and sign back in — never click `Connect another Google account` unless the user wants to link accounts.
3. If the session is logged out, points to the wrong Google account, lands on an OAuth consent popup (`page_out_of_scope`), or triggers verification/captcha, stop and hand off to the user via `request_human_help` / `await_human_help`.
4. Confirm before running large, multi-output (`x2`–`x4`), or high-cost video/song generation batches so account credits are never spent unexpectedly.

## Google Flow workflow (`https://flow.google.com/`)

1. **Create or open a project**: Click `New project` (or open the named project requested by the user). Rename the project if helpful via its header title field.
2. **Navigate the workspace**:
   - **Left navigation**: `All media`, `Characters` (6 archetype starters plus prompt/upload consistency builder), `Scenes` (timeline/scene sequence builder), `Library` + `Create collection`, `Tools` (`My Tools`, `Community`, `Templates`), `Create tool`, and `Trash`.
   - **Right Flow Agent panel**: Conversational assistant (`What do you want to create?`), `Open session history`, and `Agent settings` (`Confirm before generating`: `Always` / `Never`, `Image defaults`, `Video defaults`).
3. **Configure model and parameters before prompting**:
   - **Video defaults** (`Agent settings` -> `Video defaults`): `Omni 1.2 Flash` (default), `Veo 3.1 - Lite` (plus lower-priority/ultra options and other active models shown in the radio list), aspect ratio (`16:9`, `9:16`), and number of outputs (`x1`–`x4`).
   - **Image generation** (`Settings trigger` inside the prompt box or `Agent settings` -> `Image defaults`): `Nano Banana 2.1` (default), `Nano Banana Pro`, `Nano Banana 2 Lite`, aspect ratio (`16:9`, `4:3`, `1:1`, `3:4`, `9:16`), thinking level (`Low`, `Medium`, `High`), and number of outputs (`x1`–`x4`).
   - **Inputs**: Add reference frames or visual ingredients via `Add ingredients to the prompt box` or `Add media menu`.
4. **Generate and verify**:
   - Check the displayed credit cost in the prompt settings popover before clicking `Start generation`.
   - Wait for the output card to settle using `waitForSelector` / `waitForText` rather than fixed sleep loops.
   - Download finished media through BrowserOS neo `download` to the user's requested path and verify the saved file exists and is non-empty before reporting success.
5. **Privacy awareness**: If the user needs prompts excluded from product-improvement review, check `More options` -> `Help improve Flow` (and `Account details` -> `Visible watermarking` if clean exports are needed) and confirm the user's preference before changing settings.

## Reference-video remake workflow (Depth Map + Omni 1.2 Flash)

Use the packaged helper [scripts/flow_video_prep.py](scripts/flow_video_prep.py) (`uv run` + `ffmpeg`/`ffprobe`) together with **BrowserOS neo** to remake viral/reference videos into new character casts without tripping Flow's live-action/copyright moderation or installing unofficial scraper CLIs.

1. **Inspect and trim to `<= 15s`**:
   - Run `python3 scripts/flow_video_prep.py probe <input.mp4>` to verify resolution, FPS, audio, and whether `duration_sec <= 15` (`fits_flow_15s`). Trim longer clips into `<= 15s` segments with `prep` first.
2. **Convert real-person / copyrighted references to grayscale depth video locally**:
   - Run `uv run scripts/flow_video_prep.py depth <input.mp4> -o <depth.mp4>` (runs `Depth-Anything-V2` on Apple Silicon MPS / CUDA / CPU and outputs silent H.264 `yuv420p` with near = bright/white, far = dark/black).
   - Depth video strips recognizable faces, textures, and watermarks while preserving blocking, pacing, and camera motion so Flow moderation passes. (For exact 1:1 facial micro-expression or finger fidelity rather than blocking/camera transfer, note depth maps omit fine expression/finger detail.)
3. **Prepare single-character sheets**:
   - Generate or upload **individual** character turnaround/reference images (e.g., `Nano Banana 2.1` inside the same Flow project costs `0` video credits; approve any first-time upload rights dialog in the UI if prompted).
   - **Never** attach a multi-person composite group image alongside the depth video — it locks camera framing to a single frontal angle and suppresses scene cuts.
4. **Attach media carefully in Flow (`+` asset picker)**:
   - Upload the depth MP4 and character images via **BrowserOS neo**'s native `upload` tool (never `gflow-cli` or unofficial internal endpoints).
   - Open `+`, switch to the **`Videos`** tab **first** to attach `<depth.mp4>`, and **verify the prompt footer displays the video duration (e.g., `15s` / `15 秒`)** before switching to **`Images`** to select single-character sheets. (Generated images push videos out of "Recent", and submitting without the video attached silently runs an `8s` image-only generation.)
5. **Prompting rules for clean character swaps**:
   - Bind replacements by **clothing/visual features**, never screen position (`left`/`right` breaks as soon as actors cross).
   - Explicitly state that character reference images lock **face/appearance and outfit only**, while motion, framing, cuts, lighting, and stage follow the reference video.
   - Keep prompts concise and direct; heavy stacks of negative rules ("must", "strictly forbid") increase validation failures and stiffen motion.
6. **Draft-first cost gate, audio remux, and QA contact sheet**:
   - Check and report the displayed credit cost and remaining Flow credits before submitting. Run a **`360p` (`x1`, ~20 credits for 15s)** draft first.
   - Download the result via BrowserOS neo, restore original audio with `python3 scripts/flow_video_prep.py remux --video <gen.mp4> --audio-from <orig.mp4> -o <final.mp4>`, and render a 6-frame side-by-side comparison sheet with `python3 scripts/flow_video_prep.py compare --original <orig.mp4> --generated <final.mp4> -o <compare.png>`.
   - Visually inspect `<compare.png>` before confirming a **`720p` (60 credits)** re-render or **`1080p` download upscale (+5 credits)**.
7. **Cross-harness fallback**: If the current agent session lacks direct `browseros-neo` MCP tools, delegate the BrowserOS neo UI upload, generation, and download steps to an enabled harness that has `browseros-neo` connected (or connect `browseros-neo` MCP first) rather than falling back to non-BrowserOS scrapers.

## Google Flow Music workflow (`https://www.flowmusic.app/`)

1. **Start or resume a session**: Click `New session` (`https://www.flowmusic.app/session`) or open an existing session/song from `Songs`, `Playlists`, `Music videos`, `Spaces`, or `Projects`.
2. **Choose creation mode**:
   - **Conversational Producer chat** (main pane): Type a prompt in `Chat message` (or use `Voice mode`), attach references with `Add audio or image` (`Recording`, `Audio` up to 40 MB, or `Image`), and tune `Chat settings`:
     - `Instrument`: `Lyria 3.5` (default flagship) or `Lyria 3 Pro` (legacy).
     - `Ghostwriter`: `Standard` or `Pro` (lyric composition).
     - `Producer`: `Standard` or `Fast` (assistant reasoning speed).
   - **Direct Compose panel** (`Open compose panel`): Fill `Lyrics` (or toggle `Instrumental`), `Sound` (or toggle `Advanced`), and `Details`, then submit `Generate`.
3. **Iterate, transform, and export**:
   - Ask the Producer conversationally to edit specific sections (intro/verse/bridge/solo), extend a track, remix uploaded audio, or split stems.
   - Create accompanying AI music videos (`https://www.flowmusic.app/library/videos`) or interactive audio mini-apps/plugins (`https://www.flowmusic.app/library/spaces`).
   - Download tracks in `MP3`, `WAV`, `M4A`, or separated stems via the song options/download controls, and verify each downloaded file on disk.
   - Note that `Turntable` (`https://www.flowmusic.app/turntable`) offers A/B sample voting for personalization and earning bonus credits (only participate if the user asks).
4. **Privacy awareness**: Check `https://www.flowmusic.app/settings` for `Moderate lyrics`, `Visible watermarking`, `After Hours` (free background edit suggestions), and `Help improve Google Flow Music` when privacy constraints apply.

## Tab hygiene

- Record tabs created during the task and close all task-created tabs at completion (using `tabs` / `page.close()`), unless a tab is intentionally kept open for a pending human handoff or explicit user inspection.

## Local owner context

If `~/.config/personal-skills/profiles/google-flow/SKILL.md` exists, read it once at the start of the task for the owner's BrowserOS neo profile, authorized account, and standing credit/privacy preferences. Keep that profile strictly local and out of Git; verify live credit counts and available models directly in the UI on every run.
