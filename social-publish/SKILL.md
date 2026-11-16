---
name: social-publish
description: "Prepare local, platform-specific publishing packages for Reddit, X, Product Hunt, and RedNote (Xiaohongshu), with truthful copy/assets and explicit manual posting readiness. It does not publish."
---

# Social Publish

Create platform-native publishing packages for Reddit, X, Product Hunt, and RedNote (Xiaohongshu). Do not turn one generic announcement into lightly edited copies across platforms.

## Boundaries

- Prepare files locally only. Never log in, inspect an account, open a publishing form, upload media, save a platform draft, schedule, automate engagement, or publish.
- Support only Reddit, X, Product Hunt, and RedNote (Xiaohongshu) unless the user explicitly expands the platform set.
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

## Workflow

1. Establish source truth from the repository, release page, supplied material, real photos/metrics, or another authoritative source. For a product or tool, record the canonical product URL, availability, platform support, pricing, and important limits in campaign metadata even when a target platform forbids external links in the post itself.
2. Read the target platform reference below. For Reddit, research the exact community before drafting; for RedNote (Xiaohongshu), select the note pillar and media carrier before writing.
3. Verify any time-sensitive rules, field limits, media requirements, flairs, disclosure flags, recurring threads, and account gates against current first-party guidance or the live community.
4. Draft for the destination's native format and reason for caring. Do not start from a universal launch post.
5. For editable prose (English or Chinese), use the separately installed `humanizer` skill in embedded mode when available. Preserve technical identifiers, required URLs, factual limits, required disclosures, and approved copy.
6. Recheck facts, character limits, link and anti-diversion rules, media dimensions, on-image text, and community fit after editing. For RedNote packages, run `python3 scripts/check_xiaohongshu.py <package-dir>` from this skill directory (with `--ocr` on macOS once visual assets are rendered).
7. Save the complete package with final copy, assets, and a short manual checklist. State clearly that nothing was uploaded or published.

## Platform routing

- Reddit: read [references/reddit.md](references/reddit.md). Community rules and account eligibility control whether a draft is actually ready.
- X: read [references/x.md](references/x.md). Default to one concise standard post; add a thread only when each post contributes something distinct.
- Product Hunt: read [references/product-hunt.md](references/product-hunt.md). Prepare listing fields and factual Maker notes, but do not generate a ready-to-paste Maker comment.
- RedNote (Xiaohongshu / 小红书): read [references/xiaohongshu.md](references/xiaohongshu.md). Keep external links, CLI install strings, QR codes, and contact hooks out of both copy and slides; record the exact AIGC disclosure action and leave upload/scheduling manual.

## Shared asset rules

- Prefer real interface screenshots, authentic photos, and truthful product or concept visuals. Never fabricate UI.
- Use one strong asset before adding a gallery. Every additional image must explain a different part of the product or story.
- Keep text sparse, legible at feed size, and inside safe margins. Inspect the final image for crop, spelling, hierarchy, product fidelity, and platform-restricted text or codes.
- Put assets inside the relevant platform directory. Duplication across platform folders is acceptable when it makes each package self-contained.

## Completion standard

A package is ready only when it is platform-specific, fact-checked, within current limits, self-contained, and explicit about unresolved account, disclosure, or community choices. List the package path and readiness of each platform without implying publication.

## Local owner context

If `~/.config/personal-skills/profiles/social-publish/SKILL.md` exists, read it once for this task's private destinations, environment and established constraints. Keep that profile local. Verify changing facts live; a saved profile does not grant new access or authorize an unrelated action. Without a configured profile, resolve the required inputs from the current request and authorized tools; never invent the author's account or destination.
