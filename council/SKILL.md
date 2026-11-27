---
name: council
description: Run an explicit, read-only Council review with Codex, Gemini Neon, and Command Code DeepSeek V4.1 Flash for code, UI, or a decision. Use only when the user asks to run Council.
disable-model-invocation: true
---

# Council

Adapted from [Theo Browne's Council](https://github.com/t3dotgg/tstack/blob/11e37a74d0a6868c121cd0910ab2b3bd9873b92a/skills/council/SKILL.md), under the [MIT license](LICENSE).

## Reviewers

Use three independent reviewers by default:

- Codex with GPT-6.2 Sol (`gpt-6.2-sol`).
- Antigravity with Gemini 4 Neon (`gemini-4-neon`). Select the direct Neon model.
- Command Code via ACP with DeepSeek V4.1 Flash (`deepseek/deepseek-v4.1-flash`).

Use any reviewer the user explicitly requests in place of the corresponding default. In T3 Code, resolve the requested models and provider instances with `orchestrator_capabilities` (pass `search`, such as `"deepseek"`, when a large ACP catalog is truncated), reuse an applicable capability result, and delegate according to the host's orchestration rules. In other hosts, use an available delegation tool that can run each requested model independently. Report unavailable reviewers and any partial coverage. Honor explicit model choices and ask before substituting a model.

## Review

1. Freeze the review scope and give each reviewer the same brief and candidate. Use the same diff, decision criteria, or before/after screenshots for all reviewers. Include the intended behavior, relevant constraints, and verification already run. Share only authorized material.
2. Start the reviews in parallel when supported. Keep them read-only and independent. Ask each for up to three findings with impact, evidence, and a proposed fix or check. For a decision, ask for a recommendation and its decisive trade-off. If the user requests scores, give the same rubric to all reviewers and keep any target score out of their brief.
3. Verify the findings against the candidate and relevant checks. Report agreement, meaningful disagreements, and missing coverage. The parent agent owns any fixes the user authorized. After material fixes, run at most one fresh review round by default. Carry forward the project's existing acceptance and delivery rules.

Report the actual reviewers, rounds, verified findings, and remaining blockers. Label any missing review or score explicitly. Only write to a PR when the user or delivery workflow has authorized the write.
