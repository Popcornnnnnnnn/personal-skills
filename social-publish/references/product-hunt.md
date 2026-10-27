# Product Hunt

Product Hunt is a structured product listing plus maker participation. Optimize each field for scanning and make the gallery explain the product without inflated claims.

## Source of truth

Inspect the authenticated live submission flow before preparing a package. Use the live field labels, counters, accepted media, and checklist as the operational source of truth; use Help Center articles for policy and general guidance. When they disagree, record the discrepancy and follow the live form for data that must be submitted.

For example, the live form inspected on 2026-09-10 allowed a 500-character Description while the Help Center still described 260 characters. Do not preserve the older number merely because it appears in documentation.

## Listing fields

Prepare and validate:

- Product name: name only.
- Direct product URL, with the selection rationale recorded in the package.
- Short, benefit-led tagline.
- Concise description that answers the live prompt and stays within the current form counter.
- Pricing/status and a small number of closest available topics.
- Square thumbnail; record actual dimensions, file type, and size against the live requirements.
- Gallery images; record exact order, dimensions, and which image becomes the social preview.
- Maker identity and any permitted secondary links.

Do not invent topics that are absent from the live selector.

## Primary URL decision

Product Hunt asks for a direct link to the product page and says to avoid press or blog links. Choose links in this order:

1. A maintained public product or landing page where a visitor can understand the product and reach the product itself.
2. For an open-source product without a separate site, the repository root when its README functions as the product page and exposes installation or release access.
3. A store listing only when it is the actual product destination and no better product page exists.

Do not use a release tag, changelog, article, press page, README anchor, or direct binary as the primary URL. Put an App Store, Play Store, package, installer, or direct-download URL in Product Hunt's separate **Download link** field when appropriate. Treat release notes as supporting information.

Open the chosen primary URL signed out and confirm that it is public, current, product-specific, and understandable before download. If a better landing page is planned but not live, use the best valid page available now rather than inventing a future URL.

## Form-aligned document

Structure each Product Hunt `POST.md` in the same order as the current submission flow. The flow inspected on 2026-09-10 contained:

### Main info

- **Name of the launch** with its live character count. Check imported URLs carefully: repository metadata may incorrectly set the product name to the hosting provider.
- **Tagline** with its live character count.
- **Links to the launch**, including the selected primary URL, why it was selected, and any link added through **+ Add more links**.
- **Is this an open source project?** with an explicit Yes/No answer.
- **X account of the launch**. Leave blank when the product has no dedicated account; do not insert an unrelated personal account.
- **Description** with its live character count and prompt fit. Replace weak auto-imported repository metadata.
- **Launch tags**, limited to the number shown by the form. Record exact selectable names rather than generic topics.
- **Write the first comment**, handled under the Maker comment boundary below.

### Images and media

- **Thumbnail**: the inspected form recommended 240x240 and accepted JPG, PNG, or GIF up to 2 MB. Verify again for each launch.
- **Gallery**: state the upload order and social-preview image. The inspected form recommended at least three images; its Help Center also notes that a gallery needs multiple images to appear.
- **Video / Loom**: optional. Record `None` when no real walkthrough or maker story exists.
- **Interactive demo**: optional. Record `None` when no truthful supported demo exists.

### Makers

- **Did you work on this launch?** Record whether the submitter is Hunter only or both Hunter and Maker.
- **Who worked on this launch?** List only verified Product Hunt usernames of actual contributors; record `None` for additional Makers when appropriate.

### Shoutouts

- Optional founder reviews for products that genuinely helped build the launch.
- Add only tools the maker can truthfully recommend and describe from direct use. Record `None` rather than inventing endorsements.

### Extras

- **Pricing**: Free, Paid, or Paid with a free trial/plan, based on product truth.
- **Promo code**: include offer, code, and expiration only when a real promotion exists; otherwise record `None`.
- **Funding information**: Bootstrapped, Y Combinator company, or Venture backed. Record only a verified answer; otherwise leave it unselected and flag it for the maker.

### Connect with Investors

- Optional and private to Product Hunt's investor-matching flow.
- Do not infer or draft founder fit, motivation, competitors, revenue, growth, or other investor answers. Record `Skipped` unless the maker explicitly asks to prepare this section from verified facts.

### Launch checklist

Mirror the live required and strongly recommended items, then state which optional items are intentionally empty and why. The flow inspected on 2026-09-10 required product name, tagline, description, thumbnail, gallery image, and launch tags; it strongly recommended Shoutouts, Additional Makers, the first comment, and Video / Loom. Record whether the user should choose **Create draft** or **Schedule launch for later**, but never operate either control under this skill.

## Writing style

- Tagline: say what outcome the product provides, not that it is new or exciting.
- Description: explain the product, primary audience, and one meaningful differentiator. Avoid a compressed feature dump.
- Gallery: first image establishes the product; later images show distinct workflows, modes, or proof.
- Use English unless the current platform rules explicitly permit the intended language.

## Maker comment boundary

Product Hunt's current commenting guidelines prohibit AI-generated comments. Do not produce a ready-to-paste Maker comment.

Create `MAKER-NOTES.md` instead. It may contain only factual prompts, source facts, questions to answer, and a suggested outline. Tell the maker to write the final comment personally in their own words. Do not convert the notes into polished sentences that function as a disguised generated comment.

## Sharing and launch conduct

- Organic sharing is allowed, but never ask for upvotes, coordinate voting, mass-message people, offer incentives, or use voting services.
- Recommend a complete, genuine personal profile before launch.
- Avoid duplicate submissions. If removed, diagnose the stated reason before attempting again.

## Package

Use `product-hunt/` with:

- `POST.md`: mirror the live Main info, Images and media, Makers, Shoutouts, Extras, Connect with Investors, and launch-action sections with exact fields, limits, values, links, asset order, and truthful `None` or `Skipped` entries.
- `MAKER-NOTES.md`: fact-only outline for the maker's personally written first comment.
- `CHECKLIST.md`: mirror the live submission steps, account gate, required/strongly recommended checklist, profile, asset order, schedule, and no-upvote rules.
- `assets/`: square icon plus at least two correctly sized gallery images when a gallery is desired.

## Current first-party references

- How to post: https://help.producthunt.com/en/articles/479557-how-to-post-a-product
- Featuring guidelines: https://help.producthunt.com/en/articles/9883485-product-hunt-featuring-guidelines
- Commenting guidelines: https://help.producthunt.com/en/articles/10030102-commenting-guidelines
- Sharing: https://help.producthunt.com/en/articles/2690626-how-do-i-share-my-post
- Upvote requests: https://help.producthunt.com/en/articles/484935-can-i-ask-my-community-friends-family-to-upvote-a-product
- Removal reasons: https://help.producthunt.com/en/articles/3539992-why-was-my-comment-or-post-removed

Verify field limits and asset requirements live at drafting time.
