#!/usr/bin/env python3
"""Atomic progress ledger for agent-observed saved-content runs; no remote writes."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta
import fcntl
import hashlib
import json
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


def ready(item, policy=None):
    if not in_scope(item, policy or {}):
        raise ValueError("Item or folder membership is outside the authorized cleanup scope")
    receipt = json.loads(Path(item["photos_receipt"]).read_text()) if item.get("route") == "photos" else None
    image_photos = receipt is not None and receipt.get("kind") in {"image", "live_photo"}
    if not all(item.get(k) is True for k in ("archive_verified", "coverage_complete")):
        raise ValueError("Archive and reading/media coverage must both be verified")
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("command", choices=["begin", "inventory", "record", "ready", "finish", "brief", "audit", "status", "due"])
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
        elif args.command == "ready":
            platform = args.key.split(":", 1)[0]
            if platform in data.get("cleanup_holds", {}):
                raise ValueError("Source cleanup is on hold: " + data["cleanup_holds"][platform])
            result = {"key": args.key, "cleanup_ready": ready(data["items"][args.key], json.loads((args.root / "trial.json").read_text()))}
        elif args.command == "audit":
            run = data["runs"][args.run]
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
