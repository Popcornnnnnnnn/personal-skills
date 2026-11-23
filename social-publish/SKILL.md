---
name: social-publish
description: "Prepare platform-specific publishing packages and a Notion pre-publish review page (scripts, uploaded media, and channel readiness) for Reddit, X, Product Hunt, TikTok, and RedNote/Douyin. Never publish without explicit per-channel authorization or automate manual-only channels."
---

# Social Publish

Create platform-native publishing packages for Reddit, X, Product Hunt, and RedNote (Xiaohongshu), plus any user-requested launch channels, with a standardized Notion pre-publish review gate. Do not turn one generic announcement into lightly edited copies across platforms.

## Boundaries

- Prepare local packages and the Notion pre-publish review page first. Never publish, submit, schedule, or automate engagement on any platform without explicit per-channel user authorization after review.
- **Manual-only channels:** Never automate logins, uploads, drafts, or posting on RedNote (Xiaohongshu) or Douyin, and leave mobile-app TikTok posting to the user when attaching trending sounds.
- Keep promotional material out of the product repository unless the user explicitly asks otherwise.
- Do not invent experience, adoption, metrics, endorsements, comparisons, availability, pricing, or product behavior.

## Storage

Use the caller's selected campaign directory, keeping promotional assets separate from product source by default. Reuse an existing campaign directory and keep one subdirectory per platform:

```text
<campaign>/
  README.md
  reddit/
  x/
  product-hunt/
  xiaohongshu/
```

For Reddit, add one subdirectory per community when the angles or rules differ. For RedNote (Xiaohongshu), use `xiaohongshu/` for a single note or `xiaohongshu/<note-slug>/` when preparing multiple notes in one batch.

## Pre-publish Notion review gate

Before publishing any campaign live, create or update a Notion pre-publish review page (following the `notion-writing` skill) so the user can inspect every asset and line of copy in one place:

1. **Channel readiness matrix:** Separate **agent-publishable channels** (which stay paused until explicit per-channel user approval in chat), **channels waiting on user sign-in or onboarding**, and **manual-only channels** (RedNote/Xiaohongshu, Douyin, and mobile-app TikTok when attaching trending sounds).
2. **Complete copy & notes:** Include exact titles, post bodies, threads, hashtags, links, pinned comments, and fact-only Product Hunt Maker notes per channel.
3. **Uploaded media:** Upload and embed all promotional videos and images directly into the Notion page so they can be previewed inline, keeping local filesystem paths and internal session IDs out of reader-facing text.
4. **Compliance & rollout gates:** Surface storefront availability limits, account eligibility rules, non-affiliation notices, and platform anti-automation rules.

## Workflow

1. Establish source truth from the repository, release page, supplied material, real photos/metrics, or another authoritative source. For a product or tool, record the canonical product URL, availability, platform support, pricing, and important limits in campaign metadata even when a target platform forbids external links in the post itself.
2. Read the target platform reference below. For Reddit, research the exact community before drafting; for RedNote (Xiaohongshu), select the note pillar and media carrier before writing.
3. Verify any time-sensitive rules, field limits, media requirements, flairs, disclosure flags, recurring threads, and account gates against current first-party guidance or the live community.
4. Draft for the destination's native format and reason for caring. Do not start from a universal launch post.
5. For editable prose (English or Chinese), use the separately installed `humanizer` skill in embedded mode when available. Preserve technical identifiers, required URLs, factual limits, required disclosures, and approved copy.
6. Recheck facts, character limits, link and anti-diversion rules, media dimensions, on-image text, and community fit after editing. For RedNote packages, run `python3 scripts/check_xiaohongshu.py <package-dir>` from this skill directory (with `--ocr` on macOS once visual assets are rendered).
7. Save the complete local package and assemble the **Notion pre-publish review page** with final copy, uploaded media, readiness status, and compliance notes. State clearly that nothing was published, and publish on agent-publishable channels only after explicit per-channel user approval.

## Platform routing

- Reddit: read [references/reddit.md](references/reddit.md). Community rules and account eligibility control whether a draft is actually ready.
- X: read [references/x.md](references/x.md). Default to one concise standard post; add a thread only when each post contributes something distinct.
- Product Hunt: read [references/product-hunt.md](references/product-hunt.md). Prepare listing fields and factual Maker notes, but do not generate a ready-to-paste Maker comment.
- RedNote (Xiaohongshu / 小红书): read [references/xiaohongshu.md](references/xiaohongshu.md). Keep external links, CLI install strings, QR codes, and contact hooks out of both copy and slides; record the exact AIGC disclosure action and leave upload/scheduling manual.
- Other requested launch channels (for example Douyin, TikTok, Hacker News, V2EX, or Jike): capture exact copy, media, storefront limits, and manual-only constraints in the Notion pre-publish review page before any live step.

## Shared asset rules

- Prefer real interface screenshots, authentic photos, and truthful product or concept visuals. Never fabricate UI.
- Use one strong asset before adding a gallery. Every additional image must explain a different part of the product or story.
- Keep text sparse, legible at feed size, and inside safe margins. Inspect the final image for crop, spelling, hierarchy, product fidelity, and platform-restricted text or codes.
- Put assets inside the relevant platform directory. Duplication across platform folders is acceptable when it makes each package self-contained.

## Completion standard

A package is ready for review only when it is platform-specific, fact-checked, within current limits, self-contained, explicit about unresolved account, disclosure, or community choices, and summarized in the Notion pre-publish review page with uploaded media. List the package path, Notion review link, and readiness of each channel without implying publication.

## Local owner context

If `~/.config/personal-skills/profiles/social-publish/SKILL.md` exists, read it once for this task's private destinations, environment and established constraints. Keep that profile local. Verify changing facts live; a saved profile does not grant new access or authorize an unrelated action. Without a configured profile, resolve the required inputs from the current request and authorized tools; never invent the author's account or destination.
