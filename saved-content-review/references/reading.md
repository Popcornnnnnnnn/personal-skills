# Read the actual information carrier

Use this contract inside the existing saved-content workflow, not as another
collector. It adds no tools, models, permissions, background work or paid service.
The current human-selected scope and invocation rules still govern entry.

## Classify, then read

- `text`: read the complete source text and its relevant images.
- `speech`: review the complete audio, with relevant visual checks. Successful ASR
  execution is not proof that the words are correct.
- `captions`: read the full on-screen text and key visuals. Confirm audio is
  `music_only` or `none` from actual inspection, platform evidence or an explicit
  human clarification. ASR is not applicable to a music-only soundtrack.
- `mixed`: satisfy both speech and caption requirements.
- Unknown carrier: retain the source and report precisely what needs inspection.
  An audio waveform, nonzero signal, missing text track or nonsensical transcript
  does not establish whether the video contains spoken narration or burned-in text.

For caption-led material, inspect the entire timeline using dense extraction
(baseline four frames per second), OCR and visual review of every caption/change
group. Resolve low-confidence text, transitions, diagrams and short-lived captions
against the actual frames. Increase density around uncertain transitions; do not
claim that a few cover frames or the first minute cover the whole source. Retain
the timestamps, OCR and reviewed-frame evidence privately. Sampling checks bound
gaps; they do not independently establish understanding or guarantee that arbitrary
sub-frame text was captured.

## Evidence required by the existing checkpoint helper

New knowledge `archived`/`complete` records carry `reading_receipt`, the path to a
JSON file. `record` sets `reading_contract_required`; `ready` revalidates the same
receipt before cleanup. Historical completed records are not recaptured or silently
reclassified. A legacy archive being completed now needs the current receipt.
Record the same file's source/carrier/audio/basis/evidence fields while still pending,
before asking `plan` to allow recognition. That plan accepts an ASR attempt only for
observed speech or mixed content; caption/music-only and unclassified inputs cannot
start ASR. Fill the remaining coverage fields after actually reading the source.

Common fields:

```json
{
  "version": 1,
  "source_key": "douyin:123",
  "carrier": "captions",
  "audio_kind": "music_only",
  "basis": "explicit human confirmation; actual frames inspected",
  "evidence_path": "private-existing-observation.json",
  "duration_seconds": 2,
  "visuals_verified": true,
  "captions": {
    "sample_times": [0, 0.25, 0.5, 0.75, 1, 1.25, 1.5, 1.75, 2],
    "all_text_reviewed": true,
    "changes_reviewed": true,
    "unresolved_low_confidence": 0,
    "unreadable_intervals": []
  }
}
```

Paths must refer to actual private evidence; the example is not an acceptance
receipt. Caption timestamps must be ordered, span the source with no gap above
0.25 seconds, and include the ending. For `text`, use `text_complete:true` instead
of video fields. For `speech`/`mixed`, use `audio_kind:"speech"` and add:

```json
{
  "speech": {
    "method": "asr",
    "recognition_verified": true,
    "reviewed_ranges": [[0, 2]],
    "language": "zh",
    "expected_language": "zh",
    "segments": [{"text": "A fictional source sentence."}],
    "suspicious_segments": []
  }
}
```

`reviewed_ranges` covers the complete audio, including non-speech intervals checked
as such. Verify words, names and numbers against the source; wrong language,
suspicious segments and repeated long phrases block ASR acceptance. Actual listening
can use `method:"listening"` with the same full-audio verification and evidence;
never claim listening that did not occur. Keep factual research qualifications
separate from source-reading coverage. Save new prose under the current writing
rules, preserve human edits and read back the same canonical page before cleanup.

## Bounded recognition and explicit resumption

### Explicit acceptance of disclosed gaps

The full-reading contract above remains the default. When the user explicitly
authorizes cleanup after all accessible material is processed and residual gaps
are disclosed in the saved note, use the existing ledger's supported gap-aware
contract. This grants no new source access, recognition budget or cleanup scope.
Do not use it to skip material that can still be processed through authorized
routes, invent missing words, or classify an ASR omission as missing source audio.

Record `cleanup_acceptance:"available_content_with_disclosed_gaps"` and
`gap_acceptance_receipt` on the same knowledge item. Preserve
`coverage_complete:false`, source identity, canonical note and reading history.
The receipt is JSON with `version:1`, the same `criterion`, exact `source_key`,
canonical `source_url`, canonical `note_url`, and these required fields:

- `authorization`: a hashed JSON reference with `kind` equal to
  `explicit_user_available_content_cleanup`, the exact `source_key`, the same
  `criterion`, and the actual nonempty user `request_text`. A receipt or this
  document is not independent authorization.
- `accessible_review`: a hashed JSON reference with the exact `source_key`,
  `all_accessible_processed:true`, `unprocessed_accessible:[]`, a nonempty list of
  `processed_material`, and nonempty hashed `evidence` references to actual source
  coverage observations. Reuse verified prior reading without pretending to repeat it.
- `note_readback`: a hashed JSON reference with the exact `source_key`,
  `source_url`, `note_url`, `page_id`, current verified `save_intent_id`,
  `source_verified:true`, `content_verified:true`, actual timezone-aware
  `observed_at`, full saved `body`, and hashed `evidence` of independent readback.
- `residual_gaps`: a nonempty list. Each gap has a distinct `id`, nonempty
  `description` and `reason`, exact `note_text` appearing in the saved body, and
  nonempty hashed `evidence`. Describe uncertainty honestly, including tool limits.

Every hashed reference is `{path,sha256}` and must point to unchanged evidence.
`record` and `ready` validate this contract, current verified save, source/note
identity and existing scope/index/outcome checks. Preserve pre-click intents and
independent membership readback. `complete` means the authorized processing and
cleanup goal was met; `coverage_complete:false` and the receipt continue to show
the reading gaps. Keep fully-read counts separate from accepted cleanup counts.
This is not the separate human-discard route and does not authorize forced-zero
cleanup or deletion of unknown records.

Run `state.py plan --key KEY --file REQUEST` on the existing item. REQUEST supplies
an actual current human `authorization` reference and a `resume_reason` of
`manual_request`, `user_clarification`, `source_changed` or `tool_changed`.
Source/tool changes alone do not authorize a manual-only workflow. `unchanged`
never means completed: an authorized clarification can select a different carrier
without another ASR job. Parked/decision items require a human clarification.

Before each recognition job, include `next_attempt` in the plan, then append that
exact attempt to `reading_attempts` through `record` before execution. Each attempt
identifies `engine`, `model`, `source_revision` when known, and `estimated_cost`.
First reconcile this exact source's ledger and original job receipts. Record
`reading_attempt_history_evidence`, a private JSON file with matching `source_key`,
`history_complete:true`, and the full `prior_attempts` array found in those receipts
(empty only after checking). Missing structured history is not zero attempts. If
history is uncertain, report it instead of starting recognition. Legacy attempts
remain an immutable prefix and consume the bound; historical nonconforming attempts
are retained as evidence, never a reason to grant a new pair of jobs.
On first acceptance the helper seals that imported prefix as `reading_prior_attempts`
in the existing item. Subsequent receipt edits cannot enlarge it or reclassify a new
job as history; do not modify this internal field through ordinary checkpoints.
There are at most two entries across runs: one initial attempt and one alternative.
The alternative needs a different model or verified source revision and a concrete
`difference_evidence`; changing only language or repeating the same input/model is
not a new remedy. Never reset history on re-entry. Default `reading_cost_limit` is
zero. Any positive limit additionally needs `reading_cost_currency` and the exact
`reading_cost_authorization`; estimates must use that currency and fit the total
limit. A model or provider name does not grant upload or spending permission.

If a plan reports a spent budget or missing evidence, report that exact gap and its
re-entry condition in the existing result. A caption clarification, corrected
source evidence or actual listening may resolve the gap without another recognition
job. Do not start a third job, create an exception article, or leave an item silently
pending forever. Further recognition beyond the approved bound needs a new explicit
decision; this helper never resets the bound automatically.

Before a save or cleanup request, record `save_outcome:"pending"` with a new
`save_intent_id`, or `cleanup_outcome:"pending"` with a new `cleanup_intent_id`.
Use a unique ID for each actual operation and preserve its exact-source intent.
An uncertain response becomes `unknown`; never replace an unresolved intent.
`plan` then requires reconciliation, not another mutation, and `ready` blocks
cleanup. Clearing an uncertain outcome through `record` requires an explicitly
incoming `reconciliation_evidence` path, not a prior inherited receipt. Its JSON
must contain the exact `source_key`, `stage` (`save` or `cleanup`), current
`intent_id`, resulting `outcome`, and an existing `evidence_path` from independent
readback. A prior operation or other stage's receipt cannot reconcile this request.
Confirmed outcomes
can be `verified` or `not_applied`. Preserve original intent and response receipts.
Even after successful archival, execute only the currently authorized exact-source
cleanup, once, then reload and verify its actual resulting state.
