#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "torch>=2.4",
#   "transformers>=4.46",
#   "numpy>=1.26",
#   "pillow>=10.0",
# ]
# ///
"""Media prep, local Depth-Anything-V2 depth-map conversion, audio remux, and QA sheets for Google Flow."""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from fractions import Fraction
from pathlib import Path
from typing import Any

MODEL_ALIASES = {
    "small": "depth-anything/Depth-Anything-V2-Small-hf",
    "base": "depth-anything/Depth-Anything-V2-Base-hf",
    "large": "depth-anything/Depth-Anything-V2-Large-hf",
}


def even_dimensions(width: int, height: int, max_side: int | None = None) -> tuple[int, int]:
    """Return positive even dimensions, optionally scaling down so max(w, h) <= max_side."""
    if width <= 0 or height <= 0:
        raise ValueError(f"Width and height must be positive, got {width}x{height}")
    w, h = float(width), float(height)
    if max_side is not None:
        if max_side < 2:
            raise ValueError(f"max_side must be >= 2, got {max_side}")
        longest = max(w, h)
        if longest > max_side:
            scale = max_side / longest
            w *= scale
            h *= scale
    ew = max(2, (int(round(w)) // 2) * 2)
    eh = max(2, (int(round(h)) // 2) * 2)
    if max_side is not None:
        if ew > max_side:
            ew = max(2, (max_side // 2) * 2)
        if eh > max_side:
            eh = max(2, (max_side // 2) * 2)
    return ew, eh


def resolve_model_id(name: str) -> str:
    """Map shorthand ('small', 'base', 'large') or pass through an org/model identifier."""
    cleaned = name.strip()
    if not cleaned:
        raise ValueError("Model name cannot be empty")
    lower = cleaned.lower()
    if lower in MODEL_ALIASES:
        return MODEL_ALIASES[lower]
    if "/" in cleaned:
        return cleaned
    raise ValueError(
        f"Unknown model shorthand {name!r}; expected one of {sorted(MODEL_ALIASES)} or 'org/model'"
    )


def smooth_bounds_window(
    bounds: list[tuple[float, float]], window: int = 15
) -> list[tuple[float, float]]:
    """Smooth per-frame (lo, hi) depth bounds using a centered rolling mean."""
    if window < 1:
        raise ValueError(f"window must be >= 1, got {window}")
    if not bounds:
        return []
    n = len(bounds)
    half = window // 2
    out: list[tuple[float, float]] = []
    for i in range(n):
        start = max(0, i - half)
        end = min(n, i + half + 1)
        count = end - start
        mean_lo = sum(bounds[j][0] for j in range(start, end)) / count
        mean_hi = sum(bounds[j][1] for j in range(start, end)) / count
        out.append((mean_lo, mean_hi))
    return out


def smooth_bounds_ema(
    bounds: list[tuple[float, float]], alpha: float = 0.15
) -> list[tuple[float, float]]:
    """Smooth per-frame (lo, hi) depth bounds using causal exponential moving average."""
    if not (0.0 < alpha <= 1.0):
        raise ValueError(f"alpha must be in (0, 1], got {alpha}")
    if not bounds:
        return []
    ema_lo = float(bounds[0][0])
    ema_hi = float(bounds[0][1])
    out: list[tuple[float, float]] = [(ema_lo, ema_hi)]
    for lo, hi in bounds[1:]:
        ema_lo = alpha * float(lo) + (1.0 - alpha) * ema_lo
        ema_hi = alpha * float(hi) + (1.0 - alpha) * ema_hi
        out.append((ema_lo, ema_hi))
    return out


def normalize_depth_values(
    values: list[float], lo: float, hi: float, invert: bool = False
) -> list[int]:
    """Normalize scalar depth values to 0..255 uint8 ints (flat guard -> 128)."""
    if hi <= lo + 1e-6:
        return [128 for _ in values]
    span = hi - lo
    out: list[int] = []
    for x in values:
        t = min(1.0, max(0.0, (x - lo) / span))
        v = int(round(t * 255.0))
        if invert:
            v = 255 - v
        out.append(v)
    return out


def build_blur_corners_filter(width: int, height: int, ratio: float) -> str:
    """Build an ffmpeg -filter_complex string that blurs the 4 corners onto [vout]."""
    if width <= 0 or height <= 0:
        raise ValueError(f"Width and height must be positive, got {width}x{height}")
    if not (0.0 < ratio <= 0.25):
        raise ValueError(f"Corner blur ratio must be in (0, 0.25], got {ratio}")
    cw = max(16, (int(round(width * ratio)) // 2) * 2)
    ch = max(16, (int(round(height * ratio)) // 2) * 2)
    cw = min(cw, max(2, (width // 2) * 2))
    ch = min(ch, max(2, (height // 2) * 2))
    luma_radius = min(8, max(1, (min(cw, ch) // 2) - 1))
    chroma_radius = min(luma_radius, max(1, (min(cw, ch) // 4) - 1))
    rx = width - cw
    by = height - ch
    return (
        f"[0:v]split=5[base][c0][c1][c2][c3];"
        f"[c0]crop={cw}:{ch}:0:0,boxblur={luma_radius}:2:{chroma_radius}:2[b0];"
        f"[c1]crop={cw}:{ch}:{rx}:0,boxblur={luma_radius}:2:{chroma_radius}:2[b1];"
        f"[c2]crop={cw}:{ch}:0:{by},boxblur={luma_radius}:2:{chroma_radius}:2[b2];"
        f"[c3]crop={cw}:{ch}:{rx}:{by},boxblur={luma_radius}:2:{chroma_radius}:2[b3];"
        f"[base][b0]overlay=0:0[t0];"
        f"[t0][b1]overlay={rx}:0[t1];"
        f"[t1][b2]overlay=0:{by}[t2];"
        f"[t2][b3]overlay={rx}:{by}[vout]"
    )


def _require_bin(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"Required executable {name!r} was not found in PATH")
    return path


def _parse_fps(rate_str: str | None) -> float:
    if not rate_str or rate_str == "0/0":
        return 0.0
    try:
        val = float(Fraction(rate_str))
        return val if math.isfinite(val) and val > 0 else 0.0
    except Exception:
        return 0.0


def probe_media(path: str | Path) -> dict[str, Any]:
    """Run ffprobe on path and return structured video/audio metadata."""
    ffprobe = _require_bin("ffprobe")
    target = Path(path).expanduser().resolve()
    if not target.is_file():
        raise FileNotFoundError(f"Media file not found: {target}")
    cmd = [
        ffprobe,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(target),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {target}: {res.stderr.strip()}")
    data = json.loads(res.stdout)
    streams = data.get("streams", [])
    fmt = data.get("format", {})

    v_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    a_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if not v_stream:
        raise RuntimeError(f"No video stream found in {target}")

    width = int(v_stream.get("width", 0))
    height = int(v_stream.get("height", 0))
    fps = _parse_fps(v_stream.get("avg_frame_rate")) or _parse_fps(v_stream.get("r_frame_rate"))
    if fps <= 0:
        fps = 24.0

    dur_raw = fmt.get("duration") or v_stream.get("duration") or 0.0
    duration_sec = round(float(dur_raw), 3)

    return {
        "ok": True,
        "path": str(target),
        "width": width,
        "height": height,
        "fps": round(fps, 4),
        "video_codec": v_stream.get("codec_name", ""),
        "has_audio": a_stream is not None,
        "audio_codec": a_stream.get("codec_name", "") if a_stream else None,
        "duration_sec": duration_sec,
        "fits_flow_15s": duration_sec <= 15.05,
        "fits_gemini_api_10s": duration_sec <= 10.05,
    }


def _read_exact(stream: Any, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining > 0:
        chunk = stream.read(remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def cmd_probe(args: argparse.Namespace) -> dict[str, Any]:
    return probe_media(args.input)


def cmd_prep(args: argparse.Namespace) -> dict[str, Any]:
    ffmpeg = _require_bin("ffmpeg")
    src = Path(args.input).expanduser().resolve()
    out = Path(args.output).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    meta = probe_media(src)
    src_w, src_h = meta["width"], meta["height"]
    out_w, out_h = even_dimensions(src_w, src_h, args.max_side)

    eff_dur: float | None = None
    if args.duration is not None and args.max_duration is not None:
        eff_dur = min(args.duration, args.max_duration)
    elif args.duration is not None:
        eff_dur = args.duration
    elif args.max_duration is not None:
        avail = max(0.0, meta["duration_sec"] - (args.start or 0.0))
        if avail > args.max_duration:
            eff_dur = args.max_duration

    cmd: list[str] = [ffmpeg, "-nostdin", "-y"]
    if args.start is not None and args.start > 0:
        cmd += ["-ss", f"{args.start:.3f}"]
    cmd += ["-i", str(src)]
    if eff_dur is not None:
        if eff_dur <= 0:
            raise ValueError(f"Effective duration must be > 0, got {eff_dur}")
        cmd += ["-t", f"{eff_dur:.3f}"]

    needs_scale = (out_w != src_w) or (out_h != src_h)
    keep_audio = bool(args.keep_audio and meta["has_audio"])

    if args.blur_corners is not None:
        blur_graph = build_blur_corners_filter(out_w, out_h, args.blur_corners)
        if needs_scale:
            # Replace initial [0:v] in blur graph with scaled [vscaled]
            blur_graph = f"[0:v]scale={out_w}:{out_h}[vscaled];" + blur_graph.replace(
                "[0:v]", "[vscaled]", 1
            )
        cmd += ["-filter_complex", blur_graph, "-map", "[vout]"]
        if keep_audio:
            cmd += ["-map", "0:a?"]
    else:
        if needs_scale:
            cmd += ["-vf", f"scale={out_w}:{out_h}"]

    cmd += [
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
    ]
    if keep_audio:
        cmd += ["-c:a", "aac", "-b:a", "192k"]
    else:
        cmd += ["-an"]
    cmd += ["-movflags", "+faststart", str(out)]

    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg prep failed: {res.stderr.strip()}")

    out_meta = probe_media(out)
    return {
        "ok": True,
        "input": str(src),
        "output": str(out),
        "stripped_audio": not keep_audio,
        "blurred_corners": args.blur_corners,
        "width": out_meta["width"],
        "height": out_meta["height"],
        "fps": out_meta["fps"],
        "has_audio": out_meta["has_audio"],
        "duration_sec": out_meta["duration_sec"],
        "fits_flow_15s": out_meta["fits_flow_15s"],
        "fits_gemini_api_10s": out_meta["fits_gemini_api_10s"],
    }


def _select_device(requested: str, torch_mod: Any) -> str:
    if requested == "auto":
        if torch_mod.backends.mps.is_available():
            return "mps"
        if torch_mod.cuda.is_available():
            return "cuda"
        return "cpu"
    if requested == "mps" and not torch_mod.backends.mps.is_available():
        raise RuntimeError("Requested device 'mps', but torch.backends.mps.is_available() is False")
    if requested == "cuda" and not torch_mod.cuda.is_available():
        raise RuntimeError("Requested device 'cuda', but torch.cuda.is_available() is False")
    return requested


def cmd_depth(args: argparse.Namespace) -> dict[str, Any]:
    import numpy as np
    import torch
    import torch.nn.functional as F
    from PIL import Image
    from transformers import AutoImageProcessor, AutoModelForDepthEstimation

    ffmpeg = _require_bin("ffmpeg")
    src = Path(args.input).expanduser().resolve()
    out = Path(args.output).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    model_id = resolve_model_id(args.model)
    device = _select_device(args.device, torch)
    meta = probe_media(src)

    src_w, src_h, src_fps, src_dur = meta["width"], meta["height"], meta["fps"], meta["duration_sec"]
    out_w, out_h = even_dimensions(src_w, src_h, args.max_side)
    out_fps = min(src_fps, args.max_fps) if (args.max_fps and args.max_fps > 0) else src_fps
    if out_fps <= 0:
        out_fps = 24.0

    start = args.start or 0.0
    avail_dur = max(0.0, src_dur - start)
    eff_dur = min(args.duration, avail_dur) if args.duration is not None else avail_dur
    est_frames = int(math.ceil(eff_dur * out_fps)) if eff_dur > 0 else 0

    if args.norm_mode == "window":
        norm_mode = "window"
    elif args.norm_mode == "ema":
        norm_mode = "ema"
    else:
        norm_mode = "window" if est_frames <= 600 else "ema"

    print(
        f"[flow_video_prep] Loading {model_id} on {device} (norm={norm_mode}, out={out_w}x{out_h}@{out_fps:.2f}fps)...",
        file=sys.stderr,
    )
    t0 = time.monotonic()
    processor = AutoImageProcessor.from_pretrained(model_id)
    model = AutoModelForDepthEstimation.from_pretrained(model_id).to(device)
    model.eval()

    dec_cmd: list[str] = [ffmpeg, "-nostdin", "-v", "error"]
    if start > 0:
        dec_cmd += ["-ss", f"{start:.3f}"]
    dec_cmd += ["-i", str(src)]
    if args.duration is not None:
        dec_cmd += ["-t", f"{args.duration:.3f}"]

    vf_parts: list[str] = []
    if args.max_fps and args.max_fps > 0 and src_fps > args.max_fps + 1e-3:
        vf_parts.append(f"fps={out_fps:.4f}")
    if out_w != src_w or out_h != src_h:
        vf_parts.append(f"scale={out_w}:{out_h}")
    if vf_parts:
        dec_cmd += ["-vf", ",".join(vf_parts)]
    dec_cmd += ["-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"]

    enc_cmd: list[str] = [
        ffmpeg,
        "-nostdin",
        "-v",
        "error",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "gray",
        "-s",
        f"{out_w}x{out_h}",
        "-r",
        f"{out_fps:.4f}",
        "-i",
        "pipe:0",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-an",
        "-movflags",
        "+faststart",
        str(out),
    ]

    frame_byte_count = out_w * out_h * 3
    batch_size = max(1, int(args.batch_size))
    invert = bool(args.invert)

    dec = subprocess.Popen(dec_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert dec.stdout is not None and dec.stderr is not None

    def _to_uint8_frame(arr: Any, lo: float, hi: float) -> bytes:
        if hi <= lo + 1e-6:
            u8 = np.full(arr.shape, 128, dtype=np.uint8)
        else:
            scaled = np.clip((arr - lo) / (hi - lo), 0.0, 1.0)
            u8 = np.rint(scaled * 255.0).astype(np.uint8)
            if invert:
                u8 = 255 - u8
        return u8.tobytes()

    frame_count = 0
    if norm_mode == "window":
        stored_maps: list[Any] = []
        raw_bounds: list[tuple[float, float]] = []

        def _process_window_batch(batch_imgs: list[Any]) -> None:
            nonlocal frame_count
            inputs = processor(images=batch_imgs, return_tensors="pt")
            inputs = {k: v.to(device) for k, v in inputs.items()}
            with torch.inference_mode():
                pred = model(**inputs).predicted_depth.to(dtype=torch.float32)
            pred_cpu = pred.cpu()
            for idx in range(pred_cpu.shape[0]):
                f_np = pred_cpu[idx].numpy()
                lo, hi = np.percentile(f_np, [2.0, 98.0])
                raw_bounds.append((float(lo), float(hi)))
                stored_maps.append(pred_cpu[idx].to(dtype=torch.float16))
                frame_count += 1

        batch_imgs: list[Any] = []
        while True:
            raw = _read_exact(dec.stdout, frame_byte_count)
            if len(raw) < frame_byte_count:
                break
            arr = np.frombuffer(raw, dtype=np.uint8).reshape((out_h, out_w, 3))
            batch_imgs.append(Image.fromarray(arr))
            if len(batch_imgs) >= batch_size:
                _process_window_batch(batch_imgs)
                batch_imgs.clear()
                if frame_count % 48 == 0:
                    print(f"[flow_video_prep] Inferred {frame_count} frames...", file=sys.stderr)
        if batch_imgs:
            _process_window_batch(batch_imgs)
            batch_imgs.clear()

        dec_err = dec.stderr.read().decode("utf-8", errors="replace")
        dec_rc = dec.wait()
        if dec_rc != 0:
            raise RuntimeError(f"ffmpeg decode failed ({dec_rc}): {dec_err.strip()}")
        if frame_count == 0:
            raise RuntimeError("No frames decoded from input video")

        smoothed = smooth_bounds_window(raw_bounds, window=args.window)
        enc = subprocess.Popen(enc_cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        assert enc.stdin is not None and enc.stderr is not None

        for i in range(0, frame_count, batch_size):
            chunk = torch.stack(stored_maps[i : i + batch_size]).to(device=device, dtype=torch.float32)
            up = F.interpolate(
                chunk.unsqueeze(1), size=(out_h, out_w), mode="bilinear", align_corners=False
            ).squeeze(1)
            up_np = up.cpu().numpy()
            for j in range(up_np.shape[0]):
                lo, hi = smoothed[i + j]
                enc.stdin.write(_to_uint8_frame(up_np[j], lo, hi))

        enc.stdin.close()
        enc_err = enc.stderr.read().decode("utf-8", errors="replace")
        enc_rc = enc.wait()
        if enc_rc != 0:
            raise RuntimeError(f"ffmpeg encode failed ({enc_rc}): {enc_err.strip()}")
    else:
        enc = subprocess.Popen(enc_cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        assert enc.stdin is not None and enc.stderr is not None
        ema_lo: float | None = None
        ema_hi: float | None = None
        alpha = float(args.ema_alpha)

        def _process_ema_batch(batch_imgs: list[Any]) -> None:
            nonlocal frame_count, ema_lo, ema_hi
            inputs = processor(images=batch_imgs, return_tensors="pt")
            inputs = {k: v.to(device) for k, v in inputs.items()}
            with torch.inference_mode():
                pred = model(**inputs).predicted_depth.to(dtype=torch.float32)
                up = F.interpolate(
                    pred.unsqueeze(1), size=(out_h, out_w), mode="bilinear", align_corners=False
                ).squeeze(1)
            up_np = up.cpu().numpy()
            for idx in range(up_np.shape[0]):
                f_np = up_np[idx]
                lo, hi = np.percentile(f_np, [2.0, 98.0])
                if ema_lo is None or ema_hi is None:
                    ema_lo, ema_hi = float(lo), float(hi)
                else:
                    ema_lo = alpha * float(lo) + (1.0 - alpha) * ema_lo
                    ema_hi = alpha * float(hi) + (1.0 - alpha) * ema_hi
                assert enc.stdin is not None
                enc.stdin.write(_to_uint8_frame(f_np, ema_lo, ema_hi))
                frame_count += 1

        batch_imgs = []
        while True:
            raw = _read_exact(dec.stdout, frame_byte_count)
            if len(raw) < frame_byte_count:
                break
            arr = np.frombuffer(raw, dtype=np.uint8).reshape((out_h, out_w, 3))
            batch_imgs.append(Image.fromarray(arr))
            if len(batch_imgs) >= batch_size:
                _process_ema_batch(batch_imgs)
                batch_imgs.clear()
                if frame_count % 48 == 0:
                    print(f"[flow_video_prep] Encoded {frame_count} frames...", file=sys.stderr)
        if batch_imgs:
            _process_ema_batch(batch_imgs)
            batch_imgs.clear()

        dec_err = dec.stderr.read().decode("utf-8", errors="replace")
        dec_rc = dec.wait()
        enc.stdin.close()
        enc_err = enc.stderr.read().decode("utf-8", errors="replace")
        enc_rc = enc.wait()
        if dec_rc != 0:
            raise RuntimeError(f"ffmpeg decode failed ({dec_rc}): {dec_err.strip()}")
        if frame_count == 0:
            raise RuntimeError("No frames decoded from input video")
        if enc_rc != 0:
            raise RuntimeError(f"ffmpeg encode failed ({enc_rc}): {enc_err.strip()}")

    elapsed = round(time.monotonic() - t0, 3)
    out_meta = probe_media(out)
    result: dict[str, Any] = {
        "ok": True,
        "input": str(src),
        "output": str(out),
        "model_id": model_id,
        "device": device,
        "norm_mode": norm_mode,
        "invert": invert,
        "frames": frame_count,
        "width": out_meta["width"],
        "height": out_meta["height"],
        "fps": out_meta["fps"],
        "duration_sec": out_meta["duration_sec"],
        "elapsed_sec": elapsed,
        "throughput_fps": round(frame_count / max(elapsed, 1e-6), 2),
        "has_audio": out_meta["has_audio"],
        "fits_flow_15s": out_meta["fits_flow_15s"],
    }
    if not out_meta["fits_flow_15s"]:
        result["warning"] = (
            f"Output duration {out_meta['duration_sec']}s exceeds Google Flow's ~15s reference cap; "
            "trim into <=15s segments with `prep` before uploading."
        )
    return result


def cmd_remux(args: argparse.Namespace) -> dict[str, Any]:
    ffmpeg = _require_bin("ffmpeg")
    vid = Path(args.video).expanduser().resolve()
    audio_src = Path(args.audio_from).expanduser().resolve()
    out = Path(args.output).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    probe_media(vid)
    audio_meta = probe_media(audio_src)
    if not audio_meta["has_audio"]:
        raise RuntimeError(f"Source has no audio track: {audio_src}")

    cmd: list[str] = [ffmpeg, "-nostdin", "-y", "-i", str(vid)]
    if args.audio_start is not None and args.audio_start > 0:
        cmd += ["-ss", f"{args.audio_start:.3f}"]
    cmd += [
        "-i",
        str(audio_src),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        "-movflags",
        "+faststart",
        str(out),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg remux failed: {res.stderr.strip()}")

    out_meta = probe_media(out)
    return {
        "ok": True,
        "video": str(vid),
        "audio_from": str(audio_src),
        "output": str(out),
        "width": out_meta["width"],
        "height": out_meta["height"],
        "has_audio": out_meta["has_audio"],
        "audio_codec": out_meta["audio_codec"],
        "duration_sec": out_meta["duration_sec"],
    }


def cmd_compare(args: argparse.Namespace) -> dict[str, Any]:
    ffmpeg = _require_bin("ffmpeg")
    orig = Path(args.original).expanduser().resolve()
    gen = Path(args.generated).expanduser().resolve()
    out = Path(args.output).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    orig_meta = probe_media(orig)
    gen_meta = probe_media(gen)

    n_frames = max(1, int(args.frames))
    tile_h = max(64, (int(args.tile_height) // 2) * 2)
    orig_start = float(args.orig_start or 0.0)
    avail_orig = max(0.0, orig_meta["duration_sec"] - orig_start)
    span = min(avail_orig, gen_meta["duration_sec"])
    if span <= 0:
        raise ValueError(
            f"Non-positive comparison span: orig_avail={avail_orig}s, gen={gen_meta['duration_sec']}s"
        )

    timestamps = [round((i + 0.5) * span / n_frames, 3) for i in range(n_frames)]

    with tempfile.TemporaryDirectory(prefix="flow-compare-") as tmpdir:
        tmp = Path(tmpdir)
        orig_tiles: list[Path] = []
        gen_tiles: list[Path] = []
        for idx, t in enumerate(timestamps):
            op = tmp / f"orig_{idx:02d}.png"
            gp = tmp / f"gen_{idx:02d}.png"
            for src_path, ts, dst in ((orig, orig_start + t, op), (gen, t, gp)):
                cmd = [
                    ffmpeg,
                    "-nostdin",
                    "-v",
                    "error",
                    "-y",
                    "-ss",
                    f"{ts:.3f}",
                    "-i",
                    str(src_path),
                    "-frames:v",
                    "1",
                    "-vf",
                    f"scale=-2:{tile_h}",
                    str(dst),
                ]
                res = subprocess.run(cmd, capture_output=True, text=True, check=False)
                if res.returncode != 0 or not dst.is_file():
                    raise RuntimeError(
                        f"Failed extracting comparison frame at t={ts:.3f}s from {src_path}: {res.stderr.strip()}"
                    )
            orig_tiles.append(op)
            gen_tiles.append(gp)

        sheet_w, sheet_h = _compose_contact_sheet(
            orig_tiles, gen_tiles, timestamps, out, ffmpeg
        )

    return {
        "ok": True,
        "original": str(orig),
        "generated": str(gen),
        "output": str(out),
        "frames": n_frames,
        "timestamps": timestamps,
        "width": sheet_w,
        "height": sheet_h,
    }


def _compose_contact_sheet(
    orig_tiles: list[Path],
    gen_tiles: list[Path],
    timestamps: list[float],
    output: Path,
    ffmpeg: str,
) -> tuple[int, int]:
    try:
        from PIL import Image, ImageDraw, ImageFont

        pad = 8
        header_h = 26
        o_imgs = [Image.open(p).convert("RGB") for p in orig_tiles]
        g_imgs = [Image.open(p).convert("RGB") for p in gen_tiles]

        col_widths = [max(o.width, g.width) for o, g in zip(o_imgs, g_imgs)]
        top_h = max(im.height for im in o_imgs)
        bot_h = max(im.height for im in g_imgs)

        sheet_w = pad + sum(w + pad for w in col_widths)
        sheet_h = pad + (header_h + top_h) + pad + (header_h + bot_h) + pad
        canvas = Image.new("RGB", (sheet_w, sheet_h), (18, 22, 30))
        draw = ImageDraw.Draw(canvas)
        font = ImageFont.load_default()

        x = pad
        for idx, (o_im, g_im, t) in enumerate(zip(o_imgs, g_imgs, timestamps)):
            cw = col_widths[idx]
            y_top = pad
            draw.rectangle([x, y_top, x + cw - 1, y_top + header_h - 2], fill=(32, 41, 56))
            draw.text((x + 6, y_top + 6), f"ORIG  t={t:.2f}s", fill=(160, 212, 255), font=font)
            canvas.paste(o_im, (x + (cw - o_im.width) // 2, y_top + header_h))

            y_bot = pad + header_h + top_h + pad
            draw.rectangle([x, y_bot, x + cw - 1, y_bot + header_h - 2], fill=(32, 46, 40))
            draw.text((x + 6, y_bot + 6), f"GEN   t={t:.2f}s", fill=(140, 240, 190), font=font)
            canvas.paste(g_im, (x + (cw - g_im.width) // 2, y_bot + header_h))

            x += cw + pad

        canvas.save(output, format="PNG")
        return sheet_w, sheet_h
    except ImportError:
        # Pure-ffmpeg fallback when Pillow is absent in plain python3 environments.
        with tempfile.TemporaryDirectory(prefix="flow-sheet-") as tmpdir:
            tmp = Path(tmpdir)
            row1 = tmp / "row_orig.png"
            row2 = tmp / "row_gen.png"
            n = len(orig_tiles)
            for tiles, row_out in ((orig_tiles, row1), (gen_tiles, row2)):
                if n == 1:
                    shutil.copyfile(tiles[0], row_out)
                else:
                    cmd = [ffmpeg, "-nostdin", "-v", "error", "-y"]
                    for p in tiles:
                        cmd += ["-i", str(p)]
                    cmd += ["-filter_complex", f"hstack=inputs={n}", str(row_out)]
                    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
                    if res.returncode != 0:
                        raise RuntimeError(f"ffmpeg hstack failed: {res.stderr.strip()}")
            cmd = [
                ffmpeg,
                "-nostdin",
                "-v",
                "error",
                "-y",
                "-i",
                str(row1),
                "-i",
                str(row2),
                "-filter_complex",
                "[0:v][1:v]vstack=inputs=2",
                str(output),
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if res.returncode != 0:
                raise RuntimeError(f"ffmpeg vstack failed: {res.stderr.strip()}")
        meta = probe_media(output)
        return meta["width"], meta["height"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="flow_video_prep.py",
        description="Video probe, trim/corner-blur prep, local MPS Depth-Anything-V2 converter, audio remux, and QA contact sheet generator.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_probe = sub.add_parser("probe", help="Inspect video/audio stream metadata via ffprobe.")
    p_probe.add_argument("input", help="Input video path")
    p_probe.set_defaults(func=cmd_probe)

    p_prep = sub.add_parser("prep", help="Trim, optionally blur corners, scale, and strip audio.")
    p_prep.add_argument("input", help="Input video path")
    p_prep.add_argument("-o", "--output", required=True, help="Output MP4 path")
    p_prep.add_argument("--start", type=float, default=None, help="Start offset in seconds")
    p_prep.add_argument("--duration", type=float, default=None, help="Target clip duration in seconds")
    p_prep.add_argument("--max-duration", type=float, default=None, help="Cap duration to at most N seconds")
    audio_grp = p_prep.add_mutually_exclusive_group()
    audio_grp.add_argument("--keep-audio", action="store_true", help="Keep and re-encode audio as AAC")
    audio_grp.add_argument("--strip-audio", action="store_true", help="Strip audio track (default)")
    p_prep.add_argument("--max-side", type=int, default=None, help="Scale down longest edge to <= N pixels")
    p_prep.add_argument(
        "--blur-corners",
        type=float,
        default=None,
        help="Blur each of the 4 corners using box size ratio in (0, 0.25]",
    )
    p_prep.set_defaults(func=cmd_prep)

    p_depth = sub.add_parser("depth", help="Convert a video to a Depth-Anything-V2 grayscale depth MP4.")
    p_depth.add_argument("input", help="Input video path")
    p_depth.add_argument("-o", "--output", required=True, help="Output silent H.264 depth MP4 path")
    p_depth.add_argument(
        "--model",
        default="small",
        help="Depth-Anything-V2 size ('small', 'base', 'large') or HuggingFace model ID",
    )
    p_depth.add_argument(
        "--device",
        choices=("auto", "mps", "cuda", "cpu"),
        default="auto",
        help="Torch inference device (default: auto)",
    )
    p_depth.add_argument("--batch-size", type=int, default=8, help="Frames per inference batch (default: 8)")
    p_depth.add_argument("--start", type=float, default=None, help="Start offset in seconds")
    p_depth.add_argument("--duration", type=float, default=None, help="Clip duration in seconds")
    p_depth.add_argument("--max-fps", type=float, default=None, help="Cap output FPS if source exceeds N")
    p_depth.add_argument("--max-side", type=int, default=None, help="Cap longest edge to N pixels")
    p_depth.add_argument(
        "--norm-mode",
        choices=("auto", "window", "ema"),
        default="auto",
        help="Temporal normalization mode (default: auto -> window for <=600 frames, else ema)",
    )
    p_depth.add_argument("--window", type=int, default=15, help="Centered rolling window size (default: 15)")
    p_depth.add_argument("--ema-alpha", type=float, default=0.15, help="EMA smoothing alpha (default: 0.15)")
    p_depth.add_argument(
        "--invert",
        action="store_true",
        help="Invert brightness (default: False -> near=bright/white, far=dark/black)",
    )
    p_depth.set_defaults(func=cmd_depth)

    p_remux = sub.add_parser("remux", help="Mux original audio track onto generated silent video.")
    p_remux.add_argument("--video", required=True, help="Generated video path")
    p_remux.add_argument("--audio-from", required=True, help="Original video carrying audio track")
    p_remux.add_argument("--audio-start", type=float, default=None, help="Optional audio start offset (s)")
    p_remux.add_argument("-o", "--output", required=True, help="Output MP4 path")
    p_remux.set_defaults(func=cmd_remux)

    p_cmp = sub.add_parser("compare", help="Build a 2-row N-frame original-vs-generated PNG contact sheet.")
    p_cmp.add_argument("--original", required=True, help="Original video path")
    p_cmp.add_argument("--generated", required=True, help="Generated video path")
    p_cmp.add_argument("-o", "--output", required=True, help="Output PNG path")
    p_cmp.add_argument("--frames", type=int, default=6, help="Sample frame count (default: 6)")
    p_cmp.add_argument("--tile-height", type=int, default=360, help="Tile height in pixels (default: 360)")
    p_cmp.add_argument("--orig-start", type=float, default=0.0, help="Start offset inside original video (s)")
    p_cmp.set_defaults(func=cmd_compare)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = args.func(args)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
