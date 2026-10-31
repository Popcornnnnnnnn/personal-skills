#!/usr/bin/env python3
"""Atomic progress ledger for agent-observed saved-content runs; no remote writes."""
import argparse
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timedelta
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

ROOT = Path.home() / "Library/Application Support/saved-content-review"
TZ = ZoneInfo("Asia/Shanghai")
def configured_accounts():
    path = Path.home() / '.config/personal-skills/settings.json'
    if not path.exists():
        return {key: '' for key in ('xhs', 'douyin', 'bilibili')}
    value = json.loads(path.read_text()).get('saved_content_review', {}).get('accounts', {})
    if not isinstance(value, dict) or any(not isinstance(v, str) for v in value.values()):
        raise ValueError('Invalid saved-content account configuration')
    return {key: value.get(key, '') for key in ('xhs', 'douyin', 'bilibili')}


ACCOUNTS = configured_accounts()
ID_PATTERNS = {"xhs": r"[0-9a-f]{24}", "douyin": r"[0-9]+", "bilibili": r"BV[0-9A-Za-z]{10}"}
URL_BASES = {"xhs": "https://www.xiaohongshu.com/explore/", "douyin": "https://www.douyin.com/video/",
             "bilibili": "https://www.bilibili.com/video/"}
STATES = {"pending", "pending_read", "needs_decision", "failed", "archived", "complete", "discarded"}


def now():
    return datetime.now(TZ)


@contextmanager
def ledger(root):
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (root / "state.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = root / "state.json"
        data = json.loads(path.read_text()) if path.exists() else {"schema": 1, "items": {}, "runs": {}}
        assert data["schema"] == 1
        yield data
        temp = root / "state.tmp"
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        temp.chmod(0o600)
        os.replace(temp, path)


def in_scope(item, policy):
    if item.get("scope_excluded"):
        return False
    if item.get("key", "").startswith("bilibili:"):
        allowed = policy.get("bilibili_scope", {}).get("folder_ids")
        if allowed is not None:
            folders = item.get("folder_ids", [])
            return bool(folders) and set(folders).issubset(set(allowed))
    return True


def finite_number(value):
    return type(value) in (int, float) and math.isfinite(value)


def validate_reading(item, required=False):
    """Check observed carrier evidence, not an ASR job's completion flag."""
    path = item.get("reading_receipt")
    if not path:
        if required:
            raise ValueError("Knowledge completion needs a source-carrier reading receipt")
        return True  # Historical acceptance is not a new reading attempt.
    receipt = json.loads(Path(path).read_text())
    carrier = receipt.get("carrier")
    if (receipt.get("version") != 1 or receipt.get("source_key") != item["key"]
            or carrier not in {"text", "speech", "captions", "mixed"}
            or not receipt.get("basis") or not Path(receipt.get("evidence_path", "")).is_file()):
        raise ValueError("Reading receipt needs the exact source, known carrier and observed evidence")
    if carrier == "text":
        if receipt.get("text_complete") is not True:
            raise ValueError("Source text is incomplete")
        return True
    if (carrier == "captions" and receipt.get("audio_kind") not in {"music_only", "none"}
            or carrier in {"speech", "mixed"} and receipt.get("audio_kind") != "speech"):
        raise ValueError("Confirm whether audio contains speech before choosing the reading route")
    duration = receipt.get("duration_seconds")
    if not finite_number(duration) or duration <= 0 or receipt.get("visuals_verified") is not True:
        raise ValueError("Video needs its actual duration and verified relevant visuals")
    if carrier in {"captions", "mixed"}:
        captions = receipt.get("captions", {})
        times = captions.get("sample_times", [])
        if (len(times) < 2 or any(not finite_number(t) or not 0 <= t <= duration for t in times)
                or times[0] > .25 or duration - times[-1] > .25
                or any(not 0 < b - a <= .250001 for a, b in zip(times, times[1:]))
                or captions.get("all_text_reviewed") is not True
                or captions.get("changes_reviewed") is not True
                or type(captions.get("unresolved_low_confidence")) is not int
                or captions["unresolved_low_confidence"] != 0
                or captions.get("unreadable_intervals") != []):
            raise ValueError("Captions need dense full-timeline coverage and resolved text/visual checks")
    if carrier in {"speech", "mixed"}:
        speech = receipt.get("speech", {})
        ranges = speech.get("reviewed_ranges", [])
        if (speech.get("method") not in {"asr", "listening"}
                or speech.get("recognition_verified") is not True or not ranges
                or any(not isinstance(r, list) or len(r) != 2
                       or any(not finite_number(t) for t in r) or not 0 <= r[0] < r[1] <= duration for r in ranges)):
            raise ValueError("Speech needs verified full-audio reading evidence")
        end = 0
        for start, stop in sorted(ranges):
            if start > end + .25:
                raise ValueError("Speech coverage has an unread interval")
            end = max(end, stop)
        if duration - end > .25:
            raise ValueError("Speech coverage ends before the source")
        if speech["method"] == "asr":
            texts = [re.sub(r"[\W_]+", "", s.get("text", "")).lower() for s in speech.get("segments", [])]
            if (not any(texts) or speech.get("suspicious_segments")
                    or (speech.get("expected_language") and speech.get("language") != speech["expected_language"])
                    or any(len(t) > 4 and n >= 3 for t, n in Counter(texts).items())):
                raise ValueError("Recognition quality is unresolved: repeated text, language or suspicious segments")
    return True


def validate_attempts(item, previous):
    """One initial recognition plus one materially different alternative, free by default."""
    attempts = item.get("reading_attempts", [])
    old = previous.get("reading_attempts", [])
    history = {}
    if attempts:
        path = item.get("reading_attempt_history_evidence")
        history = json.loads(Path(path).read_text()) if path else {}
        if history.get("source_key") != item["key"] or history.get("history_complete") is not True:
            raise ValueError("Reconcile this source's historical recognition attempts before another job")
    prior = history.get("prior_attempts", [])
    sealed = previous.get("reading_prior_attempts")
    if sealed is not None:
        if item.get("reading_prior_attempts") != sealed or prior != sealed:
            raise ValueError("Imported recognition history is sealed; a changed receipt cannot expand the budget")
    elif old and (not isinstance(prior, list) or len(prior) > len(old) or old[:len(prior)] != prior):
        raise ValueError("Cannot reclassify a new recognition attempt as existing history")
    if (not isinstance(attempts, list) or not isinstance(prior, list)
            or len(attempts) > max(2, len(prior)) or attempts[:len(old)] != old
            or attempts[:len(prior)] != prior):
        raise ValueError("Recognition attempt history is append-only and limited to two attempts")
    if attempts:
        item["reading_prior_attempts"] = json.loads(json.dumps(prior))
    limit = item.get("reading_cost_limit", 0)
    if (not finite_number(limit) or limit < 0
            or (limit and (not item.get("reading_cost_authorization") or not item.get("reading_cost_currency")))):
        raise ValueError("Paid recognition needs an explicit finite cost limit and human authorization")
    total = 0
    for attempt in attempts:
        cost = attempt.get("estimated_cost", 0)
        if (not attempt.get("engine") or not attempt.get("model") or not finite_number(cost) or cost < 0
                or (cost and attempt.get("currency") != item.get("reading_cost_currency"))):
            raise ValueError("Recognition attempts need an identified route and bounded cost/currency")
        total += cost
    if total > limit:
        raise ValueError("Recognition cost budget exhausted; report instead of starting another job")
    if len(attempts) == 2 and len(prior) < 2:
        first, second = attempts
        signature = lambda a: (a["model"], a.get("source_revision"))
        if signature(first) == signature(second) or not second.get("difference_evidence"):
            raise ValueError("Alternative recognition needs a different model or verified source revision and reason")


def item_plan(item, request, policy=None):
    """Plan the existing item's next step; never execute an external action."""
    if not in_scope(item, policy or {}):
        return {"action": "report", "reason": "outside_authorized_source_scope", "allow_external_retry": False}
    if item.get("status") in {"complete", "discarded"}:
        return {"action": "reconcile", "reason": "completed_source_dedup", "allow_external_retry": False}
    unknown = [k for k in ("save_outcome", "cleanup_outcome") if item.get(k) in {"pending", "unknown"}]
    if unknown or item.get("source_state") == "unknown":
        return {"action": "reconcile", "reason": "unknown_external_outcome", "stages": unknown,
                "allow_external_retry": False}
    conditions = ["user_clarification", "source_changed", "tool_changed", "manual_request"]
    if (request.get("resume_reason") not in conditions or not request.get("authorization")
            or ((item.get("status") == "needs_decision" or item.get("human_parked"))
                and request.get("resume_reason") != "user_clarification")):
        return {"action": "report", "gap": item.get("reading_blocker", {}).get("gap", item.get("reason", "Reading incomplete")),
                "resume_on": conditions, "allow_external_retry": False}
    if request.get("next_attempt"):
        path = item.get("reading_receipt")
        receipt = json.loads(Path(path).read_text()) if path else {}
        if (receipt.get("source_key") != item["key"] or receipt.get("carrier") not in {"speech", "mixed"}
                or receipt.get("audio_kind") != "speech" or not receipt.get("basis")
                or not Path(receipt.get("evidence_path", "")).is_file()):
            return {"action": "report", "gap": "Recognition requires observed speech; classify the actual carrier first",
                    "resume_on": conditions, "allow_external_retry": False}
        candidate = {**item, "reading_attempts": item.get("reading_attempts", []) + [request["next_attempt"]]}
        try:
            validate_attempts(candidate, item)
        except ValueError as error:
            return {"action": "report", "gap": str(error), "resume_on": conditions, "allow_external_retry": False}
    return {"action": "resume", "reason": request["resume_reason"], "reuse_source_key": item["key"],
            "reuse_note_url": item.get("note_url"), "allow_external_retry": bool(request.get("next_attempt"))}


def validate_mutation_outcomes(item, previous, incoming):
    """A readback must reconcile this operation, never an inherited prior receipt."""
    seen = previous.get("mutation_intent_ids", [])
    if "mutation_intent_ids" in incoming and incoming["mutation_intent_ids"] != seen:
        raise ValueError("Mutation intent history cannot be replaced")
    seen = list(seen)
    for stage in ("save", "cleanup"):
        field, intent = stage + "_outcome", stage + "_intent_id"
        old, new = previous.get(field), item.get(field)
        if new is not None and new not in {"pending", "unknown", "verified", "not_applied"}:
            raise ValueError("Unknown external-outcome state")
        if old in {"pending", "unknown"}:
            if item.get(intent) != previous.get(intent):
                raise ValueError("Cannot replace an unresolved mutation intent")
            if new != old and new != "unknown":
                path = incoming.get("reconciliation_evidence")
                receipt = json.loads(Path(path).read_text()) if path else {}
                if (new not in {"verified", "not_applied"} or not previous.get(intent)
                        or receipt.get("source_key") != item["key"] or receipt.get("stage") != stage
                        or receipt.get("intent_id") != previous[intent] or receipt.get("outcome") != new
                        or not Path(receipt.get("evidence_path", "")).is_file()):
                    raise ValueError("Reconciliation needs a new source/stage/current-intent readback receipt")
        elif new in {"pending", "unknown"} and new != old:
            identity = item.get(intent)
            if not isinstance(identity, str) or not identity.strip() or identity in seen:
                raise ValueError("Record a unique mutation intent before the external request")
            seen.append(identity)
    if seen:
        item["mutation_intent_ids"] = seen


def ready(item, policy=None):
    if not in_scope(item, policy or {}):
        raise ValueError("Item or folder membership is outside the authorized cleanup scope")
    receipt = json.loads(Path(item["photos_receipt"]).read_text()) if item.get("route") == "photos" else None
    image_photos = receipt is not None and receipt.get("kind") in {"image", "live_photo"}
    if not all(item.get(k) is True for k in ("archive_verified", "coverage_complete")):
        raise ValueError("Archive and reading/media coverage must both be verified")
    if any(item.get(k) in {"pending", "unknown"} for k in ("save_outcome", "cleanup_outcome")):
        raise ValueError("Reconcile unknown external outcomes before cleanup")
    if not image_photos:
        if item.get("index_verified") is not True:
            raise ValueError("Index readback must be verified for this route")
        if not str(item.get("index_url", "")).startswith("https://app.notion.com/"):
            raise ValueError("Missing verified index URL")
    if item["key"].startswith("bilibili:"):
        folders = item.get("folder_ids", [])
        if (not isinstance(folders, list) or not folders
                or any(not isinstance(f, str) or not re.fullmatch(r"[0-9]+", f) for f in folders)
                or len(set(folders)) != len(folders)):
            raise ValueError("Bilibili cleanup needs exact observed owned-folder IDs")
    if item.get("route") == "knowledge":
        validate_reading(item, required=item.get("reading_contract_required", False))
        if not str(item.get("note_url", "")).startswith("https://app.notion.com/"):
            raise ValueError("Missing canonical note URL")
    elif item.get("route") == "photos":
        if receipt.get("kind") == "live_photo" and receipt.get("live_pairs_verified") is not True:
            raise ValueError("Live Photo still/motion pairs must be independently verified")
        reference = receipt.get("source", "")
        source = urlsplit(reference if "://" in reference else "https://" + reference)
        platform, identity = item["key"].split(":", 1)
        host = urlsplit(URL_BASES[platform]).hostname.removeprefix("www.")
        expected = receipt.get("expected_count")
        if (receipt.get("complete") is not True or receipt.get("managed_originals_verified") is not True
                or type(expected) is not int or expected < 1
                or not receipt.get("assets")
                or (source.hostname or "").removeprefix("www.") != host
                or identity not in source.path.split("/")):
            raise ValueError("Photos receipt is incomplete or belongs to another source")
        assets = receipt["assets"]
        manifest = receipt.get("source_assets")
        if manifest is None:
            if len(assets) != expected:
                raise ValueError("Photos receipt does not cover the full source count")
        else:
            by_id = {asset["asset_id"]: asset for asset in assets}
            if (len(by_id) != len(assets) or len(manifest) != expected
                    or [entry.get("index") for entry in manifest] != list(range(1, expected + 1))
                    or {entry.get("asset_id") for entry in manifest} != set(by_id)):
                raise ValueError("Photos source-to-asset mapping is incomplete")
            for entry in manifest:
                asset = by_id[entry["asset_id"]]
                if any(entry.get(field) != asset[field] for field in ("sha256", "bytes")):
                    raise ValueError("Photos source mapping does not match a verified original")
        library = Path(receipt["library"]).resolve() / "originals"
        for asset in receipt["assets"]:
            path = Path(asset["managed_path"])
            if (not path.resolve().is_relative_to(library) or path.is_symlink()
                    or path.stat().st_size != asset["bytes"]
                    or hashlib.sha256(path.read_bytes()).hexdigest() != asset["sha256"]):
                raise ValueError("Managed Photos original no longer matches the receipt")
    else:
        raise ValueError("Unresolved content route")
    return True


def explicit_discard_only(run):
    """Verified human discards do not spend the automatic recovery allowance."""
    changes = run.get("events", [])
    if run.get("status") != "finished" or not changes:
        return False
    for event in changes:
        authorization = event.get("discard_authorization", {})
        if (event.get("status") != "discarded" or event.get("route") != "discard"
                or event.get("cleanup_verified") is not True
                or event.get("source_state") not in {"not_favorited", "not_in_collection", "not_in_scoped_folders"}
                or authorization.get("kind") != "explicit_user_discard"
                or not event.get("key") or authorization.get("source_key") != event["key"]
                or not str(authorization.get("request_text", "")).strip()):
            return False
    return True


def brief_current(runs, day):
    results = [r for r in runs if r.get("date") == day and r.get("status") == "finished"
               and r.get("kind", "collect") in {"collect", "repair"}]
    if not results:
        return False
    latest = max(results, key=lambda r: datetime.fromisoformat(r.get("finished_at", r["started_at"])))
    reports = [r for r in results if r.get("brief_date") == day and r.get("brief_url") and r.get("brief_delivered") is not False]
    if latest in reports:
        return True
    result_at = datetime.fromisoformat(latest.get("finished_at", latest["started_at"]))
    return any(datetime.fromisoformat(r[stamp]) >= result_at
               for r in reports for stamp in ("brief_updated_at", "brief_verified_at") if r.get(stamp))


def nonblocking_unavailable(snapshot):
    """A scoped human-confirmed empty list is a notice, never full coverage."""
    visibility = snapshot.get("visibility", {})
    return (snapshot.get("platform") == "xhs"
            and bool(ACCOUNTS["xhs"])
            and snapshot.get("account") == ACCOUNTS["xhs"]
            and type(snapshot.get("displayed_total")) is int and snapshot["displayed_total"] > 0
            and snapshot.get("accessible_count") == 0
            and snapshot.get("pagination_complete") is True
            and snapshot.get("coverage_complete") is False
            and visibility.get("status") == "content_unavailable"
            and visibility.get("non_blocking") is True
            and visibility.get("reason_confirmed") is False
            and visibility.get("basis") == "user_confirmed_empty_collection"
            and visibility.get("confirmed_displayed_total") == snapshot["displayed_total"]
            and bool(visibility.get("user_confirmation")))


def brief_content_update(page_content, section, day, run_id):
    """Plan one narrow edit; repeated delivery never overwrites user edits."""
    marker = "saved-content-review:" + day
    if marker not in section or run_id not in section:
        raise ValueError("Daily section needs its exact date marker and original run ID")
    if marker in page_content:
        if page_content.count(marker) != 1 or run_id not in page_content:
            raise ValueError("Existing daily marker is ambiguous; reconcile before writing")
        return None
    placeholder = "## 收藏与录音\n\n本期未收到 Mac 本地任务的已核验结果；这不等于没有新增。"
    if page_content.count(placeholder) != 1:
        raise ValueError("Expected unique daily placeholder is absent; preserve existing content")
    return {"old_str": placeholder, "new_str": section.strip()}


def discovered_after_scan(item, parent):
    if item.get("first_seen_run") == parent["id"] and item.get("first_seen_phase") in {"after", "audit"}:
        return True
    first, finished = item.get("first_seen_at"), parent.get("finished_at")
    return bool(first and finished and datetime.fromisoformat(first) > datetime.fromisoformat(finished))


def due(data, policy):
    """Choose bounded local recovery work; this does not wake the Mac or start a run."""
    instant = now()
    day = instant.date().isoformat()
    dates = policy["dates"]
    continuous = policy.get("mode") == "continuous"
    if continuous:
        start = datetime.fromisoformat(policy.get("start_date", dates[0])).date()
        if instant.date() < start:
            return {"action": "none", "reason": "before_authorized_start"}
        dates = [(start + timedelta(days=n)).isoformat()
                 for n in range((instant.date() - start).days + 1)]
    if day not in dates:
        return {"action": "none", "reason": "outside_authorized_trial"}
    runs = list(data["runs"].values())
    collections = [r for r in runs if r.get("kind", "collect") == "collect"]
    minute = instant.hour * 60 + instant.minute
    missing = [d for d in dates if (d < day or (d == day and minute >= 240))
               and not any(r["date"] == d and r["status"] == "finished" for r in collections)]
    today = [r for r in collections if r["date"] == day and r["status"] == "finished"]
    brief_hour, brief_minute = map(int, policy.get("brief_at", "04:00").split(":"))
    brief_due = minute >= brief_hour * 60 + brief_minute and not brief_current(runs, day)
    result = {"missing_dates": missing, "brief_due": brief_due, "cleanup_holds": data.get("cleanup_holds", {})}
    if any(r["status"] == "running" and instant - datetime.fromisoformat(r["started_at"]) < timedelta(minutes=90) for r in runs):
        return {**result, "action": "none", "reason": "active_lease"}
    end_hour, end_minute = map(int, policy.get("primary_window_end", "07:30").split(":"))
    primary = 240 <= minute < end_hour * 60 + end_minute
    recovery = policy.get("recovery", {})
    if recovery.get("automatic") is False and not primary:
        if 235 <= minute < 240:
            return {**result, "action": "none", "reason": "early_execution_window",
                    "wait_until": instant.replace(hour=4, minute=0, second=0, microsecond=0).isoformat()}
        return {**result, "action": "none", "reason": "daytime_recovery_disabled"}
    slots = [480] + [int(h) * 60 for h in recovery.get("hours", [10, 16, 22])]
    in_window = primary or any(start <= minute < start + 90 for start in slots)
    final_day = not continuous and day == dates[-1]
    if not in_window or (final_day and minute >= 570):
        collect_hour, collect_minute = map(int, policy.get("collect_at", "04:00").split(":"))
        starts = [(collect_hour, collect_minute)]
        if not final_day:
            starts += [(int(hour), 0) for hour in recovery.get("hours", [10, 16, 22])]
        early = [instant.replace(hour=hour, minute=part, second=0, microsecond=0)
                 for hour, part in starts
                 if 0 < (instant.replace(hour=hour, minute=part, second=0, microsecond=0) - instant).total_seconds() <= 300]
        if early:
            return {**result, "action": "none", "reason": "early_execution_window",
                    "wait_until": min(early).isoformat()}
        return {**result, "action": "none", "reason": "outside_execution_windows"}
    if not today:
        return {**result, "action": "collect", "trigger": "scheduled" if primary else "catchup",
                "max_work_minutes": 60 if primary else recovery.get("max_work_minutes", 30)}
    parent = max(today, key=lambda r: r["started_at"])
    pending = [k for k, item in data["items"].items() if item["status"] in {"pending", "pending_read", "failed", "archived"}
               and not item.get("historical_backlog") and not item.get("test_sample") and not item.get("human_parked")
               and in_scope({"key": k, **item}, policy)
               and not discovered_after_scan(item, parent)]
    missing_platforms = sorted(set(policy["accounts"]) - set(parent.get("platforms", {})))
    repairs = [r for r in runs if r.get("kind") == "repair" and r["date"] == day
               and not explicit_discard_only(r)]
    needs_repair = pending or missing_platforms or parent.get("retry_needed")
    if not primary and needs_repair and len(repairs) < recovery.get("max_repair_runs_per_day", 1):
        return {**result, "action": "repair", "trigger": "catchup", "repair_of": parent["id"],
                "retry_keys": pending, "missing_platforms": missing_platforms,
                "max_work_minutes": recovery.get("max_work_minutes", 30)}
    return {**result, "action": "brief" if brief_due else "none",
            "reason": "repair_budget_used" if needs_repair and repairs else "daily_collection_finished", "run_id": parent["id"]}


def validate_execution_audit(audit, run):
    """Validate optional stage evidence without replacing original run receipts."""
    if audit.get("version") != 1 or audit.get("run_id") != run["id"] or audit.get("date") != run["date"]:
        raise ValueError("Execution audit must match the original run and date")
    counts = audit.get("counts", {})
    for field in ("discovered", "fully_read", "saved_verified", "unfavorited", "remaining"):
        if field not in counts or (counts[field] is not None and
                (type(counts[field]) is not int or counts[field] < 0)):
            raise ValueError("Audit counts must be nonnegative integers or null for unknown")
    stages = audit.get("stages")
    if not isinstance(stages, list) or not stages:
        raise ValueError("Execution audit needs observed stages")
    identities = set()
    for stage in stages:
        identity = (stage.get("id"), stage.get("platform"), stage.get("source_key"))
        if (not isinstance(identity[0], str) or not identity[0].strip()
                or identity[1] not in ("xhs", "douyin", "bilibili", None)
                or (identity[2] is not None and not isinstance(identity[2], str))
                or identity in identities):
            raise ValueError("Audit stages need unique identities and a known platform")
        identities.add(identity)
        if stage.get("source_key") is not None:
            platform, _, source_id = stage["source_key"].partition(":")
            if platform != stage["platform"] or not re.fullmatch(ID_PATTERNS.get(platform, r"(?!)"), source_id):
                raise ValueError("Audit source identity must match its platform")
        if stage.get("status") not in {"success", "failed", "unknown", "not_attempted"}:
            raise ValueError("Unknown execution stage status")
        times = []
        for field in ("started_at", "ended_at"):
            if field not in stage:
                raise ValueError("Stage times must be explicit, using null when unknown")
            value = stage[field]
            instant = datetime.fromisoformat(value) if isinstance(value, str) else None
            if value is not None and (instant is None or instant.utcoffset() is None):
                raise ValueError("Stage times need timezone offsets or null")
            times.append(instant)
        if all(t is not None for t in times) and times[1] < times[0]:
            raise ValueError("Stage end precedes its start")
        if type(stage.get("cause_proven")) is not bool or not isinstance(stage.get("next_step"), str):
            raise ValueError("Stage cause and next step must be explicit")
        if stage["status"] == "failed" and not str(stage.get("error") or "").strip():
            raise ValueError("A failed stage needs its actual error")
        evidence = stage.get("evidence", [])
        if not isinstance(evidence, list) or (stage["status"] in {"success", "failed"} and not evidence):
            raise ValueError("A resolved stage needs checkable evidence")
        for entry in evidence:
            path = Path(entry["path"])
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != entry.get("sha256"):
                raise ValueError("Stage evidence is missing or changed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("command", choices=["begin", "inventory", "record", "ready", "plan", "finish", "brief", "audit", "status", "due"])
    parser.add_argument("--run")
    parser.add_argument("--trigger", choices=["manual", "scheduled", "catchup"], default="manual")
    parser.add_argument("--repair-of", help="Begin a bounded repair of a finished/interrupted collection run from today")
    parser.add_argument("--file", type=Path)
    parser.add_argument("--key")
    args = parser.parse_args()
    incoming = json.loads(args.file.read_text()) if args.file else None
    with ledger(args.root) as data:
        instant = now().isoformat()
        if args.command == "begin":
            if args.trigger != "manual":
                decision = due(data, json.loads((args.root / "trial.json").read_text()))
                expected = "repair" if args.repair_of else "collect"
                if (decision["action"] != expected or decision.get("trigger") != args.trigger
                        or (args.repair_of and decision.get("repair_of") != args.repair_of)):
                    raise ValueError("Automatic run is not due: " + decision.get("reason", decision["action"]))
            day = now().date().isoformat()
            if args.repair_of:
                parent = data["runs"][args.repair_of]
                parent_status = parent["status"]
                if (parent_status == "running"
                        and now() - datetime.fromisoformat(parent["started_at"]) >= timedelta(minutes=90)):
                    parent_status = "interrupted"
                if (parent["date"] != day or parent_status not in {"finished", "interrupted"}
                        or parent.get("kind") in {"repair", "setup"}):
                    raise ValueError("Repairs require today's finished/interrupted collection run")
            live = [r for r in data["runs"].values() if r["status"] == "running"]
            for run in live:
                if now() - datetime.fromisoformat(run["started_at"]) < timedelta(minutes=90):
                    raise ValueError("A collection run is active; reconcile it instead of overlapping")
                run.update(status="interrupted", needs_reconciliation=True)
            completed = [r for r in data["runs"].values() if r["date"] == day and r["status"] == "finished"
                         and r.get("kind", "collect") == "collect"]
            if completed and not args.repair_of:
                result = {"already_finished": True, "run": completed[-1]}
            else:
                run_id = now().strftime("%Y%m%dT%H%M%S%f")
                run = {"id": run_id, "date": day, "started_at": instant, "status": "running", "platforms": {}, "events": [],
                       "kind": "repair" if args.repair_of else "collect", "trigger": args.trigger,
                       "scheduled_for": day + "T04:00:00+08:00"}
                if args.repair_of:
                    run["repair_of"] = args.repair_of
                data["runs"][run_id] = run
                result = {"run": run, "reconcile_interrupted": [r["id"] for r in live]}
        elif args.command == "status":
            result = data if not args.run else data["runs"][args.run]
        elif args.command == "due":
            result = due(data, json.loads((args.root / "trial.json").read_text()))
        elif args.command == "plan":
            result = item_plan(data["items"][args.key], incoming or {}, json.loads((args.root / "trial.json").read_text()))
        elif args.command == "ready":
            platform = args.key.split(":", 1)[0]
            if platform in data.get("cleanup_holds", {}):
                raise ValueError("Source cleanup is on hold: " + data["cleanup_holds"][platform])
            result = {"key": args.key, "cleanup_ready": ready(data["items"][args.key], json.loads((args.root / "trial.json").read_text()))}
        elif args.command == "audit":
            run = data["runs"][args.run]
            if "execution_audit" in incoming:
                validate_execution_audit(incoming["execution_audit"], run)
            if incoming["status"] not in {"pass", "attention", "blocked"}:
                raise ValueError("Unknown audit status")
            report = Path(incoming["report_path"])
            if not report.is_file():
                raise ValueError("Save the audit report before recording it")
            for platform, snapshot in incoming.get("channel_observations", {}).items():
                original = run.get("platforms", {}).get(platform, {})
                if (platform != "xhs" or not nonblocking_unavailable(snapshot)
                        or any(snapshot.get(k) != original.get(k) for k in
                               ("account", "displayed_total", "accessible_count", "pagination_complete", "coverage_complete"))):
                    raise ValueError("Visibility reclassification must match this run's unchanged source observation")
            holds = incoming.get("cleanup_holds", {})
            if any(p not in ACCOUNTS or (reason is not None and (not isinstance(reason, str) or not reason.strip()))
                   for p, reason in holds.items()):
                raise ValueError("Cleanup holds need an authorized platform and a reason, or null to clear")
            for platform, reason in holds.items():
                if reason is None:
                    data.setdefault("cleanup_holds", {}).pop(platform, None)
                else:
                    data.setdefault("cleanup_holds", {})[platform] = reason
            run.setdefault("audits", []).append({**incoming, "at": instant})
            result = {"audit": run["audits"][-1], "cleanup_holds": data.get("cleanup_holds", {})}
        elif args.command == "brief":
            run = data["runs"][args.run]
            if not str(incoming.get("brief_url", "")).startswith("https://app.notion.com/"):
                raise ValueError("Missing verified brief URL")
            if run["status"] != "finished" or incoming.get("brief_date") != run["date"]:
                raise ValueError("Daily delivery must match the finished run's original date")
            if not Path(incoming.get("brief_report_path", "")).is_file():
                raise ValueError("Save the independently checked daily section before recording delivery")
            fields = {k: incoming[k] for k in ("brief_url", "brief_date", "brief_report_path", "brief_delivery_path") if k in incoming}
            if not (all(run.get(k) == v for k, v in fields.items()) and run.get("brief_delivered") is True):
                run.update(fields, brief_delivered=True, brief_delivery_status="delivered", brief_updated_at=instant)
                run.setdefault("counts", {})["brief_delivered"] = True
            result = run
        else:
            run = data["runs"][args.run]
            if run["status"] != "running":
                raise ValueError("Run is no longer active")
            if now() - datetime.fromisoformat(run["started_at"]) >= timedelta(minutes=90):
                raise ValueError("Run lease expired; begin a new run and reconcile")
            if args.command == "inventory":
                platform = incoming["platform"]
                if not ACCOUNTS.get(platform) or incoming["account"] != ACCOUNTS[platform]:
                    raise ValueError("Account does not match the authorized source")
                items = incoming["items"]
                if len({str(row["id"]) for row in items}) != len(items) or incoming["accessible_count"] != len(items):
                    raise ValueError("Inventory count and unique source IDs do not match")
                if incoming.get("phase", "before") not in {"before", "after", "audit"}:
                    raise ValueError("Inventory phase must be before, after or audit")
                if incoming.get("visibility", {}).get("non_blocking") and not nonblocking_unavailable(incoming):
                    raise ValueError("Nonblocking invisibility needs the matching account, empty-list evidence and human confirmation")
                run["platforms"][platform] = {k: v for k, v in incoming.items() if k != "items"}
                run.setdefault("inventories", {}).setdefault(platform, []).append({**incoming, "at": instant})
                for row in items:
                    identity = str(row["id"])
                    pattern = ID_PATTERNS[platform]
                    if not re.fullmatch(pattern, identity):
                        raise ValueError("Invalid stable source ID")
                    key = platform + ":" + identity
                    item = data["items"].setdefault(key, {"key": key, "first_seen_at": instant, "status": "pending",
                                                        "first_seen_run": args.run, "first_seen_phase": incoming.get("phase", "before")})
                    url = URL_BASES[platform] + identity
                    item.update(title=row.get("title", ""), url=url, last_seen_at=instant)
                    if platform == "bilibili":
                        folders = row.get("folder_ids", [])
                        if not folders or any(not isinstance(f, str) or not re.fullmatch(r"[0-9]+", f) for f in folders):
                            raise ValueError("Bilibili inventory needs observed owned-folder IDs")
                        item["observed_folder_ids"] = list(dict.fromkeys(folders))
                        if (run.get("kind") != "repair" and incoming.get("phase", "before") == "before") or not item.get("folder_ids"):
                            item["folder_ids"] = list(dict.fromkeys(folders))
                result = {"observed": len(items), "pending": [i for i in data["items"].values() if i["status"] not in {"complete", "discarded"}]}
            elif args.command == "record":
                key = incoming["key"]
                if not re.fullmatch(r"(?:xhs:[0-9a-f]{24}|douyin:[0-9]+|bilibili:BV[0-9A-Za-z]{10})", key):
                    raise ValueError("Item is outside the authorized platform scope")
                if incoming["status"] not in STATES:
                    raise ValueError("Unknown item status")
                if key not in data["items"] and not str(incoming.get("index_url", "")).startswith("https://app.notion.com/"):
                    raise ValueError("An item absent from live inventory needs an existing queue record")
                previous = data["items"].get(key, {"key": key, "first_seen_at": instant, "discovered_from_queue": True})
                item = {**previous, **incoming, "updated_at": instant}
                validate_attempts(item, previous)
                validate_mutation_outcomes(item, previous, incoming)
                if item.get("route") == "knowledge" and item["status"] in {"archived", "complete"}:
                    if previous.get("status") != "complete":
                        item["reading_contract_required"] = True
                    validate_reading(item, required=item.get("reading_contract_required", False))
                if item["status"] == "complete":
                    ready(item, json.loads((args.root / "trial.json").read_text()))
                    if item.get("cleanup_verified") is not True or item.get("source_state") not in ["not_favorited", "not_in_collection", "not_in_scoped_folders"]:
                        raise ValueError("Source state must be reloaded and verified before completion")
                if item["status"] == "discarded":
                    if not in_scope(item, json.loads((args.root / "trial.json").read_text())):
                        raise ValueError("Discard membership is outside the authorized cleanup scope")
                    authorization = item.get("discard_authorization", {})
                    if (item.get("route") != "discard" or authorization.get("kind") != "explicit_user_discard"
                            or authorization.get("source_key") != key or not str(authorization.get("request_text", "")).strip()):
                        raise ValueError("Discard needs an explicit human request for this exact source")
                    if item.get("cleanup_verified") is not True or item.get("source_state") not in ["not_favorited", "not_in_collection", "not_in_scoped_folders"]:
                        raise ValueError("Discard source state must be reloaded and verified")
                data["items"][key] = item
                run["events"].append({"at": instant, **incoming})
                result = item
            else:
                if set(incoming or {}) & {"id", "date", "started_at", "kind", "trigger", "repair_of", "scheduled_for", "events", "inventories", "platforms", "audits"}:
                    raise ValueError("Run identity and original evidence cannot be overwritten by finish")
                run.update(incoming or {})
                run.update(status="finished", finished_at=instant)
                result = run
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, AssertionError) as error:
        raise SystemExit(str(error))
