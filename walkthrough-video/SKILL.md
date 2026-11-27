---
name: walkthrough-video
description: Build narrated, subtitled 1080p walkthrough and explainer videos locally with Python, Pillow, neural TTS, and FFmpeg. Use when the user asks for a walkthrough video, animated concept explainer, or visual slide-by-slide video explanation.
---

# Walkthrough video

Turn concepts, guides, or workflows into clear, narrated 1080p MP4 walkthrough videos with verified layout, natural voiceover, and clean single-layer subtitles. Put the explanation inside the video scenes rather than repeating a long text essay in chat.

## Workspace and output hygiene

- **Central output library**: Write the final `.mp4` directly to the canonical video folder configured in the local owner profile (or `~/Movies/Walkthroughs/` on macOS—never drop loose `.mp4` files at `~/Movies/` root—unless the user explicitly specifies another path for the task). Prefer lowercase `kebab-case` filenames (`<topic>.mp4`) by topic so the library stays publish-ready.
- **Keep one unified video per topic**: When the user asks to expand, clarify, or refine part of the same topic in follow-up feedback, weave the new or revised scenes directly into that single authoritative `.mp4` in logical narrative order (renumbering chapters and rebuilding the single timeline/finale, and removing obsolete fragment `.mp4` files). Produce separate videos only when the user explicitly requests separate episodes or distinct topics.
- **Retain scratch while iterating; clean up after explicit acceptance**: Store intermediate outputs (render scripts, raw TTS clips, padded WAVs, silence metadata, preview PNGs, backup `.srt` files, and temporary preview copies) inside a dedicated scratch directory while iterating so revisions stay fast, never at a workspace root. **Do not delete intermediate files prematurely**; once the user **explicitly accepts** the video, remove all intermediate scratch outputs and temporary copies, then verify that the final `.mp4` in the central output folder remains intact.
- Deliver the finished video with a direct file link (or inline media embed when supported by the chat host); do **not** include copy-pasteable local player launch commands (such as `open -a IINA ...`) unless the user explicitly asks.

## 1. 3Blue1Brown visual pedagogy & motion-first design

- **Know when a walkthrough video fits the topic (*Medium Fit*)**: Walkthrough videos shine for **concrete mechanisms, algorithms, system architectures, and step-by-step mental models**. For **broad multi-topic research surveys or dense strategic reports**, either narrow the video to one concrete mechanism/decision or suggest a higher-bandwidth format (an interactive visual explorer, a longer audio deep-dive, or structured Q&A paired with a reference doc) rather than cramming the whole report into a short video or stripping away its substance.
- **Default to a 3Blue1Brown visual aesthetic**: Favor a deep dark math-slate canvas (`#060A14`–`#090D1A` with subtle dot-grid coordinates when helpful) and clean geometric diagrams, vectors, node-edge graphs, and morphing shapes over boxed SaaS dashboard cards or PowerPoint slide decks.
- **Depth through structure, never clutter or shallowness (*Substantive Pacing Rule*)**: Teach one clean narrative spine (`question -> concrete running example -> mechanism or failure -> synthesis -> takeaway`) and stick to **one primary taxonomy** (never stack 3–4 competing numbering schemes), **without stripping away real substance, concrete mechanisms, real-world examples, or key evidence just to stay short or hit an arbitrary stat limit**. Instead, control *density per beat*: give each meaningful idea, real example, or key number its own dedicated visual beat and scale runtime naturally (e.g., 5–8+ minutes for deep topics) instead of cramming 3–4 facts into one 8-second line or thinning the video into slogans. Leave exhaustive tables, secondary citations, and raw data appendices in companion documents.
- **Standalone self-containment (zero orphan references)**: Every walkthrough must make complete sense on its own without assuming the viewer read an earlier document or draft. Start from the viewer's real question, visually introduce any concrete running example before citing its numbers, and never drop undefined internal labels (such as unintroduced section numbers, shorthand labels, or companion-document cross-references).
- **One evolving visual world per scene (no dark-mode PowerPoint)**: Never cram multiple unrelated mini-charts or boxed bullet lists onto one stage or reset layouts mid-scene. Evolve one continuous geometric object, balance, flow, or coordinate system across beats—where elements visibly transform, compress, collide, or carry animated packets—so motion shows *cause and effect* rather than merely fading static boxes in.
- **Intuition before jargon (*Show Evolution, Not Static States*)**: Introduce the concrete visual mechanism, tension, or state transformation *first* so the viewer sees *why* it works before naming the formal term. Place short labels right beside the object they describe at the exact moment the voice names it (*Mayer's Spatial & Temporal Contiguity*).
- **Strict semantic color continuity**: Assign each core concept one restrained accent color (such as sky blue `#58C4DD` / `#38BDF8`, focal gold `#FBBF24`, emerald `#34D399`, coral `#F87171`, lavender `#A78BFA`) and keep that exact color identity across every scene in the video.
- **Zero prose paragraphs on canvas (*Mayer's Redundancy Principle*)**: The voiceover and bottom subtitle bar already carry full sentences. Never place paragraph text or multi-sentence bullet cards on the visual stage. Keep total on-screen canvas text under **~10–15 words at any moment** (short 1–4 word labels, hero keywords, or single-line terminal/diff tokens) and replace bulky top slide titles with a compact corner chapter pill (`02 / 06 • TOPIC`).
- **Spring physics, soft spotlight signaling, and continuous flow**:
  - **Damped harmonic `spring()` motion**: Drive entrances, scaling, and layer swaps with damped spring curves (`zeta ~ 0.72–0.76`) rather than flat linear or cubic slides.
  - **Radial spotlight halos (*Signaling Principle*)**: Composite a soft Gaussian-blurred `RGBA` radial glow behind the active node while dimming inactive elements to ~25–35% opacity so the viewer's eye always knows where to look.
  - **Live micro-transitions & packet streams**: Animate directional packet dots flowing along connectors, slots physically swapping, values scrubbing/redacting live, and gauges filling or resetting on exact spoken beats (~2.5–4s).
  - **Pass the Mute Fast-Forward Test**: Each scene should prove one clear idea visually so a viewer watching on mute at 2x speed can still follow the story arc.
- **Conversational pacing over rigid beat grids**: Vary sentence rhythm and allow breathing room after turning points instead of packing 3–4 facts into every spoken line.
- **Phonetic TTS vs. clean display tokens**: Write natural conversational spoken sentences. Spell out symbols phonetically in the TTS input only (`~/.gemini` -> "dot-gemini", `/learn` -> "slash learn", `MCP` -> "M-C-P") while keeping clean technical tokens (`~/.gemini`, `/learn`, `MCP`) on screen and in subtitles.

## 2. Natural neural voiceover and timing

- Prefer a conversational neural TTS voice (for example `edge-tts` with `en-US-AndrewMultilingualNeural` via `uv run --with edge-tts`, or an explicitly configured neural TTS provider) over robotic built-in OS `say` voices. Fall back to `say` only when offline and no neural engine is cached, and tell the user if falling back.
- Synthesize scenes **sequentially** with a short pause, timeout, and retry rather than firing many concurrent WebSocket requests at once (which triggers empty-audio rate limits). Always write TTS output to a `.tmp` file first and `os.replace()` only after the stream completes cleanly, so a mid-stream timeout never leaves a truncated clip that looks cached on retry.
- Listen to or read back synthesized clips to verify complete sentences and pronunciation before video encoding.
- Normalize each clip to 44.1 kHz stereo WAV with a short lead-in and tail breath (for example `adelay=400|400,apad=pad_dur=0.65`), measure exact duration with `ffprobe`, and detect exact clause pause boundaries with `ffmpeg -nostdin -i <clip.wav> -af silencedetect=noise=-35dB:d=0.16 -f null -`.

## 3. Single-layer subtitle rule

- **Never combine burned-in subtitles with an embedded `mov_text` subtitle stream or a same-basename `.srt` file in the same directory.** Desktop players such as IINA and VLC automatically render embedded or sidecar `.srt` tracks in large default text directly on top of burned-in captions.
- Default to **one** clean, high-contrast phrase-by-phrase burned-in subtitle pill near the bottom of the 1920x1080 canvas, synced to the `silencedetect` clause intervals. Keep any `.srt` backup inside `scratch/` under a non-matching filename unless the user explicitly asks for soft-only subtitles.

## 4. Visual layout and mandatory `--preview` check

- Design on a 1920x1080 grid with clear vertical zones: compact corner chapter pill (`y = 40..85`), full-bleed animated stage (`y = 130..900`), synced subtitle pill (`y = 925..1020`), and timeline bar (`y = 1038..1050`).
- Do **not** rely on system prose fonts (such as `HelveticaNeue.ttc`) for Unicode symbols (`✓`, `✕`, `→`, `▲`), which often render as missing-glyph boxes (`□`). Draw checkmarks, crosses, and arrows as crisp vector lines/polygons in Pillow.
- Before encoding the full video, run a `--preview` mode that saves early, mid, and late beat PNGs per scene and visually inspect every preview frame to verify geometry and contrast (low word density, color contrast, crisp vector icon geometry, and zero overlapping elements) alongside **clarity with real substance** (zero orphan references, single-focus composition free of multi-widget dashboard clutter, visible state transformation from early to late beats, no multi-fact crowding per beat, and enough concrete examples, numbers, and mechanisms that the video genuinely teaches rather than feeling shallow).

## 5. Deadlock-free FFmpeg encode and verification

- Stream raw `rgb24` frames into `ffmpeg` with `-nostdin` and **only** video + audio inputs (`-c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p -profile:v high -c:a aac -b:a 192k -shortest -movflags +faststart`). Never mux `-c:s mov_text` on the same `rawvideo` stdin pipe with `-shortest`, which can deadlock FFmpeg's muxer at EOF; if soft-only subtitles are requested, mux them in a second `-nostdin -c copy` pass.
- Verify the finished `.mp4` with `ffprobe` (confirm `h264` video, `aac` audio, expected duration, and absence of unintended duplicate subtitle streams) before reporting completion.

## 6. Continuous feedback learning and local owner context

- If `~/.config/personal-skills/profiles/walkthrough-video/SKILL.md` exists, read it once at the start of the task (and before handling follow-up video feedback) for local owner defaults, player preferences, and standing skill-update rules. Keep that profile local and owner-only.
- When the user gives a new reusable requirement, preference, correction, or quality judgment about walkthrough videos (such as voice style, pacing, visual layout, subtitle formatting, encoding reliability, or delivery handoff), separate reusable video-making principles from one-off topic facts or temporary shortcuts so single-session exceptions never cause memory drift.
- When the local owner profile authorizes automatic updates to `walkthrough-video`, fold the verified reusable lesson directly into the relevant section of `SKILL.md` without creating duplicates, run the repository release check, and sync in the same task. Without an owner profile grant, present a short diff proposal and wait for approval before modifying skill files.
