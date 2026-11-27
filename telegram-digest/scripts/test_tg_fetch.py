"""Offline unit tests for `telegram-digest/scripts/tg_fetch.py`."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import tg_fetch  # noqa: E402


def _photo_msg(msg_id: int, ts: int, text: str = "", uid: int = 101) -> dict:
    return {
        "id": msg_id,
        "type": "message",
        "file": f"{9000 + msg_id}.jpg",
        "date": ts,
        "text": text,
        "raw": {
            "ID": msg_id,
            "Date": ts,
            "Message": text,
            "FromID": {"UserID": uid},
            "Media": {
                "Photo": {
                    "ID": 9000 + msg_id,
                    "Sizes": [{"Type": "x", "Size": 42000}],
                }
            },
        },
    }


def _doc_msg(
    msg_id: int,
    ts: int,
    mime: str,
    filename: str,
    size: int = 12345,
    attrs: list[dict] | None = None,
    extra_media: dict | None = None,
) -> dict:
    media = {
        "Document": {
            "ID": 8000 + msg_id,
            "MimeType": mime,
            "Size": size,
            "Attributes": attrs if attrs is not None else [{"FileName": filename}],
        }
    }
    if extra_media:
        media.update(extra_media)
    return {
        "id": msg_id,
        "type": "message",
        "file": filename,
        "date": ts,
        "text": "",
        "raw": {
            "ID": msg_id,
            "Date": ts,
            "FromID": {"UserID": 102},
            "Media": media,
        },
    }


class TelegramDigestTests(unittest.TestCase):
    def test_classify_media_variants(self):
        self.assertEqual(tg_fetch.classify_media(_photo_msg(1, 1700000000))[0], "photo")
        self.assertEqual(
            tg_fetch.classify_media(_doc_msg(2, 1700000001, "image/png", "screenshot.png", size=500_000))[0],
            "image_document",
        )
        # WebP sticker excluded by DocumentAttributeSticker (`Stickerset` field)
        sticker = _doc_msg(
            3,
            1700000002,
            "image/webp",
            "sticker.webp",
            attrs=[{"Alt": "🙂", "Stickerset": {"ID": 1}}, {"FileName": "sticker.webp"}],
        )
        self.assertEqual(tg_fetch.classify_media(sticker)[0], "sticker")
        # Animated GIF excluded
        gif_img = _doc_msg(4, 1700000003, "image/gif", "anim.gif", attrs=[{}])
        self.assertEqual(tg_fetch.classify_media(gif_img)[0], "gif")
        gif_mp4 = _doc_msg(5, 1700000004, "video/mp4", "loop.mp4", attrs=[{}], extra_media={"Video": True})
        self.assertEqual(tg_fetch.classify_media(gif_mp4)[0], "gif")
        # Oversized image document excluded from image download
        big_png = _doc_msg(6, 1700000005, "image/png", "huge.png", size=20 * 1024 * 1024)
        self.assertEqual(tg_fetch.classify_media(big_png, max_image_mb=15.0)[0], "document")
        # Video, voice, audio, PDF, poll, plain text
        vid = _doc_msg(7, 1700000006, "video/mp4", "clip.mp4", extra_media={"Video": True})
        self.assertEqual(tg_fetch.classify_media(vid)[0], "video")
        voice = _doc_msg(8, 1700000007, "audio/ogg", "voice.ogg", attrs=[{"Voice": True, "Duration": 4}], extra_media={"Voice": True})
        self.assertEqual(tg_fetch.classify_media(voice)[0], "voice")
        audio = _doc_msg(9, 1700000008, "audio/mpeg", "track.mp3", attrs=[{"Duration": 180, "Performer": "A"}])
        self.assertEqual(tg_fetch.classify_media(audio)[0], "audio")
        pdf = _doc_msg(10, 1700000009, "application/pdf", "spec.pdf")
        self.assertEqual(tg_fetch.classify_media(pdf)[0], "document")
        poll = {"id": 11, "type": "message", "file": "", "raw": {"Media": {"Poll": {"Question": {"Text": "Q?"}}}}}
        self.assertEqual(tg_fetch.classify_media(poll)[0], "poll")
        plain = {"id": 12, "type": "message", "file": "", "text": "hi", "raw": {"Message": "hi"}}
        self.assertEqual(tg_fetch.classify_media(plain)[0], "none")

    def test_extract_text_links_sender_and_reply(self):
        users = tg_fetch.parse_users_file(
            {
                "users": [{"id": 101, "first_name": "Ada", "last_name": "Lovelace", "username": "ada"}],
                "admins": [{"id": 202, "first_name": "Grace", "last_name": "", "username": ""}],
            }
        )
        msg = {
            "id": 50,
            "text": "Check the benchmark notes here",
            "raw": {
                "ID": 50,
                "FromID": {"UserID": 101},
                "ReplyTo": {"ReplyToMsgID": 49, "ReplyToTopID": 12, "ForumTopic": True},
                "Entities": [
                    {"Offset": 26, "Length": 4, "URL": "https://example.org/bench"},
                    {"Offset": 0, "Length": 5, "URL": "https://example.org/bench"},
                ],
                "Media": {
                    "Poll": {
                        "Question": {"Text": "Ship Friday?"},
                        "Answers": [{"Text": {"Text": "Yes"}}, {"Text": {"Text": "Wait"}}],
                    }
                },
            },
        }
        self.assertEqual(tg_fetch.extract_sender(msg, users), "Ada Lovelace (@ada)")
        self.assertEqual(tg_fetch.extract_sender({"raw": {"FromID": {"ChannelID": 77}, "PostAuthor": "Ops"}}, users), "channel:77 (Ops)")
        self.assertEqual(tg_fetch.extract_reply_to(msg), (49, 12))
        text = tg_fetch.extract_text_and_links(msg)
        self.assertIn("https://example.org/bench", text)
        self.assertEqual(text.count("https://example.org/bench"), 1)
        self.assertIn("[Poll] Ship Friday? — Options: Yes | Wait", text)

    def test_resolve_chat_cases(self):
        chats = [
            {"id": 1001, "type": "group", "visible_name": "Infra Alpha", "username": "infra_alpha", "topics": []},
            {"id": 1002, "type": "group", "visible_name": "Infra Alpha Backup", "username": "", "topics": []},
            {"id": 1003, "type": "channel", "visible_name": "Release Notes", "username": "relnotes", "topics": []},
        ]
        self.assertEqual(tg_fetch.resolve_chat("Infra Alpha", chats)["id"], 1001)
        self.assertEqual(tg_fetch.resolve_chat("Release", chats)["id"], 1003)
        self.assertEqual(tg_fetch.resolve_chat("-100123456", chats)["target"], "-100123456")
        self.assertEqual(tg_fetch.resolve_chat("@relnotes", chats)["id"], 1003)
        with self.assertRaises(tg_fetch.ChatResolutionError) as ctx:
            tg_fetch.resolve_chat("Infra", chats)
        self.assertEqual(len(ctx.exception.candidates), 2)
        with self.assertRaises(tg_fetch.ChatResolutionError) as ctx_empty:
            tg_fetch.resolve_chat("Nonexistent", chats)
        self.assertEqual(ctx_empty.exception.candidates, [])

    def test_fetch_pipeline_mocked(self):
        chats_payload = [
            {"id": 555001, "type": "group", "visible_name": "Core Eng", "username": "coreeng", "topics": []}
        ]
        export_payload = {
            "id": 555001,
            "messages": [
                _photo_msg(103, 1700000300, text="Latest dashboard"),
                _doc_msg(102, 1700000200, "image/png", "trace.png", size=50000),
                _photo_msg(101, 1700000100, text="Old photo omitted by max-images=2"),
                _doc_msg(100, 1700000050, "application/pdf", "design.pdf", size=120000),
                {"id": 99, "type": "message", "file": "", "date": 1700000000, "text": "Kickoff", "raw": {"ID": 99, "Date": 1700000000, "Message": "Kickoff", "FromID": {"UserID": 101}}},
            ],
        }

        def fake_run(cmd, **_kwargs):
            # cmd[0] is binary; inspect subcommands
            if "ls" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(chats_payload), stderr="")
            if "export" in cmd:
                out_path = Path(cmd[cmd.index("-o") + 1])
                out_path.write_text(json.dumps(export_payload), encoding="utf-8")
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            if "users" in cmd:
                return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="CHAT_ADMIN_REQUIRED")
            if "dl" in cmd:
                dl_dir = Path(cmd[cmd.index("-d") + 1])
                subset = json.loads(Path(cmd[cmd.index("-f") + 1]).read_text(encoding="utf-8"))
                # Simulate partial download: download 102, fail 103
                for m in subset["messages"]:
                    if m["id"] == 102:
                        (dl_dir / "102_trace.png").write_bytes(b"PNG")
                return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="partial download failure")
            raise AssertionError(f"Unexpected command: {cmd}")

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "out"
            with patch.object(tg_fetch, "run_tdl", side_effect=fake_run):
                manifest = tg_fetch.fetch_chat(
                    chat_arg="Core Eng",
                    ns="default",
                    proxy=None,
                    last=10,
                    max_images=2,
                    out_dir=str(out_dir),
                )

            self.assertTrue(manifest["ok"])
            self.assertEqual(manifest["message_count"], 5)
            self.assertEqual(manifest["images_omitted"], 1)
            self.assertEqual(manifest["images_downloaded"], 1)
            self.assertEqual(manifest["images_failed"], [103])
            self.assertEqual(manifest["skipped_media_counts"], {"document": 1})
            self.assertEqual(len(manifest["warnings"]), 2)

            subset_saved = json.loads((out_dir / "raw" / "images_only.json").read_text(encoding="utf-8"))
            self.assertEqual([m["id"] for m in subset_saved["messages"]], [102, 103])

            transcript = (out_dir / "transcript.md").read_text(encoding="utf-8")
            # Chronological order: #99 before #100 before #102 before #103
            self.assertLess(transcript.index("### #99"), transcript.index("### #100"))
            self.assertLess(transcript.index("### #100"), transcript.index("### #102"))
            self.assertLess(transcript.index("### #102"), transcript.index("### #103"))
            self.assertIn("[IMAGE #102:", transcript)
            self.assertIn("[MEDIA skipped: document (design.pdf)]", transcript)


if __name__ == "__main__":
    unittest.main()
