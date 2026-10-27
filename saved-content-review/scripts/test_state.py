#!/usr/bin/env python3
"""Offline regression checks for trial recovery and source-cleanup safeguards."""
import contextlib
import copy
from datetime import datetime, timedelta
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
import state


class StateTests(unittest.TestCase):
    def test_image_photos_complete_without_queue_but_keep_archive_gates(self):
        import hashlib
        run_id = self.call("begin")["run"]["id"]
        self.call("inventory", {"platform": "douyin", "account": state.ACCOUNTS["douyin"],
                  "items": [{"id": "123"}], "accessible_count": 1}, "--run", run_id)
        original = self.root / "library/originals/A/photo.jpg"
        original.parent.mkdir(parents=True)
        original.write_bytes(b"offline image original")
        asset = {"asset_id": "A/L0/001", "managed_path": str(original),
                 "bytes": original.stat().st_size, "sha256": hashlib.sha256(original.read_bytes()).hexdigest()}
        receipt = {"source": "www.douyin.com/note/123", "kind": "image", "complete": True,
                   "managed_originals_verified": True, "expected_count": 1,
                   "library": str(self.root / "library"), "assets": [asset]}
        path = self.root / "photos.json"
        path.write_text(json.dumps(receipt))
        item = {"key": "douyin:123", "route": "photos", "status": "complete",
                "archive_verified": True, "coverage_complete": True, "photos_receipt": str(path),
                "cleanup_verified": True, "source_state": "not_in_collection"}
        saved = self.call("record", item, "--run", run_id)
        self.assertNotIn("index_url", saved)
        self.assertNotIn("index_verified", saved)
        self.assertTrue(state.ready(saved, self.policy))
        for field in ("archive_verified", "coverage_complete"):
            with self.assertRaises(ValueError):
                state.ready({**saved, field: False}, self.policy)
        path.write_text(json.dumps({**receipt, "source": "unrelated.example/note/123"}))
        with self.assertRaises(ValueError):
            state.ready(saved, self.policy)
        path.write_text(json.dumps(receipt))
        original.write_bytes(b"changed bytes")
        with self.assertRaises(ValueError):
            state.ready(saved, self.policy)

    def test_live_photo_needs_verified_pairs_and_both_managed_originals(self):
        import hashlib
        assets = []
        library = self.root / "live.photoslibrary"
        for name, content in (("still.jpg", b"still fixture"), ("motion.mov", b"motion fixture")):
            p = library / "originals/A" / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(content)
            assets.append({"asset_id": name, "managed_path": str(p), "bytes": len(content),
                           "sha256": hashlib.sha256(content).hexdigest()})
        receipt = {"source": "www.douyin.com/note/123", "kind": "live_photo", "complete": True,
                   "managed_originals_verified": True, "expected_count": 2, "library": str(library),
                   "assets": assets, "live_pairs_verified": False}
        path = self.root / "live-receipt.json"
        path.write_text(json.dumps(receipt))
        item = {"key": "douyin:123", "route": "photos", "archive_verified": True,
                "coverage_complete": True, "photos_receipt": str(path)}
        with self.assertRaises(ValueError):
            state.ready(item, self.policy)
        receipt["live_pairs_verified"] = True
        path.write_text(json.dumps(receipt))
        self.assertTrue(state.ready(item, self.policy))
        Path(assets[1]["managed_path"]).unlink()
        with self.assertRaises((ValueError, OSError)):
            state.ready(item, self.policy)

    def test_video_and_knowledge_still_require_queue_acceptance(self):
        import hashlib
        p = self.root / "library/originals/A/video.mov"
        p.parent.mkdir(parents=True)
        p.write_bytes(b"offline video original")
        receipt = {"source": "www.douyin.com/video/123", "kind": "video", "complete": True,
                   "managed_originals_verified": True, "expected_count": 1, "library": str(self.root / "library"),
                   "assets": [{"asset_id": "video", "managed_path": str(p), "bytes": p.stat().st_size,
                               "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}]}
        path = self.root / "video-receipt.json"
        path.write_text(json.dumps(receipt))
        video = {"key": "douyin:123", "route": "photos", "archive_verified": True,
                 "coverage_complete": True, "photos_receipt": str(path)}
        knowledge = {"key": "douyin:123", "route": "knowledge", "title": "图像技术文章",
                     "archive_verified": True, "coverage_complete": True,
                     "note_url": "https://app.notion.com/p/article"}
        for item in (video, knowledge):
            with self.assertRaises(ValueError):
                state.ready(item, self.policy)
            self.assertTrue(state.ready({**item, "index_verified": True,
                "index_url": "https://app.notion.com/p/existing-row"}, self.policy))
        del receipt["kind"]  # Unknown historical media is never assumed to be an image.
        path.write_text(json.dumps(receipt))
        with self.assertRaises(ValueError):
            state.ready(video, self.policy)

    def test_nonblocking_visibility_does_not_suppress_new_readable_ids(self):
        run = self.call("begin")["run"]
        run_id = run["id"]
        snapshot = {"platform": "xhs", "account": state.ACCOUNTS["xhs"], "items": [],
                    "displayed_total": 2, "accessible_count": 0, "unknown_count": 2,
                    "pagination_complete": True, "coverage_complete": False,
                    "visibility": {"status": "content_unavailable", "non_blocking": True,
                                   "reason_confirmed": False, "basis": "user_confirmed_empty_collection",
                                   "confirmed_displayed_total": 2, "user_confirmation": "User checked the empty official collection"}}
        self.assertTrue(state.nonblocking_unavailable(snapshot))
        self.call("inventory", snapshot, "--run", run_id)
        changed = copy.deepcopy(snapshot)
        changed["displayed_total"] = 3
        self.reject_unchanged("inventory", changed, "--run", run_id)
        changed["accessible_count"] = 1
        changed["items"] = [{"id": "a" * 24}]
        del changed["visibility"]
        self.call("inventory", changed, "--run", run_id)
        self.assertEqual(self.call("status")["items"]["xhs:" + "a" * 24]["status"], "pending")
        self.assertFalse(state.nonblocking_unavailable(changed))
        # A rejected channel checkpoint never prevents a different channel's checkpoint.
        self.call("inventory", {"platform": "douyin", "account": state.ACCOUNTS["douyin"],
                               "items": [], "accessible_count": 0, "displayed_total": 0,
                               "pagination_complete": True, "coverage_complete": True}, "--run", run_id)
        self.assertIn("douyin", self.call("status", None, "--run", run_id)["platforms"])

    def test_pending_daily_delivery_and_idempotent_late_receipt(self):
        run_id = self.call("begin")["run"]["id"]
        self.call("finish", {"brief_delivered": False, "counts": {"notes_created": 0, "brief_delivered": False}}, "--run", run_id)
        before = self.call("status", None, "--run", run_id)
        self.assertFalse(state.brief_current([before], before["date"]))
        report = self.root / "brief.md"
        report.write_text("Independently read back the existing daily section")
        receipt = {"brief_url": "https://app.notion.com/p/daily", "brief_date": before["date"],
                   "brief_report_path": str(report)}
        self.reject_unchanged("brief", {**receipt, "brief_date": "2026-10-17"}, "--run", run_id)
        delivered = self.call("brief", receipt, "--run", run_id)
        repeated = self.call("brief", receipt, "--run", run_id)
        self.assertEqual(delivered, repeated)
        self.assertTrue(delivered["brief_delivered"])
        self.assertTrue(delivered["counts"]["brief_delivered"])
        self.assertEqual(delivered["finished_at"], before["finished_at"])
        self.assertEqual(delivered["events"], [])
        self.assertTrue(state.brief_current([delivered], delivered["date"]))

    def test_daily_section_update_preserves_other_content_and_user_edits(self):
        old = "## 收藏与录音\n\n本期未收到 Mac 本地任务的已核验结果；这不等于没有新增。"
        surrounding = "News and user edits\n\n" + old + '\n\n## Other\n<file source="retained">Attachment</file>'
        section = "## 收藏与录音\n\nsaved-content-review:2026-10-18 run-original\n\nNo new archive; XHS unavailable."
        change = state.brief_content_update(surrounding, section, "2026-10-18", "run-original")
        saved = surrounding.replace(change["old_str"], change["new_str"], 1)
        self.assertTrue(saved.startswith("News and user edits\n\n"))
        self.assertTrue(saved.endswith('## Other\n<file source="retained">Attachment</file>'))
        self.assertIsNone(state.brief_content_update(saved, section, "2026-10-18", "run-original"))
        self.assertIsNone(state.brief_content_update(saved + "\nUser addition", section, "2026-10-18", "run-original"))
        self.assertEqual(saved.count("saved-content-review:2026-10-18"), 1)
        with self.assertRaises(ValueError):
            state.brief_content_update(saved, section.replace("run-original", "other-run"), "2026-10-18", "other-run")

    def setUp(self):
        self.accounts_patch = patch.object(state, "ACCOUNTS", {"xhs": "fixture-xhs", "douyin": "fixture-douyin", "bilibili": "fixture-bilibili"})
        self.accounts_patch.start()
        self.temp = tempfile.TemporaryDirectory(prefix="saved-content-state-test-")
        self.root = Path(self.temp.name)
        self.clock = datetime(2026, 10, 18, 4, tzinfo=state.TZ)
        self.clock_patch = patch.object(state, "now", lambda: self.clock)
        self.clock_patch.start()
        self.policy = {"dates": ["2026-10-18", "2026-10-19", "2026-10-20"],
                       "accounts": state.ACCOUNTS,
                       "recovery": {"hours": [10, 16, 22], "max_work_minutes": 30, "max_repair_runs_per_day": 1}}
        (self.root / "trial.json").write_text(json.dumps(self.policy))
        self.serial = 0

    def tearDown(self):
        self.accounts_patch.stop()
        self.clock_patch.stop()
        self.temp.cleanup()

    def call(self, command, incoming=None, *args):
        self.serial += 1
        self.clock += timedelta(microseconds=1)
        argv = ["state.py", "--root", str(self.root), command, *args]
        if incoming is not None:
            path = self.root / f"input-{self.serial}.json"
            path.write_text(json.dumps(incoming))
            argv += ["--file", str(path)]
        output = io.StringIO()
        with patch.object(sys, "argv", argv), contextlib.redirect_stdout(output):
            state.main()
        return json.loads(output.getvalue())

    def reject_unchanged(self, command, incoming=None, *args):
        path = self.root / "state.json"
        before = path.read_bytes()
        with self.assertRaises((ValueError, KeyError)):
            self.call(command, incoming, *args)
        self.assertEqual(before, path.read_bytes())

    def finished(self, day="2026-10-18"):
        return {"id": "original", "date": day, "kind": "collect", "status": "finished",
                "started_at": day + "T04:00:00+08:00", "platforms": {p: {} for p in state.ACCOUNTS}}

    def data(self, run=None, items=None):
        return {"schema": 1, "runs": {run["id"]: run} if run else {}, "items": items or {}}

    def test_code_status_mode_disables_daytime_models_and_limits_night(self):
        self.policy['recovery']['automatic'] = False
        self.policy['primary_window_end'] = '05:30'
        self.assertEqual(state.due(self.data(), self.policy)['action'], 'collect')
        for hour, minute in [(5, 30), (8, 0), (10, 0), (16, 0), (22, 0)]:
            self.clock = self.clock.replace(hour=hour, minute=minute)
            self.assertEqual(state.due(self.data(), self.policy)['action'], 'none')

    def test_missed_run_windows_and_trial_expiry(self):
        empty = self.data()
        self.assertEqual(state.due(empty, self.policy)["max_work_minutes"], 60)
        self.clock = self.clock.replace(hour=8)
        morning = state.due(empty, self.policy)
        self.assertEqual((morning["action"], morning["trigger"], morning["max_work_minutes"]), ("collect", "catchup", 30))
        self.assertEqual(morning["missing_dates"], ["2026-10-18"])
        for hour in [10, 16, 22]:
            self.clock = self.clock.replace(hour=hour)
            self.assertEqual(state.due(empty, self.policy)["action"], "collect")
        self.clock = self.clock.replace(hour=12)
        self.assertEqual(state.due(empty, self.policy)["action"], "none")
        self.clock = self.clock.replace(day=20, hour=10)
        self.assertEqual(state.due(empty, self.policy)["action"], "none")
        self.clock = self.clock.replace(day=21, hour=4)
        self.assertEqual(state.due(empty, self.policy)["reason"], "outside_authorized_trial")

    def test_continuous_mode_survives_trial_end_and_month_boundary(self):
        self.policy.update(mode="continuous", start_date="2026-10-18")
        for instant in [datetime(2026, 10, 21, 4, tzinfo=state.TZ),
                        datetime(2026, 11, 1, 4, tzinfo=state.TZ)]:
            self.clock = instant
            result = state.due(self.data(), self.policy)
            self.assertEqual((result["action"], result["trigger"]), ("collect", "scheduled"))
            self.assertIn(instant.date().isoformat(), result["missing_dates"])

    def test_continuous_recovery_has_no_final_day_cutoff(self):
        self.policy.update(mode="continuous", start_date="2026-10-18")
        self.clock = datetime(2026, 10, 20, 10, tzinfo=state.TZ)
        self.assertEqual(state.due(self.data(), self.policy)["action"], "collect")
        self.clock = self.clock.replace(day=21, hour=21, minute=58)
        self.assertEqual(state.due(self.data(), self.policy)["reason"], "early_execution_window")
        self.clock = self.clock.replace(day=17, hour=4)
        self.assertEqual(state.due(self.data(), self.policy)["reason"], "before_authorized_start")

    def test_completed_day_brief_and_retry_cap(self):
        self.clock = self.clock.replace(hour=10)
        run = self.finished()
        data = self.data(run)
        self.assertEqual(state.due(data, self.policy)["action"], "brief")
        run.update(brief_url="https://app.notion.com/p/daily", brief_date="2026-10-18")
        self.assertEqual(state.due(data, self.policy)["action"], "none")
        data["items"]["douyin:123"] = {"status": "failed"}
        self.assertEqual(state.due(data, self.policy)["action"], "repair")
        data["runs"]["repair"] = {**run, "id": "repair", "kind": "repair", "repair_of": "original"}
        self.assertEqual(state.due(data, self.policy)["reason"], "repair_budget_used")

    def test_explicit_user_discards_preserve_automatic_repair_budget(self):
        self.clock = self.clock.replace(hour=16)
        original = self.finished()
        original.update(brief_url="https://app.notion.com/p/daily", brief_date="2026-10-18")
        data = self.data(original, {"douyin:123": {"status": "failed"}})
        key = "bilibili:BV1wS4y1D7uT"
        event = {"key": key, "status": "discarded", "route": "discard", "cleanup_verified": True,
                 "source_state": "not_in_scoped_folders",
                 "discard_authorization": {"kind": "explicit_user_discard", "source_key": key,
                                           "request_text": "Directly remove this favorite"}}
        repair = {**original, "id": "user-discard", "kind": "repair", "repair_of": "original",
                  "trigger": "catchup", "events": [event]}
        data["runs"][repair["id"]] = repair
        self.assertEqual(state.due(data, self.policy)["action"], "repair")
        uncertain = {**event, "cleanup_verified": False}
        unauthorized = {**event, "discard_authorization": {"kind": "explicit_user_discard",
                        "source_key": "bilibili:BV1zG3m6fEpe", "request_text": "Discard"}}
        for events in ([], [uncertain], [unauthorized], [event, {"key": "douyin:123", "status": "failed"}]):
            with self.subTest(events=events):
                repair["events"] = events
                self.assertEqual(state.due(data, self.policy)["reason"], "repair_budget_used")
        repair.update(events=[event], status="interrupted")
        self.assertEqual(state.due(data, self.policy)["reason"], "repair_budget_used")

    def test_mechanism_repair_result_requires_a_fresh_brief(self):
        self.clock = self.clock.replace(hour=16)
        original = self.finished()
        original.update(finished_at="2026-10-18T04:30:00+08:00",
                        brief_url="https://app.notion.com/p/daily", brief_date="2026-10-18")
        data = self.data(original)
        repair = {**self.finished(), "id": "later-repair", "kind": "repair", "repair_of": "original",
                  "started_at": "2026-10-18T10:00:00+08:00", "finished_at": "2026-10-18T10:30:00+08:00"}
        data["runs"][repair["id"]] = repair
        self.assertEqual(state.due(data, self.policy)["action"], "brief")
        original["brief_updated_at"] = "2026-10-18T10:40:00+08:00"
        self.assertFalse(state.due(data, self.policy)["brief_due"])
        del original["brief_updated_at"]
        repair.update(brief_url="https://app.notion.com/p/daily", brief_date="2026-10-18")
        self.assertFalse(state.due(data, self.policy)["brief_due"])

    def test_mechanism_later_discovery_waits_for_the_next_collection(self):
        self.clock = self.clock.replace(hour=16)
        original = self.finished()
        original.update(finished_at="2026-10-18T04:30:00+08:00",
                        brief_url="https://app.notion.com/p/daily", brief_date="2026-10-18")
        item = {"status": "pending", "first_seen_run": "later-observation", "first_seen_phase": "before",
                "first_seen_at": "2026-10-18T10:05:00+08:00"}
        data = self.data(original, {"douyin:123": item})
        self.assertEqual(state.due(data, self.policy)["action"], "none")
        item["first_seen_at"] = "2026-10-18T04:05:00+08:00"
        self.assertEqual(state.due(data, self.policy)["action"], "repair")
        item["first_seen_at"] = "2026-10-18T10:05:00+08:00"
        self.clock = self.clock.replace(day=19, hour=4)
        self.assertEqual(state.due(data, self.policy)["action"], "collect")

    def test_mechanism_automatic_begin_enforces_the_due_decision(self):
        original = self.finished()
        used = {**original, "id": "used-repair", "kind": "repair", "repair_of": "original"}
        exhausted = self.data(original, {"douyin:123": {"status": "failed"}})
        exhausted["runs"][used["id"]] = used
        for day, hour, trigger, data, parent in [
                (18, 12, "scheduled", self.data(), None),
                (21, 4, "scheduled", self.data(), None),
                (18, 16, "catchup", exhausted, "original")]:
            with self.subTest(day=day, hour=hour):
                self.clock = self.clock.replace(day=day, hour=hour)
                (self.root / "state.json").write_text(json.dumps(data))
                args = ["--trigger", trigger] + (["--repair-of", parent] if parent else [])
                self.reject_unchanged("begin", None, *args)
        self.clock = self.clock.replace(day=18, hour=12)
        (self.root / "state.json").write_text(json.dumps(self.data()))
        self.assertEqual(self.call("begin", None, "--trigger", "manual")["run"]["trigger"], "manual")

    def test_mechanism_discard_cannot_change_out_of_scope_membership(self):
        self.policy["bilibili_scope"] = {"folder_ids": ["910612620"]}
        (self.root / "trial.json").write_text(json.dumps(self.policy))
        run = self.call("begin")["run"]["id"]
        bvid = "BV1wS4y1D7uT"
        self.call("inventory", {"platform": "bilibili", "account": state.ACCOUNTS["bilibili"],
                  "phase": "before", "accessible_count": 1,
                  "items": [{"id": bvid, "folder_ids": ["910612620"]}]}, "--run", run)
        record = {"key": "bilibili:" + bvid, "status": "discarded", "route": "discard",
                  "folder_ids": ["1608907220"], "cleanup_verified": True,
                  "source_state": "not_in_scoped_folders", "discard_authorization": {
                      "kind": "explicit_user_discard", "source_key": "bilibili:" + bvid, "request_text": "Discard"}}
        self.reject_unchanged("record", record, "--run", run)

    def test_mechanism_finish_preserves_observed_platforms_and_audits(self):
        run = self.call("begin")["run"]["id"]
        self.reject_unchanged("finish", {"platforms": {"xhs": {"pagination_complete": True}}}, "--run", run)
        self.reject_unchanged("finish", {"audits": []}, "--run", run)

    def test_mechanism_photos_need_nonempty_matching_platform_evidence(self):
        import hashlib
        library = self.root / "library"
        original = library / "originals" / "A" / "asset.jpg"
        original.parent.mkdir(parents=True)
        original.write_bytes(b"offline fixture")
        asset = {"asset_id": "A/L0/001", "managed_path": str(original), "bytes": original.stat().st_size,
                 "sha256": hashlib.sha256(original.read_bytes()).hexdigest()}
        receipt = {"source": "www.douyin.com/note/123", "complete": True, "managed_originals_verified": True,
                   "expected_count": 1, "library": str(library), "assets": [asset]}
        path = self.root / "photos.json"
        item = {"key": "douyin:123", "route": "photos", "archive_verified": True,
                "coverage_complete": True, "index_verified": True, "index_url": "https://app.notion.com/p/index",
                "photos_receipt": str(path)}
        for invalid in ({**receipt, "expected_count": 0, "assets": []},
                        {**receipt, "source": "unrelated.example/note/123"}):
            with self.subTest(receipt=invalid):
                path.write_text(json.dumps(invalid))
                with self.assertRaises(ValueError):
                    state.ready(item, self.policy)
        path.write_text(json.dumps(receipt))
        self.assertTrue(state.ready(item, self.policy))
        original.write_bytes(b"changed offline fixture")
        with self.assertRaises(ValueError):
            state.ready(item, self.policy)

    def test_mechanism_ninety_minute_lease_boundary_is_closed(self):
        run = self.call("begin")["run"]
        self.clock = datetime.fromisoformat(run["started_at"]) + timedelta(minutes=90, microseconds=-1)
        self.reject_unchanged("inventory", {"platform": "douyin", "account": state.ACCOUNTS["douyin"],
                              "accessible_count": 0, "items": []}, "--run", run["id"])

    def test_duplicate_gallery_media_reuses_one_verified_asset(self):
        import hashlib
        from types import SimpleNamespace
        import photos_capture
        source1, source2 = self.root / "one.jpg", self.root / "two.jpg"
        for p in (source1, source2):
            p.write_bytes(b"same offline image bytes")
        identifier = "AB111111-1111-1111-1111-111111111111/L0/001"
        library = self.root / "gallery.photoslibrary"
        managed = library / "originals" / "A" / (identifier.split("/")[0] + ".jpg")
        managed.parent.mkdir(parents=True)
        managed.write_bytes(source1.read_bytes())
        launcher = self.root / "fake-linkget"
        launcher.write_text('"' + str(self.root / "libexec/linkget/cli.py") + '"')
        receipt_path = self.root / "gallery-receipt.json"
        cli = SimpleNamespace(VERSION="offline-fixture", verify_library_copies=lambda files, ids: None)
        def import_unique(files, date_now, live_pairs=None):
            cli.verify_library_copies([files[0]], [identifier])
            return [files[0]], 1
        cli.import_photos = import_unique
        cli.main = lambda argv: (cli.import_photos([source1, source2], False), 0)[1]
        digest = lambda p, fresh=False: hashlib.sha256(Path(p).read_bytes()).hexdigest()
        photos = SimpleNamespace(library_directory=lambda: library, digest=digest)
        media = SimpleNamespace(reference=lambda url: "www.douyin.com/note/123",
                                inspect_files=lambda files: [{"kind": "image", "probe_ok": True} for p in files])
        modules = {"linkget.cli": cli, "linkget.photos": photos, "linkget.media": media}
        with patch.object(photos_capture.shutil, "which", return_value=str(launcher)), \
                patch.object(photos_capture.importlib, "import_module", side_effect=lambda name: modules[name]), \
                patch.object(sys, "path", list(sys.path)), patch.object(sys, "argv", [
                    "photos_capture.py", "https://www.douyin.com/note/123", "--expected", "2", "--kind", "image",
                    "--receipt", str(receipt_path)]):
            self.assertEqual(photos_capture.main(), 0)
        receipt = json.loads(receipt_path.read_text())
        self.assertTrue(receipt["complete"])
        self.assertEqual(receipt["expected_count"], 2)
        self.assertEqual(len(receipt["assets"]), 1)
        self.assertEqual(len(receipt["source_assets"]), 2)
        item = {"key": "douyin:123", "route": "photos", "archive_verified": True, "coverage_complete": True,
                "index_verified": True, "index_url": "https://app.notion.com/p/index", "photos_receipt": str(receipt_path)}
        self.assertTrue(state.ready(item, self.policy))
        receipt["source_assets"][1]["sha256"] = "0" * 64
        receipt_path.write_text(json.dumps(receipt))
        with self.assertRaises(ValueError):
            state.ready(item, self.policy)

    def test_early_native_wakeup_waits_without_opening_the_window(self):
        for hour in (4, 10, 16, 22):
            with self.subTest(hour=hour):
                self.clock = self.clock.replace(hour=hour-1, minute=55, second=30)
                result = state.due(self.data(), self.policy)
                self.assertEqual(result["action"], "none")
                expected = self.clock.replace(hour=hour, minute=0, second=0, microsecond=0)
                self.assertEqual(result.get("wait_until"), expected.isoformat())
        self.call("status")
        self.reject_unchanged("begin", None, "--trigger", "catchup")
        self.clock = self.clock.replace(hour=16, minute=0, second=0)
        self.assertEqual(state.due(self.data(), self.policy)["action"], "collect")
        self.clock = self.clock.replace(hour=15, minute=54, second=59)
        self.assertNotIn("wait_until", state.due(self.data(), self.policy))
        self.clock = self.clock.replace(day=20, hour=9, minute=55, second=30)
        self.assertNotIn("wait_until", state.due(self.data(), self.policy))
        self.clock = self.clock.replace(day=21, hour=3)
        self.assertEqual(state.due(self.data(), self.policy)["reason"], "outside_authorized_trial")

    def test_history_new_after_scan_and_busy_lease(self):
        self.clock = self.clock.replace(hour=10)
        run = self.finished()
        run.update(brief_url="https://app.notion.com/p/daily", brief_date="2026-10-18")
        data = self.data(run, {"xhs:old": {"status": "pending_read", "historical_backlog": True},
                              "xhs:new": {"status": "pending", "first_seen_run": "original", "first_seen_phase": "after"}})
        self.assertEqual(state.due(data, self.policy)["action"], "none")
        data["runs"]["live"] = {"id": "live", "date": "2026-10-18", "kind": "repair", "status": "running",
                                "started_at": self.clock.isoformat()}
        self.assertEqual(state.due(data, self.policy)["reason"], "active_lease")
        self.clock += timedelta(minutes=91)
        self.assertNotEqual(state.due(data, self.policy)["reason"], "active_lease")

    def test_new_channel_and_previous_day_backlog(self):
        self.clock = self.clock.replace(hour=16)
        run = self.finished()
        run["platforms"].pop("bilibili")
        result = state.due(self.data(run), self.policy)
        self.assertEqual((result["action"], result["missing_platforms"]), ("repair", ["bilibili"]))
        self.clock = self.clock.replace(day=19)
        result = state.due(self.data(run), self.policy)
        self.assertEqual(result["action"], "collect")
        self.assertEqual(result["missing_dates"], ["2026-10-19"])

    def test_explicit_discard_is_separate_from_verified_archiving(self):
        run = self.call("begin")["run"]
        key = "bilibili:BV1bTun6hEMx"
        self.call("inventory", {"platform": "bilibili", "account": state.ACCOUNTS["bilibili"], "phase": "before", "accessible_count": 1,
                  "items": [{"id": key.split(":")[1], "folder_ids": ["910612620"]}]}, "--run", run["id"])
        record = {"key": key, "status": "discarded", "route": "discard", "cleanup_verified": True,
                  "source_state": "not_in_scoped_folders"}
        self.reject_unchanged("record", record, "--run", run["id"])
        record["discard_authorization"] = {"kind": "explicit_user_discard", "source_key": "bilibili:BV1w1pb6yEBn", "request_text": "Discard"}
        self.reject_unchanged("record", record, "--run", run["id"])
        record["discard_authorization"]["source_key"] = key
        self.reject_unchanged("record", {**record, "cleanup_verified": False}, "--run", run["id"])
        self.call("record", record, "--run", run["id"])
        self.reject_unchanged("ready", None, "--key", key)

    def test_bilibili_identity_membership_scope_and_completion(self):
        self.clock = self.clock.replace(hour=10)
        run = self.call("begin", None, "--trigger", "catchup")["run"]
        self.assertEqual(run["scheduled_for"], "2026-10-18T04:00:00+08:00")
        self.assertIn("T10:", run["started_at"])
        self.reject_unchanged("begin")
        identity = "BV1w1pb6yEBn"
        key = "bilibili:" + identity
        inv = {"platform": "bilibili", "account": state.ACCOUNTS["bilibili"], "phase": "before",
               "accessible_count": 1, "items": [{"id": identity, "title": "Example", "folder_ids": ["11", "22"]}]}
        self.call("inventory", inv, "--run", run["id"])
        self.reject_unchanged("inventory", {**inv, "account": "other"}, "--run", run["id"])
        self.reject_unchanged("inventory", {**inv, "items": [{"id": identity}]}, "--run", run["id"])
        self.call("inventory", {**inv, "phase": "after", "items": [{**inv["items"][0], "folder_ids": ["11", "22", "33"]}]}, "--run", run["id"])
        data = self.call("status")
        item = data["items"][key]
        self.assertEqual(item["url"], "https://www.bilibili.com/video/" + identity)
        self.assertEqual(item["folder_ids"], ["11", "22"])
        self.assertEqual(item["observed_folder_ids"], ["11", "22", "33"])
        self.assertEqual(len(data["runs"][run["id"]]["inventories"]["bilibili"]), 2)
        record = {"key": key, "status": "archived", "route": "knowledge", "archive_verified": True,
                  "coverage_complete": True, "index_verified": True,
                  "index_url": "https://app.notion.com/p/index", "note_url": "https://app.notion.com/p/note"}
        self.call("record", record, "--run", run["id"])
        self.assertTrue(self.call("ready", None, "--key", key)["cleanup_ready"])
        self.reject_unchanged("record", {**record, "status": "complete"}, "--run", run["id"])
        self.call("record", {**record, "status": "complete", "cleanup_verified": True, "source_state": "not_in_scoped_folders"}, "--run", run["id"])
        self.reject_unchanged("finish", {"date": "2026-10-17"}, "--run", run["id"])
        self.call("finish", {"counts": {}}, "--run", run["id"])
        original = copy.deepcopy(self.call("status", None, "--run", run["id"]))
        repair = self.call("begin", None, "--repair-of", run["id"], "--trigger", "catchup")["run"]
        self.call("inventory", {**inv, "items": [{**inv["items"][0], "folder_ids": ["11", "22", "33"]}]}, "--run", repair["id"])
        self.assertEqual(self.call("status")["items"][key]["folder_ids"], ["11", "22"])
        self.call("finish", {}, "--run", repair["id"])
        self.assertEqual(self.call("status", None, "--run", run["id"]), original)
        self.assertTrue(self.call("begin")["already_finished"])

    def test_daily_brief_is_due_after_four_am_collection(self):
        self.policy["brief_at"] = "04:00"
        run = self.finished()
        data = self.data(run)
        self.assertEqual(state.due(data, self.policy)["action"], "brief")
        run.update(brief_url="https://app.notion.com/p/daily", brief_date="2026-10-18")
        self.assertEqual(state.due(data, self.policy)["action"], "none")
        run.update(status="running", started_at=self.clock.isoformat())
        self.assertEqual(state.due(data, self.policy)["reason"], "active_lease")

    def test_explicit_folder_scope_blocks_cleanup_and_retry(self):
        self.policy["bilibili_scope"] = {"folder_ids": ["910612620"]}
        (self.root / "trial.json").write_text(json.dumps(self.policy))
        item = {"key": "bilibili:BV1w1pb6yEBn", "status": "archived", "folder_ids": ["1608907220"],
                "route": "knowledge", "archive_verified": True, "coverage_complete": True,
                "index_verified": True, "index_url": "https://app.notion.com/p/index",
                "note_url": "https://app.notion.com/p/note"}
        with self.assertRaises(ValueError):
            state.ready(item, self.policy)
        item["folder_ids"] = ["910612620"]
        self.assertTrue(state.ready(item, self.policy))
        item["scope_excluded"] = True
        with self.assertRaises(ValueError):
            state.ready(item, self.policy)
        self.clock = self.clock.replace(hour=10)
        run = self.finished()
        run.update(brief_url="https://app.notion.com/p/daily", brief_date="2026-10-18")
        self.assertEqual(state.due(self.data(run, {item["key"]: item}), self.policy)["action"], "none")

    def test_holds_and_expired_lease_recovery(self):
        run = self.call("begin")["run"]["id"]
        self.clock += timedelta(minutes=91)
        repair = self.call("begin", None, "--repair-of", run)["run"]
        self.assertEqual(self.call("status", None, "--run", run)["status"], "interrupted")
        report = self.root / "audit.md"
        report.write_text("Offline fixture; no remote verification.")
        self.call("audit", {"status": "attention", "report_path": str(report), "cleanup_holds": {"bilibili": "investigation", "xhs": "independent"}}, "--run", repair["id"])
        self.reject_unchanged("ready", None, "--key", "bilibili:BV1w1pb6yEBn")
        self.call("audit", {"status": "attention", "report_path": str(report), "cleanup_holds": {"bilibili": None}}, "--run", repair["id"])
        self.assertEqual(self.call("status")["cleanup_holds"], {"xhs": "independent"})


if __name__ == "__main__":
    unittest.main()
