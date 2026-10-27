# Reddit

Reddit is community-first. A project may fit Reddit generally while still being wrong for a particular subreddit, placement, account, or day.

## Research before drafting

For every target community:

1. Read the current rules, removal reasons, pinned posts, recurring showcase threads, and required disclosures.
2. Inspect a small sample of recent accepted posts with a similar purpose.
3. Determine the allowed placement: standalone post, image post, link post, recurring thread comment, or no promotion.
4. Check likely account gates: account age, verified email, overall karma, community karma, or contributor status. Treat undisclosed thresholds as unknown.

If the account has already been filtered and moderators cite karma or reputation, mark the package blocked. Recommend genuine participation and the approved recurring thread when available; do not advise repeated retries.

## Writing style

- Lead with the problem, technical decision, lesson, or concrete feedback request that matters to this community.
- Use first person only for facts the maker supplied. Disclose the maker relationship plainly when appropriate.
- Prefer one canonical link. Do not stack GitHub, release, download, and landing-page links without a community-supported reason.
- Keep feature lists short. Technical communities care more about one real constraint or tradeoff than launch language.
- Do not reuse identical title/body combinations across communities. Cross-post only when allowed and adapt each version substantively.
- Topic keywords are planning metadata, not Reddit hashtags.

## Images

- Follow the selected community and post type. Some destinations or placements do not accept images.
- In technical communities, default to no image or a real screenshot. Use a promotional hero only when recent accepted posts establish that visual norm.
- Never change to a less suitable post type just to force an image.

## Package

Use `reddit/<community>/` with:

- `POST.md`: `Community`, `Placement`, `Flair`, `Topic keywords`, `Community fit`, then exact title/body or comment text.
- `CHECKLIST.md`: current-rule checks, account-gate status, image choice, disclosure, and retry guidance.
- `assets/`: only media this specific community can use.

Separate selectable flair from internal topic keywords. Label uncertain flair as `verify in composer`.

## Anti-spam gates

- Do not mass-post repetitive content for exposure.
- Do not delete and resubmit repeatedly to escape filters.
- Do not automate posting, voting, comments, or account activity.
- A filter result may reflect reputation rather than prose. Do not promise that rewriting will bypass it.

## Current first-party references

- Spam policy: https://support.reddithelp.com/hc/en-us/articles/360043504051-Spam
- Reposting and crossposting: https://support.reddithelp.com/hc/en-us/articles/4835584113684-What-is-reposting-fka-crossposting
- Poster eligibility: https://support.reddithelp.com/hc/en-us/articles/33702751586836-Poster-Eligibility-Guide-Post-Check
- Reputation filter: https://support.reddithelp.com/hc/en-us/articles/27441485903124-Reputation-filter

Verify community-specific rules live at drafting time.
