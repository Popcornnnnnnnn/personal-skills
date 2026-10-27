# Personal skills

A collection of personal working methods for coding agents, published under the [MIT license](LICENSE). The defaults are deliberate preferences: BrowserOS neo for browser interaction, compact desktop interfaces, explicit human intent, and completion claims backed by readback. Adopt the parts that fit your work; a user's current request and established project rules take priority.

## Skills

| Skill | Method |
| --- | --- |
| `agent-browser` | Choose direct reading or Neo; preserve login and task-tab boundaries |
| `daily-brief-feedback` | Record exact human feedback without inventing preference labels |
| `doubao-search` | Query Feishu enterprise knowledge and qualify source verification |
| `learn` | Propose evidence-backed lessons and separate saving from rule application |
| `mac-app-replacement` | Replace apps and verify cleanup of confirmed obsolete copies |
| `neo-xhs-favorites-inventory` | Reconcile favorites coverage, stable identities and count gaps |
| `notes` | Keep a complete canonical source article and preserve human judgment |
| `notion-trash` | Guard selected trash/restore actions and verify the result |
| `notion-writing` | File readable documents while preserving identity, content and state |
| `saved-content-review` | Separate source coverage, verified archival and authorized cleanup |
| `shop-search` | Search JD and Taobao through explicitly configured routes |
| `social-publish` | Prepare truthful platform-specific launch materials locally |
| `tell-dot` | Hand selected material to a verified Finn/Dot recipient and check delivery |
| `ui-preferences` | Apply personal interface preferences with clear scope |
| `voice-memo-notion` | Preserve transcript evidence and verify saved recording notes |

## Install and use

Each directory is a skill package with `SKILL.md` and optional supporting files. Install only the skills you want through your agent's documented skill installer or a compatible manager such as CC Switch. Installing a skill does not install its tools, log into accounts, enable schedules, send messages, upload recordings or authorize cleanup.

Invocation behavior follows the host-specific manifest and `agents/openai.yaml` metadata; preserve both when copying a package. Some manifests retain the existing `disable-model-invocation` extension for hosts that support it.

Use your installed skill directory when running a helper, for example `python3 scripts/notion_trash.py --help` from `notion-trash/`. Keep an authoring checkout separate from a manager-owned installed release when using native updates. Review uncommitted changes before pulling or replacing files; do not let an update overwrite work silently.

## Tools and private setup

- Browser workflows need a separately installed BrowserOS neo connection and its current usage guide. `agent-browser` keeps the author's Neo preference while honoring an explicit browser choice.
- Notion workflows need an authorized connector and verified live destinations. The trash helper is an optional separate credentialed supplement, with a hidden setup prompt and guarded actions.
- `shop-search` needs a configured `cn_scraper_mcp` runtime for its optional signed-search adapter; the legacy JD bridge is optional and explicit-only. No browser cookies ship here.
- `voice-memo-notion` needs authorized audio access, Python with `requests`, FFmpeg/ffprobe and a configured transcription service. Planning is local; execution can upload audio and incur cost only within the current task's authorization. The author's preference is verified free-only processing.
- `learn` has an optional `jsonschema` validator. `tell-dot` prefers direct Slack tools; its optional bridge needs an already configured Codex CLI/Slack connection with normal host permissions.
- An installed `humanizer` can assist prose editing. External tools and skills retain their own licenses and access requirements; they are not included in this package.

Private owner profiles may live at `~/.config/personal-skills/profiles/<skill>/SKILL.md`. They preserve actual destinations, environment and applicable local constraints without publishing them. Read the selected profile before its dependent work. A profile does not grant new rights or turn old receipts into permission. A fresh installation has no preauthorized accounts, cleanup scope, historical exception or schedule.

Optional non-secret adapter settings live in `~/.config/personal-skills/settings.json`:

| Section | Required values when that adapter is used |
| --- | --- |
| `voice_memo_notion` | Official `origin`; `keychain_account` for Keychain use; optional `keychain_service` and an explicitly checked price estimate |
| `saved_content_review.accounts` | The intended `xhs`, `douyin`, and `bilibili` account identities |
| `shop_search` | Optional `python` interpreter and existing `jd_client_dir` |
| `tell_dot` | Verified `workspace_id`, `recipient_user_id`, and direct-message `conversation_id` |

Keep configuration private (owner-only directory/files). Store secrets in the user's credential mechanism or environment, not in this JSON, skill text, URLs or Git. Do not copy another person's identifiers as examples.

## Maintenance and checks

Change reusable methods in Git. Change actual account bindings and ongoing grants only in local owner configuration, within the user's request. Preserve independent checks for source coverage, data integrity, authorization, idempotent recovery and final readback.

Run `python3 tools/check_release.py` for package structure, reference and publication checks. The changed helpers have offline tests in `tests/`; the saved-content ledger also carries its own regression checks. These checks do not prove authenticated service behavior or a successful end-to-end workflow. Test only the actual task's authorized scope.

Git history, cached pull-request references and repository discussions need their own privacy review before a private working repository becomes public. A clean current tree or credential scanner alone is insufficient. Package releases should contain tracked files only; private profiles, local compatibility files, caches and execution evidence stay outside the release.
