---
name: project-audit
description: Audit a whole project for defects, inconsistencies, waste, and obsolete material. Use for broad project health checks and cleanup passes that ask for an evidence-backed review or verified fixes plus a list of remaining decisions.
---

# Project audit

Identify problems that matter to the project, make small verified fixes when authorized, and give the user a short list of decisions supported by evidence.

## Establish scope and baseline

- Identify the intended project, its repositories, its normal entry points, and applicable local instructions. Respect exclusions. Check existing changes and active work before editing.
- Map maintained code, tests, configuration, and documentation. Check generated files, archives, and private evidence only when relevant to a finding and within scope. Prioritize normal user paths and likely consequences.
- Use existing tests, checks, and issue records where relevant. Record baseline failures before attributing them to a change. Preserve other people's changes and use the project's version-control workflow so audit edits are easy to review and undo.

## Choose what to fix

- A review-only request means findings only. In a fix-and-review pass, change an item when the problem is evidenced, the intended behavior is clear, the change is small and reversible, and a relevant check can verify the result.
- In areas with little test coverage, investigate first. Use a focused regression check, safe offline reproduction, or direct verification of the changed behavior. Defer behavior changes whose effect remains uncertain.
- Check callers, configuration, entry points, and compatibility or recovery uses before removing apparently obsolete material. Verify ownership and retention needs for files. Check which rule or source is current before resolving an inconsistency, and measure or demonstrate waste before optimizing.
- Distinguish a verified symptom from an inferred cause or unverified real-world impact. Defer changes that depend on a product decision, disputed ownership, or unavailable validation. Ask the smallest question that lets the user decide, and continue independent work.
- Validate fixes through their normal entry points with the smallest relevant checks. Follow the project's delivery rules and the user's authorization for commits, publishing, issue updates, and deployment.

## Report the result

List fixes with the evidence that they work. Put the highest-impact remaining findings first. Give each a location, the observed problem and consequence, and the missing evidence or decision. Indicate confidence in words where it changes the next step. State which parts of the project were reviewed and which checks were unavailable.
