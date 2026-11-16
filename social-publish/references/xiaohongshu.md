# RedNote (Xiaohongshu / 小红书)

RedNote is visual-first, search-driven, and heavily enforced against both browser automation and off-platform lead generation. Automate everything locally up to the self-contained folder; keep upload, scheduling, replies, and account actions manual.

## Account and automation boundaries

- **Never connect auto-posting or engagement bots**: Xiaohongshu offers no individual creator publishing API (`write_notes` on `open.xiaohongshu.com` is enterprise-only). Browser clickers (`Event.isTrusted === false`), synthetic `.fill()` paste scripts, third-party MCP uploaders, and reverse-engineered `x-s` / `x-t` signers trigger error `300012`, silent distribution throttling (`限流`), or account restrictions. One real-name ID (`实名认证`) gets only one Pugongying (`蒲公英`) monetization slot—never risk it with automation.
- **Keep topic research offline-first**: Source ideas from local code, changelogs, commit history, reading notes, and real photos. If the user explicitly authorizes a live `xiaohongshu.com` keyword or card-title check in an interactive browser, keep it passive and bounded (single tab, `<=2` searches per run, `<=3` pages, `>=15 min` gap, stopping immediately on any login modal, slider verification, or `300012` warning). Never replay cookies in scripts, strip `xsec_token` parameters from `/explore/<id>` URLs, or monkey-patch `window.fetch` / `XMLHttpRequest` on public search pages.
- **Preserve network region (`IP属地`)**: When operating a Mainland-based account, route `xiaohongshu.com` and `xhscdn.com` directly (`Rule` mode) rather than through an overseas proxy (`Global` mode), which flips the public `IP属地` badge and triggers cross-region risk checks. Use `xiaohongshu.com` / `creator.xiaohongshu.com` rather than `rednote.com` links that proxy rules may route abroad.

## Pillars and conversion model

Choose one pillar per note so commercial cues do not contaminate educational or personal posts:

1. **Indie build (`indie-build`)**: Lead with one recognizable pain point, constraint, before/after workflow, or build lesson. Convert via **"Name, Don't Link"**—show a distinct, searchable product or project name and real UI clearly on screen so interested readers search the name themselves or join an official profile-mounted Xiaohongshu Fan Group (`群聊`).
2. **Tech / AI explainer (`tech-explainer`)**: Break down one AI workflow, architecture, or mental model visually without pitching a product, price, or download. Pure non-promotional explainers are the only safe candidates for standard Shutiao (`薯条`) content heating.
3. **Personal life (`personal-life`)**: Authentic running, cycling, or everyday moments built from real camera shots or Live Photos (`实况图`) and concrete personal details, with no synthetic imagery or sales angle.

## Off-platform diversion (`导流违规`) rules

Xiaohongshu scans **both prose fields and rendered slide/video frames via OCR** for external traffic diversion. Keep every title, caption, hashtag, and visual slide free of:

- External URLs (`http://`, `https://`, `www.`), repo paths (`github.com/...`), or external web domains (`.com`, `.io`, `.ai`, `.app`, `.dev`, etc.). Write plain brand or tool names (`GitHub`, `Claude`) instead of domains (`github.com`, `claude.ai`).
- CLI install or download commands (`brew install ...`, `npm i ...`, `pip install ...`, `git clone ...`, `curl ... | sh`), including inside terminal screenshots or browser address bars.
- QR codes, barcodes, third-party watermarks, personal contact IDs, email addresses, or WeChat/DM diversion hooks (`加V`, `私v`, `vx`, `绿泡泡`, `地球号`, `私信发链接`, `评论区扣1领`).
- Platform-scraping or evasion combinations (such as pairing `小红书` with `无水印下载`, `爬虫`, `自动发帖`, `绕过审核`, or `去除AI标识`).

## Mandatory AIGC disclosure (`自主声明`)

Under China's `《人工智能生成合成内容标识办法》` and Xiaohongshu's `AI创作声明` policy:

- **Not required**: Real UI screenshots, clean terminal captures, code-rendered HTML/CSS diagram cards, real camera/iPhone photos, Live Photos, and human-edited prose are not synthetic media and need no AI label.
- **Required**: Any AI-generated image/illustration, AI avatar/digital human, synthetic TTS voiceover, or heavily AI-synthesized scene **must** check `AI创作声明` (`内容含AI合成元素`) when publishing.

Record the exact decision and basis in `POST.md` and `CHECKLIST.md`. Never strip C2PA/EXIF metadata or advise hiding synthetic media: honest disclosure does not penalize strong content, whereas undeclared synthetic media triggers forced labeling **plus distribution throttling (`限制分发`)**.

## Writing style and limits

- **Title (`标题`)**: `<=20` UTF-16 characters (`creator.xiaohongshu.com` counts JavaScript `.length`: 1 CJK char = 1, 1 ASCII char/space = 1, surrogate-pair emoji = 2+). Front-load the searchable problem, concrete number, or human hook in the first 10–15 characters because mobile two-column cards truncate around ~16 characters.
- **Body (`正文`)**: `<=1,000` UTF-16 characters for standard image/video notes, including `#话题` tags at the bottom. Break lines every 1–3 sentences for mobile scanning.
- **Hashtags (`#话题`)**: Place 3–5 specific tags at the end of the body (for example `#独立开发 #AI工具 #编程日常`). Avoid tag stuffing.
- **Remove AI tells**: Apply `humanizer` principles to Chinese and English prose alike. Cut stock LLM openers and corporate clichés (`在当今时代`, `众所周知`, `底层逻辑`, `赋能`, `抓手`, `闭环`, `"不是X，而是Y"` / `"不仅…更是…"`, dramatic one-line closers, and emoji-per-line bullet walls). Write in plain, concrete first-person prose grounded in verified facts.

## Visuals and media

- **Image carousels (`carousel`)**: Default to **3:4 vertical** (`1242x1660` or `1080x1440`; `900x1200` minimum) so dual-column waterfall cards display without cropping. Upload `1–18` images (typically 4–9 slides: `01-cover` with one clear focal visual and `<=10–12` large words inside central safe margins, followed by one idea per slide). Frame desktop screenshots onto `3:4` cards with readable zoom rather than uploading raw `16:9` captures; crop or mask any visible browser URL bars.
- **Short vertical video (`video`)**: Default to **9:16 vertical** (`1080x1920`), roughly **35–60 seconds** for focused explainers, with clean captions inside vertical safe margins and music or real voiceover. Do not upload raw `16:9` desktop walkthroughs with synthetic TTS; either build a native `9:16` music-and-captions cut or explicitly mark synthetic voiceover for `AI创作声明`. Supply a `3:4` cover (or keep cover text inside the central `3:4` crop of `9:16`) for two-column feed previews.
- **Live Photos (`live-photo`)**: Keep original still + motion pairs intact for running, cycling, or life posts and specify **Xiaohongshu mobile app** upload—desktop `creator.xiaohongshu.com` flattens Live Photos into static images.

## Scheduling, growth, and monetization guardrails

- **Manual last mile**: Drag ready carousel/video bundles into `creator.xiaohongshu.com` and use official **Scheduled Publishing (`定时发布`, ~1 hour to 14 days ahead)**—for example 15–20 minutes before `07:30`, `12:00`, or `20:00` local windows to absorb review queue jitter. Use the mobile app when Live Photos or native workout stickers matter.
- **Zero engagement pods or boost scripts**: Never use `互赞群` or rapid zero-dwell-time likes (`秒赞`), which trigger anti-cheat view caps and jeopardize Pugongying (`蒲公英`, `pgy.xiaohongshu.com`) eligibility (`>=1,000` followers, real-name ID, clean 30-day violation record).
- **Shutiao (`薯条`) commercial rule**: Standard `薯条` content heating (`内容加热`) rejects notes with commercial or product-promotion cues (`营销属性无法推广`—pricing, store pitches, app promotion). Mark `Shutiao eligible: No` on `indie-build` product posts, and consider small manual Shutiao tests only on pure `tech-explainer` or non-commercial notes that already beat strong organic CTR/save benchmarks.

## Package

Use `xiaohongshu/` (or `xiaohongshu/<note-slug>/` in a multi-note batch) with:

- `POST.md`: structured exactly as:
  - `# Metadata` bullet list: `Pillar` (`indie-build` | `tech-explainer` | `personal-life`), `Carrier` (`carousel` | `video` | `live-photo`), `Publish channel` (`creator.xiaohongshu.com` | `Mobile app`), `AIGC disclosure` (`Required — ...` | `Not required — ...`), `Shutiao eligible` (`Yes — ...` | `No — ...`), `Suggested schedule`, and `Conversion path` (`None` or searchable name / profile `群聊`).
  - `## Title`: exact single-line primary title (`<=20` UTF-16 chars, raw text without counter annotations).
  - `## Title options`: optional 1–2 backup titles (`<=20` UTF-16 chars each).
  - `## Body`: exact caption prose plus 3–5 trailing `#话题` tags (`<=1,000` UTF-16 chars total).
  - `## Assets`: ordered list of slide/video files, pixel dimensions, and on-screen text summary.
- `CHECKLIST.md`: UTF-16 character counts, prose + slide OCR anti-diversion result, anti-AI-slop pass, `AI创作声明` checkbox action, aspect-ratio/cover/Live-Photo check, Shutiao eligibility note, and manual upload/schedule steps.
- `assets/`: self-contained ordered media (`01-cover.png`, `02-...`, or `video.mp4` + `cover.png`).

Run `python3 scripts/check_xiaohongshu.py <package-dir>` (add `--ocr` on macOS after rendering slides, or `--copy-only` while iterating on draft text before rendering assets) and resolve all errors before reporting readiness.

## Current first-party references

- Creator Service Platform (composer, analytics, 14-day `定时发布`): https://creator.xiaohongshu.com/
- Pugongying creator monetization platform (`蒲公英`): https://pgy.xiaohongshu.com/
- Open Platform API scope (`open.xiaohongshu.com`): https://open.xiaohongshu.com/
- Agreements and Community Guidelines (`协议与社区公约`): https://agree.xiaohongshu.com/

Verify field limits, AIGC labeling prompts, and commercial rules live in `creator.xiaohongshu.com` when publishing.
