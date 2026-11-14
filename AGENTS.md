# Working agreements

This collection publishes personal methods, not private account configuration. Preserve the explicitly personal defaults, task scope, source attribution and meaningful safety/acceptance rules. A user's current instruction and established project rules take priority. Adding a new capability or background service needs a concrete authorized purpose.

Keep credentials, account/destination identities, local owner profiles, recordings, learning records, caches, backups and execution evidence outside Git and public discussions. Public examples must use fictional data. Read only the selected private profile when actual local configuration is needed; never include that profile in a release or turn historical receipts into new authorization.

Preserve supported invocation policy and product-specific metadata. Keep each skill's purpose clear, supporting references discoverable and helper dependencies explicit. Do not broaden permissions, bypass host approvals, silently change a browser/account, or imply that installing instructions executed a workflow. Run relevant offline checks; live calls, uploads, messages and cleanup require their task-specific authorization.

Before editing a linked live checkout, inspect concurrent changes and preserve the active installation. Develop publication changes in an isolated checkout, verify the private profile and old entry points, and deploy only reviewed changes. Keep actual account configuration local. Native manager updates and Git authoring are different operations; protect uncommitted edits in either workflow.

## Authoritative source and sync procedure

On the author's primary Mac, the active local personal skills (linked through the local skill manager to this checkout, plus private bindings under `~/.config/personal-skills/profiles/<skill>/`) are the authoritative source. Whenever a task adds, revises, renames, or deletes any personal skill locally:

1. Apply the corresponding public method update, new sanitized package, rename, or deletion in this repository in the same task.
2. Keep private identifiers, Notion URLs/UUIDs, account IDs, and host-specific paths strictly inside `~/.config/personal-skills/profiles/<skill>/` (owner-only permissions), never in this public repository.
3. Keep `~/.cc-switch/skills/<skill>` symlinked to this checkout without unlinked copy drift, and remove broken or retired symlinks across local agent harness directories.
4. Update `README.md`, run `python3 tools/check_release.py` and relevant offline tests, check `git diff` for private leaks, and commit and push to GitHub so the remote repository stays synchronized.

Use English for commits, Issues and PRs. Use the existing GitHub Issue for continuing work. Keep development/review receipts out of reader documentation. Before public exposure, review the full reachable history and repository discussions, including old pull-request references. Remain private if that history is not safely prepared.

## Code Review Rules

- Check assumptions against the request, current source and actual installation; findings need precise evidence and practical impact.
- Prefer the smallest complete change. Flag unrelated work and unnecessary abstractions, dependencies or automation.
- Preserve concurrent work, private context, file permissions, existing app switches and authorization boundaries.
- Compare claims with proportionate tests and readback. Distinguish structure checks, offline behavior, installation, live service execution and publication readiness.
- Check fresh-install behavior without an owner profile: missing configuration must remain missing rather than selecting the author's account or implying a standing grant.
- Do not invent findings, require stylistic rewrites or execute a skill simply because it is included in a review.
