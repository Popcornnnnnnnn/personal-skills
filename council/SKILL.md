---
name: council
description: Run an explicit, read-only Council review with weighted primary (Codex, Gemini Neon) and supporting (DeepSeek V4.1 Flash Fast, GLM-5.3 Flash) reviewers for code, UI, or a decision. Use only when the user asks to run Council.
disable-model-invocation: true
---

# Council

Adapted from [Theo Browne's Council](https://github.com/t3dotgg/tstack/blob/11e37a74d0a6868c121cd0910ab2b3bd9873b92a/skills/council/SKILL.md), under the [MIT license](LICENSE).

## Reviewers

Use four independent reviewers by default across two weight tiers:

- Primary (`2x` weight): Codex with GPT-6.2 Sol (`gpt-6.2-sol`).
- Primary (`2x` weight): Antigravity with Gemini 4 Neon (`gemini-4-neon`). Select the direct Neon model.
- Supporting (`1x` weight): Command Code via ACP with DeepSeek V4.1 Flash Fast (`deepseek/deepseek-v4.1-flash-fast`).
- Supporting (`1x` weight): CodeBuddy Code via ACP with GLM-5.3 Flash (`glm-5.3-flash`).

Use any reviewer the user explicitly requests in place of the corresponding default. In T3 Code, resolve the requested models and provider instances with `orchestrator_capabilities` (pass `search`, such as `"deepseek"` or `"glm"`, when a large ACP catalog is truncated), reuse an applicable capability result, and delegate according to the host's orchestration rules. In other hosts, use an available delegation tool that can run each requested model independently. Do not let an unavailable supporting reviewer block the Council; report unavailable reviewers and any partial coverage. Honor explicit model choices and ask before substituting a model.

## Review

1. Freeze the review scope and give each reviewer the same brief and candidate. Use the same diff, decision criteria, or before/after screenshots for all reviewers. Include the intended behavior, relevant constraints, and verification already run. Share only authorized material.
2. Preserve blindness whenever unbiased evaluation or scoring matters: keep target scores, passing thresholds, round numbers, attempt suffixes (such as `-r2` or `-v3`), prior-round framing, and polish-pass branch names out of both the brief and artifact paths (use neutral paths for exported screenshots or snapshots).
3. Start the reviews in parallel when supported. Keep them read-only and independent. Ask each for up to three findings with impact, evidence, and a proposed fix or check. For a decision, ask for a recommendation and its decisive trade-off.
4. Verify the findings against the candidate and relevant checks. Judge concrete defects on verified evidence regardless of tier; apply the `2x` primary / `1x` supporting weights to judgment calls, tie-breaks, and aggregate scores. Report agreement, meaningful disagreements, and missing coverage. The parent agent owns any fixes the user authorized. Carry forward the project's existing acceptance and delivery rules.

## Scoring & Convergence

Apply these guardrails when scores or multi-round iterations (such as `/goal` loops) are requested:

- **Rubric scale:** Give all reviewers the same rubric. Prefer integer `1–5` bands with explicit behavioral anchors (for example, `4 = shippable with no visible defects`, `5 = reference-grade`) over `0.1`-precision `10`-point scales unless the user mandates another scale.
- **Pass gates:** Gate on zero verified `P0`/`P1` defects across all reviewers plus the `2x`/`1x` weighted aggregate (or primary-pair consensus) on subjective dimensions. Avoid unweighted headcount votes or raw per-model `min`-cell cutoffs across models with different baseline strictness; if a user-specified unweighted gate stalls on inter-model calibration drift, surface the drift and ask before looping further.
- **Stop condition:** Run at most one fresh review round after material fixes by default. In explicit multi-round runs, cap iterations at `2–3` rounds on unchanged inputs and criteria, or stop once a round finds zero new verified `P0`/`P1` defects and the weighted aggregate plateaus (within `0.2` on a `10`-point scale, or unchanged band on `1–5`). Prefer expanding audited artifacts or criteria (for example, accessibility, localization, or contrast checks) over re-scoring the same captures.

Report the actual reviewers, rounds, verified findings, and remaining blockers. Label any missing review or score explicitly. Only write to a PR when the user or delivery workflow has authorized the write.
