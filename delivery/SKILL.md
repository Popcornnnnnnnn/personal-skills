---
name: delivery
description: Complete Git/GitHub delivery and handoff using proportionate validation, direct delivery or independent PR review, verified fixes and authorized completion. Use when delivering changes, handing work between agents, or cleaning up delivered branches and worktrees; ordinary code browsing does not require it.
---

# Delivery rules

These are personal delivery defaults, reusable across agent harnesses. Read the current task and project guidance before delivery. Installation alone grants no repository access or publication, deployment or device authority.

- The user's explicit instruction for the current task overrides their own global, project and skill workflow defaults. If they request direct push or waive review, follow that choice even for a high-risk change. Record skipped checks honestly. Actual access restrictions and repository protections still apply; report a concrete blocker instead of inventing permission.
- Use two paths: direct delivery for bounded low-risk changes or an explicit user choice; otherwise one PR per complete goal, including multi-module and high-risk work.
- The current delivery session owns validation, independent review, verified fixes, necessary re-review and authorized merge. Do not stop at opening a PR. Use a fresh reviewer session or independent review process; review the current candidate and recheck the remote head before merging.
- Keep review focused on correctness, the request, simplicity and proportionate validation. Report evidence and practical impact; do not invent blockers. A failed or unfinished review is not a pass. Report unresolved blockers with the retained branch/PR and a concrete next step.
- GitHub is the task and code record. Reuse the existing Issue/PR; create an Issue only for substantive bugs, features or work needing continuation. Check current ownership before taking over. Small one-off changes do not need a tracking Issue just for ceremony.
- When human input is needed, state the blocker, the specific action or reply needed, and what follows. Preserve work for the next session. A comment does not automatically wake a finished agent; do not create watchers, schedules or cross-chat messages without an explicit request.
- When switching harnesses, leave the goal, completed work, remaining work and relevant branch/PR in the same task. Retain original authorship and record the new handler; avoid a second competing implementation.
- Verify the destination repository, branch and publication scope. Preserve unrelated changes and project-specific data, deployment and device permissions. A code merge does not establish installation, deployment or physical acceptance.
- Use English Issue/PR/commit text; preserve quoted source text. Include one attribution line, `Agent: <harness>/<runtime-reported-model>`, in each agent-written Issue or PR body and each individual agent-written Issue or PR comment. Prefer current-turn runtime metadata; use configuration only when it identifies the actual model used. Do not guess; use `Unknown` for either part that cannot be verified. For a substantial PR, include a concise original session reference when available; never fabricate or publish private host details.
- After verified delivery, remove only task-created branches, worktrees and temporary files with no undelivered work, needed evidence or active use. Preserve uncertain items and state why. Keep required CI and ordinary repository maintenance.
