# Proposal, approval and persistence

## New capture, in either mode

Invocation authorizes investigation and preparation of a concrete proposal, not formal learning writes. Before approval, use proposals/<proposal-id>/, or the explicitly assigned worker’s pending work area, for draft content and sanitized evidence. These files are unapproved staging: exclude them from canonical indexes, pattern counts, future active instructions and Notion. Do not append a canonical case revision or canonical evidence object first and merely hide it from the reader.

The human-facing learning_proposal.md contains:

- the lesson/case and why it is worth retaining, or why no reusable change is proposed;
- the exact concise reader text and intended destination;
- whether it creates a record or updates an existing one;
- proposed actions, with separate choices for saving the record and applying each asset change;
- applicable scope, necessary evidence and material uncertainty;
- exact new text or unified diffs, target files and current baseline for any rule/skill application.

Keep IDs, full hashes and processing metadata in the paired machine proposal. File paths and diffs are appropriate where the human must review a file change. Do not put machine evidence into a reader document's toggles or appendix.

Approval must come from an actual human response or a trusted human approval interface, bound to the shown version and action scope. A child prompt is not a new human approval. Do not manufacture an approval record from a request to investigate, a bot response, generic encouragement or silence. One explicit approval can cover an exact reviewed batch of records/actions; per-record bindings may cite that same real human response without asking once per row. One explicit approval can cover the exact reviewed set; do not repeatedly request it for unchanged authorized actions. If the human already supplied the exact final reviewed content, target and save action, that explicit instruction can serve as the approval; do not invent another confirmation step.

Saving alone and applying changes are distinct actions. Use save_record for the case/note and apply_asset:<id> for each concrete rule/skill/pattern change. Without the latter, a recommendation stays a recommendation. A recommendation without a full concrete patch cannot be treated as permission to implement an unspecified file change.

If the human changes the lesson, destination or action scope, revise the packet. Reuse prior approval only for its unchanged authorized part. Rejecting or postponing a proposal does not delete source evidence or authorize a different change.

## Historical exception

A historical post-review exception exists only when a real human explicitly authorizes a specific batch, window, destinations and actions. Verify its actual grant and qualifying task evidence before use. No such grant is included in this public package. A capture exception never grants rule/skill installation, pattern curation or broader access.

An isolated old case selected outside this authorized batch follows the new-capture preapproval flow. A chronological batch may be reviewed after saving; a newly proposed rule or skill from that batch still requires prior approval before application.

## Machine binding

New draft records use schema version 2. The review payload is the canonical UTF-8 JSON content of the record without publication_authorization. The shared digest helper in scripts/validate_store.py defines its byte representation. Before canonical or Notion writes, run its --candidate check against the fully authorized staged record (with --evidence-root for staged evidence). A --draft check validates structure only and never grants write authority. Use uv run --with jsonschema -- python when the dependency is not already in the selected Python runtime; unavailable validation is a blocked write, not implicit approval.

For an interactive canonical write, publication_authorization references a content-addressed human approval file in approvals/. That approval binds the reviewed payload digest and explicit action IDs. For historical saving, it references the exact authorized batch, a content-addressed HistoricalAssignment and a HistoricalTaskIndex. The assignment preserves the actual human request for a timeline review, and the task index binds that same task key and original session date to the qualifying primary evidence hashes/times. Comparison or boundary-context evidence cannot establish eligibility for a different task. The record stays awaiting_post_review; the manifest authorization is limited to save_record and its fixed window.

Any configured version-1 archival records remain frozen by explicitly recorded prior revision digests. New records and changed revisions cannot select version 1 to evade approval. Keep publication receipts separately in receipts/; do not mutate approved content to append a processing receipt.

The validator checks recorded bindings and evidence integrity. It cannot independently prove human authorship or intercept arbitrary connector writes. The executing agent must verify the human source and follow this workflow; the skill is not a host permission system.
