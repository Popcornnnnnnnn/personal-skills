---
name: walkthrough-video
description: Build narrated, subtitled 1080p walkthrough and explainer videos locally with Python, Pillow, neural TTS, and FFmpeg. Use when the user asks for a walkthrough video, animated concept explainer, or visual slide-by-slide video explanation.
---

# Walkthrough video

Turn concepts, guides, or workflows into clear, narrated 1080p MP4 walkthrough videos with verified layout, natural voiceover, and clean single-layer subtitles. Put the explanation inside the video scenes rather than repeating a long text essay in chat.

## Workspace and output hygiene

- Write scratch scripts, raw audio clips, preview PNGs, and backup subtitle files inside a dedicated scratch directory (such as the active conversation's `scratch/` folder or `/tmp/<topic>-video/`), never at a workspace or repository root.
- Write the final `.mp4` to the user-requested destination or the active artifact directory. On macOS, **always** include a copy-pasteable IINA launch command in the delivery reply alongside the clickable file link:
  ```bash
  open -a IINA "<absolute-path-to-video.mp4>"
  ```

## 1. Storyboard and spoken script

- Break the topic into short, focused scenes (typically 12–20 seconds each) with one core visual idea per scene: side-by-side comparison, 3-column mental model, layered stack, budget/progress meter, step-by-step pipeline, or 2x2 summary grid.
- Write conversational spoken sentences rather than stiff prose. Spell out symbols phonetically in the TTS input only (`~/.gemini` -> "dot-gemini", `/learn` -> "slash learn", `MCP` -> "M-C-P") while keeping clean technical tokens (`~/.gemini`, `/learn`, `MCP`) in the on-screen subtitles.

## 2. Natural neural voiceover and timing

- Prefer a conversational neural TTS voice (for example `edge-tts` with `en-US-AndrewMultilingualNeural` via `uv run --with edge-tts`, or an explicitly configured neural TTS provider) over robotic built-in OS `say` voices. Fall back to `say` only when offline and no neural engine is cached, and tell the user if falling back.
- Synthesize scenes **sequentially** with a short pause, timeout, and retry rather than firing many concurrent WebSocket requests at once (which triggers empty-audio rate limits). Always write TTS output to a `.tmp` file first and `os.replace()` only after the stream completes cleanly, so a mid-stream timeout never leaves a truncated clip that looks cached on retry.
- Listen to or read back synthesized clips to verify complete sentences and pronunciation before video encoding.
- Normalize each clip to 44.1 kHz stereo WAV with a short lead-in and tail breath (for example `adelay=400|400,apad=pad_dur=0.65`), measure exact duration with `ffprobe`, and detect exact clause pause boundaries with `ffmpeg -nostdin -i <clip.wav> -af silencedetect=noise=-35dB:d=0.16 -f null -`.

## 3. Single-layer subtitle rule

- **Never combine burned-in subtitles with an embedded `mov_text` subtitle stream or a same-basename `.srt` file in the same directory.** Desktop players such as IINA and VLC automatically render embedded or sidecar `.srt` tracks in large default text directly on top of burned-in captions.
- Default to **one** clean, high-contrast phrase-by-phrase burned-in subtitle pill near the bottom of the 1920x1080 canvas, synced to the `silencedetect` clause intervals. Keep any `.srt` backup inside `scratch/` under a non-matching filename unless the user explicitly asks for soft-only subtitles.

## 4. Visual layout and mandatory `--preview` check

- Design on a 1920x1080 grid with clear vertical zones: header badge + title (`y = 40..200`), main visual stage (`y = 235..905`), synced subtitle pill (`y = 925..1020`), and timeline bar (`y = 1038..1050`).
- Do **not** rely on system prose fonts (such as `HelveticaNeue.ttc`) for Unicode symbols (`✓`, `✕`, `→`, `▲`), which often render as missing-glyph boxes (`□`). Draw checkmarks, crosses, and arrows as crisp vector lines/polygons in Pillow.
- Before encoding the full video, run a `--preview` mode that saves one midpoint PNG per scene and visually inspect every PNG to verify contrast, wrapping, icon geometry, and zero overlapping borders or labels.

## 5. Deadlock-free FFmpeg encode and verification

- Stream raw `rgb24` frames into `ffmpeg` with `-nostdin` and **only** video + audio inputs (`-c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p -profile:v high -c:a aac -b:a 192k -shortest -movflags +faststart`). Never mux `-c:s mov_text` on the same `rawvideo` stdin pipe with `-shortest`, which can deadlock FFmpeg's muxer at EOF; if soft-only subtitles are requested, mux them in a second `-nostdin -c copy` pass.
- Verify the finished `.mp4` with `ffprobe` (confirm `h264` video, `aac` audio, expected duration, and absence of unintended duplicate subtitle streams) before reporting completion.

## 6. Continuous feedback learning and local owner context

- If `~/.config/personal-skills/profiles/walkthrough-video/SKILL.md` exists, read it once at the start of the task (and before handling follow-up video feedback) for local owner defaults, player preferences, and standing skill-update rules. Keep that profile local and owner-only.
- When the user gives a new reusable requirement, preference, correction, or quality judgment about walkthrough videos (such as voice style, pacing, visual layout, subtitle formatting, encoding reliability, or delivery handoff), separate reusable video-making principles from one-off topic facts or temporary shortcuts so single-session exceptions never cause memory drift.
- When the local owner profile authorizes automatic updates to `walkthrough-video`, fold the verified reusable lesson directly into the relevant section of `SKILL.md` without creating duplicates, run the repository release check, and sync in the same task. Without an owner profile grant, present a short diff proposal and wait for approval before modifying skill files.
