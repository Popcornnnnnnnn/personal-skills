#!/usr/bin/env python3
"""Read-only Telegram group/channel fetcher built on top of `tdl`."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any
from urllib.parse import urlsplit, urlunsplit

DEFAULT_MAX_IMAGES = 20
DEFAULT_MAX_IMAGE_MB = 15.0
DEFAULT_HOURS = 24.0
DEFAULT_LIST_LIMIT = 50
DEFAULT_TEMPLATE = "{{ .MessageID }}_{{ filenamify .FileName }}"
TDL_STORAGE_DIR = Path.home() / ".tdl"
DEFAULT_OUT_ROOT = Path("/tmp/telegram-digest")

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif", ".heic"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
VOICE_EXTS = {".ogg", ".oga", ".opus"}
AUDIO_EXTS = {".mp3", ".m4a", ".flac", ".wav", ".aac"}


class ChatResolutionError(Exception):
    """Raised when a chat name cannot be resolved uniquely."""

    def __init__(self, message: str, candidates: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message)
        self.candidates = candidates or []


def resolve_proxy(explicit_proxy: str | None) -> tuple[str | None, str | None]:
    """Resolve explicit `--proxy` flag or standard proxy environment variables."""
    if explicit_proxy is not None:
        val = explicit_proxy.strip()
        return (val or None), ("--proxy" if val else None)
    for var in ("TDL_PROXY", "ALL_PROXY", "all_proxy", "HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        val = os.environ.get(var, "").strip()
        if val:
            return val, var
    return None, None


def redact_proxy(proxy_url: str | None) -> str | None:
    """Mask embedded credentials in a proxy URL before printing."""
    if not proxy_url:
        return None
    parsed = urlsplit(proxy_url)
    if parsed.username or parsed.password:
        host = parsed.hostname or ""
        port = f":{parsed.port}" if parsed.port else ""
        netloc = f"***@{host}{port}"
        return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))
    return proxy_url


def build_tdl_base_args(ns: str, proxy: str | None) -> list[str]:
    """Construct global read-only flags for `tdl` invocations."""
    args = ["--disable-progress-ps", "-n", ns]
    if proxy:
        args.extend(["--proxy", proxy])
    return args


def has_local_session(ns: str, storage_dir: Path | None = None) -> bool:
    """Check whether `tdl` BoltDB storage holds a persisted session key."""
    root = storage_dir or TDL_STORAGE_DIR
    candidates = [root / "data" / ns, root / "data.kv"]
    for path in candidates:
        if not path.is_file():
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        # An uninitialized BoltDB file is 64 KiB and has no `session` key entry.
        if b"session" in data:
            return True
    return False


def run_tdl(
    args: list[str],
    *,
    timeout: int = 120,
    tdl_bin: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a read-only `tdl` subcommand without terminal interactivity."""
    binary = tdl_bin or shutil.which("tdl") or "tdl"
    return subprocess.run(
        [binary, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        stdin=subprocess.DEVNULL,
    )


def parse_version_text(raw: str) -> str:
    """Extract the semantic version string from `tdl version` output."""
    for line in raw.splitlines():
        if line.lower().startswith("version:"):
            return line.split(":", 1)[1].strip()
    return raw.strip().splitlines()[0] if raw.strip() else ""


def doctor_check(
    *,
    ns: str = "default",
    proxy: str | None = None,
    proxy_source: str | None = None,
    live: bool = False,
) -> dict[str, Any]:
    """Inspect local `tdl` readiness and optionally verify live auth."""
    tdl_path = shutil.which("tdl")
    tdl_version = ""
    if tdl_path:
        try:
            proc = run_tdl(["version"], timeout=10, tdl_bin=tdl_path)
            if proc.returncode == 0:
                tdl_version = parse_version_text(proc.stdout)
        except (OSError, subprocess.SubprocessError):
            tdl_version = ""

    session_present = has_local_session(ns)
    authenticated: bool | None = None
    chat_count: int | None = None
    live_error: str | None = None

    if tdl_path and live:
        try:
            proc = run_tdl([*build_tdl_base_args(ns, proxy), "chat", "ls", "-o", "json"], timeout=20, tdl_bin=tdl_path)
            if proc.returncode == 0:
                authenticated = True
                try:
                    chats = json.loads(proc.stdout or "[]")
                    if isinstance(chats, list):
                        chat_count = len(chats)
                except json.JSONDecodeError:
                    chat_count = None
            else:
                authenticated = False
                combined = "\n".join(part for part in (proc.stderr, proc.stdout) if part).strip()
                live_error = combined.splitlines()[-1] if combined else f"tdl exited with {proc.returncode}"
        except subprocess.TimeoutExpired:
            authenticated = False
            live_error = "Timed out checking Telegram connection; check proxy/network."

    ok = bool(tdl_path) and session_present and (authenticated is not False)
    if not tdl_path:
        next_step = "Install tdl first (`brew install telegram-downloader`)."
    elif not session_present or authenticated is False:
        proxy_hint = f" --proxy {redact_proxy(proxy)}" if proxy else ""
        next_step = (
            f"Run `tdl -n {ns}{proxy_hint} login -T qr` in an interactive terminal (Ghostty on macOS) "
            "and scan the QR code in Telegram (Settings -> Devices -> Link Desktop Device)."
        )
    elif authenticated is None:
        proxy_hint = f" --proxy {redact_proxy(proxy)}" if proxy else ""
        next_step = (
            "Session store exists; run `doctor --live` to verify live auth, or run "
            f"`tdl -n {ns}{proxy_hint} login -T qr` in an interactive terminal if not yet signed in."
        )
    else:
        next_step = "Ready. Run `list` to find a chat or `fetch --chat '<name_or_id>'` to export history."

    result: dict[str, Any] = {
        "ok": ok,
        "tdl_path": tdl_path,
        "tdl_version": tdl_version,
        "namespace": ns,
        "session_present": session_present,
        "authenticated": authenticated,
        "proxy": redact_proxy(proxy),
        "proxy_source": proxy_source,
        "next_step": next_step,
    }
    if chat_count is not None:
        result["chat_count"] = chat_count
    if live_error:
        result["live_error"] = live_error
    return result


def normalize_chats(raw_chats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize `tdl chat ls -o json` entries."""
    out: list[dict[str, Any]] = []
    for item in raw_chats:
        if not isinstance(item, dict):
            continue
        username = (item.get("username") or "").strip()
        if username == "-":
            username = ""
        topics = [
            {"id": t.get("id"), "title": t.get("title", "")}
            for t in (item.get("topics") or [])
            if isinstance(t, dict)
        ]
        out.append(
            {
                "id": item.get("id"),
                "type": item.get("type") or "unknown",
                "visible_name": (item.get("visible_name") or "").strip(),
                "username": username,
                "topics": topics,
            }
        )
    return out


def list_chats(
    *,
    ns: str,
    proxy: str | None,
    query: str = "",
    chat_type: str = "all",
    limit: int = DEFAULT_LIST_LIMIT,
) -> dict[str, Any]:
    """List and filter Telegram chats via `tdl chat ls -o json`."""
    proc = run_tdl([*build_tdl_base_args(ns, proxy), "chat", "ls", "-o", "json"], timeout=45)
    if proc.returncode != 0:
        err = "\n".join(p for p in (proc.stderr, proc.stdout) if p).strip()
        raise RuntimeError(err or f"tdl chat ls failed with exit code {proc.returncode}")
    raw = json.loads(proc.stdout or "[]")
    normalized = normalize_chats(raw if isinstance(raw, list) else [])
    q = query.strip().lower()
    filtered: list[dict[str, Any]] = []
    for chat in normalized:
        if chat_type != "all" and chat["type"] != chat_type:
            continue
        if q:
            haystack = " ".join(
                [
                    str(chat.get("id") or ""),
                    chat.get("visible_name", ""),
                    chat.get("username", ""),
                ]
            ).lower()
            if q not in haystack:
                continue
        filtered.append(chat)
    sliced = filtered[:limit] if limit and limit > 0 else filtered
    return {
        "ok": True,
        "count": len(sliced),
        "total_matched": len(filtered),
        "total_dialogs": len(normalized),
        "chats": sliced,
    }


def is_direct_chat_ref(chat_arg: str) -> bool:
    """Return True for numeric IDs, @usernames, or t.me links passed straight to `tdl`."""
    s = chat_arg.strip()
    if not s:
        return False
    if re.fullmatch(r"-?\d+", s):
        return True
    if s.startswith("@") and len(s) > 1:
        return True
    if s.startswith(("https://t.me/", "http://t.me/", "t.me/")):
        return True
    return False


def resolve_chat(chat_arg: str, chats: list[dict[str, Any]]) -> dict[str, Any]:
    """Resolve a chat ID/@username/link or uniquely match a visible name."""
    s = chat_arg.strip()
    if not s:
        raise ChatResolutionError("Chat argument cannot be empty.")

    if is_direct_chat_ref(s):
        norm_user = s.lstrip("@").lower()
        for chat in chats:
            if str(chat.get("id")) == s or (chat.get("username") and chat["username"].lower() == norm_user):
                return {**chat, "target": s, "direct": True}
        return {"id": s, "type": "unknown", "visible_name": s, "username": "", "topics": [], "target": s, "direct": True}

    q = s.lower()
    exact = [
        c
        for c in chats
        if (c.get("visible_name") or "").lower() == q
        or (c.get("username") or "").lstrip("@").lower() == q
    ]
    if len(exact) == 1:
        chosen = exact[0]
        return {**chosen, "target": str(chosen["id"]), "direct": False}
    if len(exact) > 1:
        raise ChatResolutionError(f"Multiple chats match exact name {chat_arg!r}. Use numeric ID.", exact)

    partial = [
        c
        for c in chats
        if q in (c.get("visible_name") or "").lower()
        or q in (c.get("username") or "").lower()
    ]
    if len(partial) == 1:
        chosen = partial[0]
        return {**chosen, "target": str(chosen["id"]), "direct": False}
    if len(partial) > 1:
        raise ChatResolutionError(f"Multiple chats match {chat_arg!r}. Pick an exact name or ID.", partial[:15])
    raise ChatResolutionError(f"No chat matched {chat_arg!r}. Run `list` to inspect available chats.", [])


def parse_iso_timestamp(value: str) -> int:
    """Parse an ISO-8601 date/datetime string into a Unix timestamp."""
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        local_tz = datetime.now().astimezone().tzinfo or timezone.utc
        dt = dt.replace(tzinfo=local_tz)
    return int(dt.timestamp())


def build_export_window_args(
    *,
    hours: float | None = None,
    since: str | None = None,
    until: str | None = None,
    last: int | None = None,
    id_range: str | None = None,
    now_ts: int | None = None,
) -> tuple[list[str], dict[str, Any]]:
    """Convert CLI window options into `tdl chat export` type/input flags."""
    now = int(now_ts if now_ts is not None else datetime.now(tz=timezone.utc).timestamp())
    if last is not None:
        if last <= 0:
            raise ValueError("--last must be positive.")
        return ["-T", "last", "-i", str(last)], {"mode": "last", "last": last}
    if id_range is not None:
        parts = [p.strip() for p in id_range.split(",")]
        if len(parts) != 2 or not all(re.fullmatch(r"\d+", p) for p in parts):
            raise ValueError("--id-range must be '<start>,<end>' of non-negative integers.")
        start_id, end_id = sorted((int(parts[0]), int(parts[1])))
        return ["-T", "id", "-i", f"{start_id},{end_id}"], {"mode": "id", "start_id": start_id, "end_id": end_id}
    if since is not None:
        start_ts = parse_iso_timestamp(since)
        end_ts = parse_iso_timestamp(until) if until else now
        if start_ts > end_ts:
            raise ValueError("--since must be earlier than --until.")
        return ["-T", "time", "-i", f"{start_ts},{end_ts}"], {
            "mode": "time",
            "start_ts": start_ts,
            "end_ts": end_ts,
            "start_iso": datetime.fromtimestamp(start_ts, tz=timezone.utc).isoformat(),
            "end_iso": datetime.fromtimestamp(end_ts, tz=timezone.utc).isoformat(),
        }
    hrs = DEFAULT_HOURS if hours is None else hours
    if hrs <= 0:
        raise ValueError("--hours must be positive.")
    start_ts = int(now - hrs * 3600)
    return ["-T", "time", "-i", f"{start_ts},{now}"], {
        "mode": "time",
        "hours": hrs,
        "start_ts": start_ts,
        "end_ts": now,
        "start_iso": datetime.fromtimestamp(start_ts, tz=timezone.utc).isoformat(),
        "end_iso": datetime.fromtimestamp(now, tz=timezone.utc).isoformat(),
    }


def _photo_size_bytes(photo: dict[str, Any]) -> int:
    sizes = photo.get("Sizes") or []
    for entry in reversed(sizes):
        if not isinstance(entry, dict):
            continue
        if isinstance(entry.get("Size"), int) and entry["Size"] > 0:
            return entry["Size"]
        prog = entry.get("Sizes")
        if isinstance(prog, list) and prog and isinstance(prog[-1], int):
            return int(prog[-1])
    return 0


def classify_media(msg: dict[str, Any], max_image_mb: float = DEFAULT_MAX_IMAGE_MB) -> tuple[str, str, str, int]:
    """Classify a `tdl` message's media as `(kind, mime, filename, size_bytes)`."""
    raw = msg.get("raw") if isinstance(msg.get("raw"), dict) else {}
    media = raw.get("Media") if isinstance(raw.get("Media"), dict) else None
    fallback_file = (msg.get("file") or "").strip()

    if media is None:
        if fallback_file:
            ext = Path(fallback_file).suffix.lower()
            if ext in IMAGE_EXTS:
                return ("photo", "image/jpeg" if ext in {".jpg", ".jpeg"} else f"image/{ext.lstrip('.')}", fallback_file, 0)
            if ext == ".gif":
                return ("gif", "image/gif", fallback_file, 0)
            if ext in VIDEO_EXTS:
                return ("video", "", fallback_file, 0)
            if ext in VOICE_EXTS:
                return ("voice", "", fallback_file, 0)
            if ext in AUDIO_EXTS:
                return ("audio", "", fallback_file, 0)
            return ("document", "", fallback_file, 0)
        return ("none", "", "", 0)

    if isinstance(media.get("Photo"), dict):
        photo = media["Photo"]
        filename = fallback_file or f"{photo.get('ID', msg.get('id', 'photo'))}.jpg"
        return ("photo", "image/jpeg", filename, _photo_size_bytes(photo))

    if isinstance(media.get("Document"), dict):
        doc = media["Document"]
        mime = (doc.get("MimeType") or "").lower().strip()
        size_bytes = int(doc.get("Size") or 0)
        attrs = [a for a in (doc.get("Attributes") or []) if isinstance(a, dict)]

        filename = fallback_file
        for attr in attrs:
            if attr.get("FileName"):
                filename = str(attr["FileName"])
                break

        has_sticker = mime == "application/x-tgsticker" or any(
            "Stickerset" in attr or attr.get("type") == "DocumentAttributeSticker"
            for attr in attrs
        )
        if has_sticker:
            return ("sticker", mime, filename, size_bytes)

        is_voice = bool(media.get("Voice")) or any(
            bool(attr.get("Voice"))
            for attr in attrs
        )
        if is_voice:
            return ("voice", mime, filename, size_bytes)

        has_animated = any(
            len(attr) == 0 or attr.get("type") == "DocumentAttributeAnimated"
            for attr in attrs
        )
        if mime == "image/gif" or (has_animated and (mime.startswith("image/") or mime.startswith("video/"))):
            return ("gif", mime, filename, size_bytes)

        if bool(media.get("Video")) or bool(media.get("Round")) or mime.startswith("video/") or any(
            "RoundMessage" in attr or "SupportsStreaming" in attr for attr in attrs
        ):
            return ("video", mime, filename, size_bytes)

        if mime.startswith("audio/") or any(
            ("Duration" in attr and ("Performer" in attr or "Title" in attr or "Voice" in attr))
            for attr in attrs
        ):
            return ("audio", mime, filename, size_bytes)

        if mime.startswith("image/"):
            max_bytes = int(max_image_mb * 1024 * 1024) if max_image_mb and max_image_mb > 0 else 0
            if max_bytes and size_bytes > max_bytes:
                return ("document", mime, filename, size_bytes)
            return ("image_document", mime, filename, size_bytes)

        return ("document", mime, filename, size_bytes)

    if isinstance(media.get("Poll"), dict):
        return ("poll", "", "", 0)
    if isinstance(media.get("Webpage"), dict):
        return ("webpage", "", "", 0)
    if fallback_file:
        return ("document", "", fallback_file, 0)
    return ("none", "", "", 0)


def parse_users_file(users_data: dict[str, Any]) -> dict[int, str]:
    """Build a `{user_id: display_label}` map from `tdl chat users` JSON."""
    users_map: dict[int, str] = {}
    for bucket in ("users", "admins", "bots", "kicked", "banned"):
        entries = users_data.get(bucket) or []
        if not isinstance(entries, list):
            continue
        for u in entries:
            if not isinstance(u, dict) or not u.get("id"):
                continue
            uid = int(u["id"])
            full = " ".join(part for part in ((u.get("first_name") or "").strip(), (u.get("last_name") or "").strip()) if part)
            username = (u.get("username") or "").strip().lstrip("@")
            if full and username:
                label = f"{full} (@{username})"
            elif username:
                label = f"@{username}"
            elif full:
                label = full
            else:
                label = f"user:{uid}"
            users_map[uid] = label
    return users_map


def extract_sender(msg: dict[str, Any], users_map: dict[int, str]) -> str:
    """Resolve message sender display name from `raw.FromID` / `PostAuthor`."""
    raw = msg.get("raw") if isinstance(msg.get("raw"), dict) else {}
    post_author = (raw.get("PostAuthor") or "").strip()
    from_id = raw.get("FromID")
    if isinstance(from_id, dict):
        if from_id.get("UserID"):
            uid = int(from_id["UserID"])
            return users_map.get(uid, f"user:{uid}")
        if from_id.get("ChannelID"):
            cid = int(from_id["ChannelID"])
            return f"channel:{cid} ({post_author})" if post_author else f"channel:{cid}"
        if from_id.get("ChatID"):
            gid = int(from_id["ChatID"])
            return f"chat:{gid}"
    if post_author:
        return post_author
    if msg.get("from"):
        return str(msg["from"])
    return "unknown"


def extract_reply_to(msg: dict[str, Any]) -> tuple[int | None, int | None]:
    """Return `(reply_to_msg_id, topic_id)` from `raw.ReplyTo` when present."""
    raw = msg.get("raw") if isinstance(msg.get("raw"), dict) else {}
    reply = raw.get("ReplyTo")
    if not isinstance(reply, dict):
        return (None, None)
    reply_id = reply.get("ReplyToMsgID") or None
    topic_id = reply.get("ReplyToTopID") or None
    if reply.get("ForumTopic") and not topic_id and reply_id:
        topic_id = reply_id
    return (int(reply_id) if reply_id else None, int(topic_id) if topic_id else None)


def _text_with_entities_str(val: Any) -> str:
    if isinstance(val, dict):
        return str(val.get("Text") or "")
    return str(val or "")


def extract_text_and_links(msg: dict[str, Any]) -> str:
    """Combine message text, hidden `TextURL` entities, polls, and link previews."""
    raw = msg.get("raw") if isinstance(msg.get("raw"), dict) else {}
    base_text = str(msg.get("text") if msg.get("text") is not None else (raw.get("Message") or "")).strip()

    extra_urls: list[str] = []
    for ent in raw.get("Entities") or []:
        if isinstance(ent, dict) and ent.get("URL"):
            url = str(ent["URL"]).strip()
            if url and url not in base_text and url not in extra_urls:
                extra_urls.append(url)

    sections: list[str] = []
    if base_text:
        sections.append(base_text)
    if extra_urls:
        sections.append("Links: " + " | ".join(extra_urls))

    media = raw.get("Media") if isinstance(raw.get("Media"), dict) else {}
    if isinstance(media.get("Poll"), dict):
        poll = media["Poll"]
        question = _text_with_entities_str(poll.get("Question")).strip()
        options = [
            _text_with_entities_str(ans.get("Text")).strip()
            for ans in (poll.get("Answers") or [])
            if isinstance(ans, dict)
        ]
        options = [opt for opt in options if opt]
        poll_line = f"[Poll] {question}" if question else "[Poll]"
        if options:
            poll_line += " — Options: " + " | ".join(options)
        sections.append(poll_line)
    elif isinstance(media.get("Webpage"), dict):
        wp = media["Webpage"]
        wp_url = (wp.get("URL") or "").strip()
        wp_title = (wp.get("Title") or "").strip()
        if wp_url and (wp_title or wp_url not in base_text):
            label = f"{wp_title} ({wp_url})" if wp_title else wp_url
            sections.append(f"[Webpage] {label}")

    return "\n".join(sections).strip()


def message_sort_key(msg: dict[str, Any]) -> tuple[int, int]:
    raw = msg.get("raw") if isinstance(msg.get("raw"), dict) else {}
    date_val = int(msg.get("date") or raw.get("Date") or 0)
    msg_id = int(msg.get("id") or raw.get("ID") or 0)
    return (date_val, msg_id)


def build_image_export_subset(
    export_data: dict[str, Any],
    max_images: int = DEFAULT_MAX_IMAGES,
    max_image_mb: float = DEFAULT_MAX_IMAGE_MB,
) -> tuple[dict[str, Any], list[dict[str, Any]], int, dict[str, int]]:
    """Select up to `max_images` most-recent downloadable images and tally skipped media."""
    messages = sorted(
        [m for m in (export_data.get("messages") or []) if isinstance(m, dict)],
        key=message_sort_key,
    )
    eligible: list[dict[str, Any]] = []
    skipped_counts: Counter[str] = Counter()

    for msg in messages:
        kind, _mime, _fn, _sz = classify_media(msg, max_image_mb=max_image_mb)
        if kind in ("photo", "image_document") and (msg.get("file") or msg.get("photo")):
            eligible.append(msg)
        elif kind not in ("none", "webpage", "poll", "photo", "image_document"):
            skipped_counts[kind] += 1

    if max_images == 0:
        selected: list[dict[str, Any]] = []
    elif max_images < 0:
        selected = eligible
    else:
        selected = eligible[-max_images:]

    omitted_count = max(0, len(eligible) - len(selected))
    subset = {"id": export_data.get("id"), "messages": selected}
    return subset, selected, omitted_count, dict(sorted(skipped_counts.items()))


def map_downloaded_files(images_dir: Path, selected_msgs: list[dict[str, Any]]) -> dict[int, str]:
    """Map files downloaded by `tdl dl` back to their Telegram message IDs."""
    by_msg_id: dict[int, str] = {}
    if not images_dir.is_dir():
        return by_msg_id

    selected_ids = {int(m["id"]) for m in selected_msgs if m.get("id") is not None}
    file_to_id = {
        str(m["file"]): int(m["id"])
        for m in selected_msgs
        if m.get("file") and m.get("id") is not None
    }

    for path in sorted(images_dir.iterdir()):
        if not path.is_file() or path.name.endswith(".tmp"):
            continue
        match = re.match(r"^(\d+)_(.+)$", path.name)
        if match:
            mid = int(match.group(1))
            if mid in selected_ids:
                by_msg_id[mid] = str(path.resolve())
                continue
        for fname, mid in file_to_id.items():
            if path.name.endswith(fname) and mid not in by_msg_id:
                by_msg_id[mid] = str(path.resolve())
                break
    return by_msg_id


def download_images(
    subset_path: Path,
    images_dir: Path,
    tdl_base_args: list[str],
    selected_msgs: list[dict[str, Any]],
) -> tuple[dict[int, str], list[int], str | None]:
    """Download selected images via `tdl dl`, surviving partial failures."""
    images_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        *tdl_base_args,
        "dl",
        "-f",
        str(subset_path),
        "-d",
        str(images_dir),
        "--skip-same",
        "--restart",
        "--template",
        DEFAULT_TEMPLATE,
    ]
    warning: str | None = None
    try:
        proc = run_tdl(cmd, timeout=180)
        if proc.returncode != 0:
            err = "\n".join(p for p in (proc.stderr, proc.stdout) if p).strip()
            warning = err.splitlines()[-1] if err else f"tdl dl exited with {proc.returncode}"
    except subprocess.TimeoutExpired:
        warning = "tdl dl timed out; partial downloads (if any) retained."

    path_by_msg_id = map_downloaded_files(images_dir, selected_msgs)
    failed_ids = [int(m["id"]) for m in selected_msgs if m.get("id") is not None and int(m["id"]) not in path_by_msg_id]
    return path_by_msg_id, failed_ids, warning


def render_transcript(
    chat_meta: dict[str, Any],
    window_meta: dict[str, Any],
    normalized_msgs: list[dict[str, Any]],
    path_by_msg_id: dict[int, str],
    *,
    omitted_count: int = 0,
    skipped_media_counts: dict[str, int] | None = None,
    images_enabled: bool = True,
) -> str:
    """Render a chronological Markdown transcript ready for agent summarization."""
    title = chat_meta.get("visible_name") or str(chat_meta.get("id") or "Telegram Chat")
    lines = [
        f"# Telegram Transcript: {title}",
        "",
        f"- **Chat ID:** `{chat_meta.get('id')}` ({chat_meta.get('type', 'unknown')})",
        f"- **Window:** `{json.dumps(window_meta, ensure_ascii=False)}`",
        f"- **Messages:** {len(normalized_msgs)}",
        f"- **Images Downloaded:** {len(path_by_msg_id)} (omitted by cap: {omitted_count})",
        f"- **Skipped Non-Image Media:** `{json.dumps(skipped_media_counts or {}, ensure_ascii=False)}`",
        "",
        "---",
        "",
    ]

    for msg in normalized_msgs:
        mid = msg["id"]
        ts_iso = msg["date_iso"]
        header = f"### #{mid} · {ts_iso} · {msg['sender']}"
        tags: list[str] = []
        if msg.get("topic_id"):
            tags.append(f"topic #{msg['topic_id']}")
        if msg.get("reply_to_msg_id"):
            tags.append(f"reply to #{msg['reply_to_msg_id']}")
        if tags:
            header += " (" + ", ".join(tags) + ")"
        lines.append(header)

        if msg.get("text"):
            lines.append(msg["text"])

        kind = msg["media_kind"]
        if mid in path_by_msg_id:
            lines.append(f"[IMAGE #{mid}: {path_by_msg_id[mid]}]")
        elif kind in ("photo", "image_document"):
            reason = "not downloaded (--no-images)" if not images_enabled else "not downloaded (cap or fetch error)"
            lines.append(f"[IMAGE #{mid} {reason}]")
        elif kind not in ("none", "webpage", "poll"):
            detail = msg.get("media_filename") or msg.get("media_mime") or kind
            lines.append(f"[MEDIA skipped: {kind} ({detail})]")

        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-._")
    return (slug[:48] or "chat").lower()


def fetch_chat(
    *,
    chat_arg: str,
    ns: str,
    proxy: str | None,
    hours: float | None = None,
    since: str | None = None,
    until: str | None = None,
    last: int | None = None,
    id_range: str | None = None,
    topic: int | None = None,
    images: bool = True,
    max_images: int = DEFAULT_MAX_IMAGES,
    max_image_mb: float = DEFAULT_MAX_IMAGE_MB,
    resolve_users: bool = True,
    out_dir: str | None = None,
) -> dict[str, Any]:
    """Export messages, optionally fetch images, and produce transcript + manifest."""
    base_args = build_tdl_base_args(ns, proxy)
    window_flags, window_meta = build_export_window_args(
        hours=hours,
        since=since,
        until=until,
        last=last,
        id_range=id_range,
    )
    if topic is not None:
        window_meta["topic"] = topic

    chats: list[dict[str, Any]] = []
    if not is_direct_chat_ref(chat_arg):
        ls_proc = run_tdl([*base_args, "chat", "ls", "-o", "json"], timeout=45)
        if ls_proc.returncode != 0:
            err = "\n".join(p for p in (ls_proc.stderr, ls_proc.stdout) if p).strip()
            raise RuntimeError(err or f"tdl chat ls failed with exit code {ls_proc.returncode}")
        raw_ls = json.loads(ls_proc.stdout or "[]")
        chats = normalize_chats(raw_ls if isinstance(raw_ls, list) else [])

    chat_meta = resolve_chat(chat_arg, chats)
    target = str(chat_meta["target"])

    if out_dir:
        dest = Path(out_dir).expanduser().resolve()
    else:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        label = chat_meta.get("visible_name") or chat_meta.get("username") or target
        dest = (DEFAULT_OUT_ROOT / f"{stamp}-{safe_slug(str(label))}").resolve()

    raw_dir = dest / "raw"
    images_dir = dest / "images"
    raw_dir.mkdir(parents=True, exist_ok=True)
    export_path = raw_dir / "export.json"

    export_cmd = [
        *base_args,
        "chat",
        "export",
        "-c",
        target,
        "-o",
        str(export_path),
        "--all",
        "--with-content",
        "--raw",
        *window_flags,
    ]
    if topic is not None:
        export_cmd.extend(["--topic", str(topic)])

    exp_proc = run_tdl(export_cmd, timeout=180)
    if exp_proc.returncode != 0 or not export_path.is_file():
        err = "\n".join(p for p in (exp_proc.stderr, exp_proc.stdout) if p).strip()
        raise RuntimeError(err or f"tdl chat export failed with exit code {exp_proc.returncode}")

    export_data = json.loads(export_path.read_text(encoding="utf-8"))
    if export_data.get("id") is not None:
        chat_meta["id"] = export_data["id"]

    warnings: list[str] = []
    users_map: dict[int, str] = {}
    if resolve_users:
        users_path = raw_dir / "users.json"
        try:
            u_proc = run_tdl([*base_args, "chat", "users", "-c", target, "-o", str(users_path)], timeout=20)
            if u_proc.returncode == 0 and users_path.is_file():
                users_map = parse_users_file(json.loads(users_path.read_text(encoding="utf-8")))
            else:
                warnings.append("User list unavailable (restricted group or unsupported chat type); using IDs.")
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
            warnings.append("User list timed out or failed; using IDs.")

    sorted_raw_msgs = sorted(
        [m for m in (export_data.get("messages") or []) if isinstance(m, dict)],
        key=message_sort_key,
    )

    subset_data, selected_msgs, omitted_count, skipped_media_counts = build_image_export_subset(
        export_data,
        max_images=max_images if images else 0,
        max_image_mb=max_image_mb,
    )

    path_by_msg_id: dict[int, str] = {}
    failed_ids: list[int] = []
    if images and selected_msgs:
        subset_path = raw_dir / "images_only.json"
        subset_path.write_text(json.dumps(subset_data, ensure_ascii=False, indent=2), encoding="utf-8")
        path_by_msg_id, failed_ids, dl_warning = download_images(subset_path, images_dir, base_args, selected_msgs)
        if dl_warning:
            warnings.append(f"Image download warning: {dl_warning}")

    normalized_msgs: list[dict[str, Any]] = []
    image_records: list[dict[str, Any]] = []
    local_tz = datetime.now().astimezone().tzinfo or timezone.utc

    for msg in sorted_raw_msgs:
        raw_obj = msg.get("raw") if isinstance(msg.get("raw"), dict) else {}
        mid = int(msg.get("id") or raw_obj.get("ID") or 0)
        ts = int(msg.get("date") or raw_obj.get("Date") or 0)
        date_iso = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(local_tz).isoformat(timespec="seconds") if ts else ""
        kind, mime, filename, size_bytes = classify_media(msg, max_image_mb=max_image_mb)
        reply_to_id, topic_id = extract_reply_to(msg)
        normalized_msgs.append(
            {
                "id": mid,
                "date": ts,
                "date_iso": date_iso,
                "sender": extract_sender(msg, users_map),
                "reply_to_msg_id": reply_to_id,
                "topic_id": topic_id,
                "text": extract_text_and_links(msg),
                "media_kind": kind,
                "media_mime": mime,
                "media_filename": filename,
                "media_size_bytes": size_bytes,
            }
        )
        if mid in path_by_msg_id:
            image_records.append(
                {
                    "msg_id": mid,
                    "path": path_by_msg_id[mid],
                    "kind": kind,
                    "mime": mime,
                    "size_bytes": size_bytes,
                }
            )

    transcript_path = dest / "transcript.md"
    transcript_path.write_text(
        render_transcript(
            chat_meta,
            window_meta,
            normalized_msgs,
            path_by_msg_id,
            omitted_count=omitted_count,
            skipped_media_counts=skipped_media_counts,
            images_enabled=images,
        ),
        encoding="utf-8",
    )

    manifest = {
        "ok": True,
        "out_dir": str(dest),
        "transcript_path": str(transcript_path),
        "raw_export_path": str(export_path),
        "chat": {k: v for k, v in chat_meta.items() if k != "target"},
        "window": window_meta,
        "message_count": len(normalized_msgs),
        "users_resolved": len(users_map),
        "images_downloaded": len(image_records),
        "images_omitted": omitted_count,
        "images_failed": failed_ids,
        "images": image_records,
        "skipped_media_counts": skipped_media_counts,
        "warnings": warnings,
    }
    (dest / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--ns", default=argparse.SUPPRESS, help="tdl session namespace (default: default)")
    common.add_argument("--proxy", default=argparse.SUPPRESS, help="Proxy URL (overrides TDL_PROXY/ALL_PROXY/HTTPS_PROXY)")

    parser = argparse.ArgumentParser(
        description="Read-only Telegram group/channel export helper backed by tdl.",
        parents=[common],
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_doc = sub.add_parser("doctor", parents=[common], help="Check tdl installation, session presence, and proxy")
    p_doc.add_argument("--live", action="store_true", help="Also run `tdl chat ls -o json` to test live auth")

    p_list = sub.add_parser("list", parents=[common], help="List Telegram chats")
    p_list.add_argument("--query", default="", help="Case-insensitive filter against name, username, or ID")
    p_list.add_argument("--type", default="all", choices=["all", "group", "channel", "private"], help="Filter by dialog type")
    p_list.add_argument("--limit", type=int, default=DEFAULT_LIST_LIMIT, help="Max dialogs returned (default: 50)")

    p_fetch = sub.add_parser("fetch", parents=[common], help="Export chat transcript and images")
    p_fetch.add_argument("--chat", required=True, help="Numeric ID, @username, t.me link, or group name")
    window_group = p_fetch.add_mutually_exclusive_group()
    window_group.add_argument("--hours", type=float, default=None, help="Fetch last N hours (default: 24)")
    window_group.add_argument("--since", default=None, help="ISO start date/datetime (used with optional --until)")
    window_group.add_argument("--last", type=int, default=None, help="Fetch last N messages")
    window_group.add_argument("--id-range", default=None, help="Fetch message ID range '<start>,<end>'")
    p_fetch.add_argument("--until", default=None, help="Optional ISO end date/datetime when --since is set")
    p_fetch.add_argument("--topic", type=int, default=None, help="Forum topic ID")
    p_fetch.add_argument("--images", action=argparse.BooleanOptionalAction, default=True, help="Download image attachments")
    p_fetch.add_argument("--max-images", type=int, default=DEFAULT_MAX_IMAGES, help="Max most-recent images to download")
    p_fetch.add_argument("--max-image-mb", type=float, default=DEFAULT_MAX_IMAGE_MB, help="Max image document size in MB")
    p_fetch.add_argument(
        "--resolve-users",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Best-effort sender resolution via `tdl chat users`",
    )
    p_fetch.add_argument("--out", default=None, help="Output directory (default: /tmp/telegram-digest/<stamp>-<chat>)")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    ns = getattr(args, "ns", "default")
    proxy, proxy_source = resolve_proxy(getattr(args, "proxy", None))

    try:
        if args.command == "doctor":
            result = doctor_check(ns=ns, proxy=proxy, proxy_source=proxy_source, live=args.live)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.command == "list":
            result = list_chats(ns=ns, proxy=proxy, query=args.query, chat_type=args.type, limit=args.limit)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.command == "fetch":
            if args.until and not args.since:
                parser.error("--until requires --since")
            result = fetch_chat(
                chat_arg=args.chat,
                ns=ns,
                proxy=proxy,
                hours=args.hours,
                since=args.since,
                until=args.until,
                last=args.last,
                id_range=args.id_range,
                topic=args.topic,
                images=args.images,
                max_images=args.max_images,
                max_image_mb=args.max_image_mb,
                resolve_users=args.resolve_users,
                out_dir=args.out,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
    except ChatResolutionError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": str(exc),
                    "candidates": exc.candidates,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
