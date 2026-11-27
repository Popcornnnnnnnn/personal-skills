"""Offline unit and ffmpeg integration tests for flow_video_prep.py (no torch/network required)."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parent / "flow_video_prep.py"


def load_module():
    spec = importlib.util.spec_from_file_location("flow_video_prep", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


flow_video_prep = load_module()


class PureHelperTests(unittest.TestCase):
    def test_even_dimensions(self):
        self.assertEqual(flow_video_prep.even_dimensions(1280, 720), (1280, 720))
        self.assertEqual(flow_video_prep.even_dimensions(1281, 721), (1280, 720))
        self.assertEqual(flow_video_prep.even_dimensions(1, 1), (2, 2))
        self.assertEqual(flow_video_prep.even_dimensions(1920, 1080, max_side=720), (720, 404))
        self.assertEqual(flow_video_prep.even_dimensions(1080, 1920, max_side=720), (404, 720))
        with self.assertRaises(ValueError):
            flow_video_prep.even_dimensions(0, 720)
        with self.assertRaises(ValueError):
            flow_video_prep.even_dimensions(1280, 720, max_side=1)

    def test_resolve_model_id(self):
        self.assertEqual(
            flow_video_prep.resolve_model_id("small"),
            "depth-anything/Depth-Anything-V2-Small-hf",
        )
        self.assertEqual(
            flow_video_prep.resolve_model_id("BASE"),
            "depth-anything/Depth-Anything-V2-Base-hf",
        )
        self.assertEqual(
            flow_video_prep.resolve_model_id("large"),
            "depth-anything/Depth-Anything-V2-Large-hf",
        )
        self.assertEqual(flow_video_prep.resolve_model_id("custom/depth-model"), "custom/depth-model")
        with self.assertRaises(ValueError):
            flow_video_prep.resolve_model_id("huge")

    def test_smooth_bounds_window(self):
        self.assertEqual(flow_video_prep.smooth_bounds_window([], window=5), [])
        raw = [(0.0, 10.0), (3.0, 13.0), (6.0, 16.0)]
        self.assertEqual(flow_video_prep.smooth_bounds_window(raw, window=1), raw)
        smoothed = flow_video_prep.smooth_bounds_window(raw, window=3)
        self.assertAlmostEqual(smoothed[0][0], 1.5)
        self.assertAlmostEqual(smoothed[0][1], 11.5)
        self.assertAlmostEqual(smoothed[1][0], 3.0)
        self.assertAlmostEqual(smoothed[1][1], 13.0)
        self.assertAlmostEqual(smoothed[2][0], 4.5)
        self.assertAlmostEqual(smoothed[2][1], 14.5)
        with self.assertRaises(ValueError):
            flow_video_prep.smooth_bounds_window(raw, window=0)

    def test_smooth_bounds_ema(self):
        self.assertEqual(flow_video_prep.smooth_bounds_ema([], alpha=0.2), [])
        raw = [(0.0, 10.0), (4.0, 14.0)]
        smoothed = flow_video_prep.smooth_bounds_ema(raw, alpha=0.5)
        self.assertEqual(smoothed[0], (0.0, 10.0))
        self.assertAlmostEqual(smoothed[1][0], 2.0)
        self.assertAlmostEqual(smoothed[1][1], 12.0)
        with self.assertRaises(ValueError):
            flow_video_prep.smooth_bounds_ema(raw, alpha=0.0)

    def test_normalize_depth_values(self):
        self.assertEqual(
            flow_video_prep.normalize_depth_values([-1.0, 0.0, 5.0, 10.0, 12.0], 0.0, 10.0),
            [0, 0, 128, 255, 255],
        )
        self.assertEqual(
            flow_video_prep.normalize_depth_values([0.0, 10.0], 0.0, 10.0, invert=True),
            [255, 0],
        )
        self.assertEqual(flow_video_prep.normalize_depth_values([3.0, 3.0], 3.0, 3.0), [128, 128])

    def test_build_blur_corners_filter(self):
        flt = flow_video_prep.build_blur_corners_filter(320, 180, 0.12)
        self.assertIn("boxblur=", flt)
        self.assertIn("[vout]", flt)
        with self.assertRaises(ValueError):
            flow_video_prep.build_blur_corners_filter(320, 180, 0.0)
        with self.assertRaises(ValueError):
            flow_video_prep.build_blur_corners_filter(320, 180, 0.3)


@unittest.skipUnless(
    shutil.which("ffmpeg") and shutil.which("ffprobe"),
    "ffmpeg/ffprobe required for synthetic media pipeline tests",
)
class FfmpegPipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="flow-prep-test-")
        self.root = Path(self.tmp.name)
        self.src = self.root / "src.mp4"
        cmd = [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x180:rate=12",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1",
            "-t",
            "1",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(self.src),
        ]
        subprocess.run(cmd, check=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _run_cli(self, *cli_args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT_PATH), *cli_args],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_probe_prep_remux_and_compare(self):
        # 1. probe
        res_probe = self._run_cli("probe", str(self.src))
        self.assertEqual(res_probe.returncode, 0, res_probe.stderr)
        probed = json.loads(res_probe.stdout)
        self.assertEqual(probed["width"], 320)
        self.assertEqual(probed["height"], 180)
        self.assertTrue(probed["has_audio"])
        self.assertTrue(probed["fits_flow_15s"])
        self.assertTrue(probed["fits_gemini_api_10s"])

        # 2. prep (strip audio + blur corners)
        silent = self.root / "silent.mp4"
        res_prep = self._run_cli(
            "prep",
            str(self.src),
            "-o",
            str(silent),
            "--strip-audio",
            "--blur-corners",
            "0.12",
        )
        self.assertEqual(res_prep.returncode, 0, res_prep.stderr)
        prepped = json.loads(res_prep.stdout)
        self.assertFalse(prepped["has_audio"])
        self.assertTrue(prepped["stripped_audio"])
        silent_probe = flow_video_prep.probe_media(silent)
        self.assertEqual(silent_probe["video_codec"], "h264")
        self.assertFalse(silent_probe["has_audio"])

        # 3. remux audio back onto silent MP4
        remuxed = self.root / "remuxed.mp4"
        res_remux = self._run_cli(
            "remux",
            "--video",
            str(silent),
            "--audio-from",
            str(self.src),
            "-o",
            str(remuxed),
        )
        self.assertEqual(res_remux.returncode, 0, res_remux.stderr)
        remux_data = json.loads(res_remux.stdout)
        self.assertTrue(remux_data["has_audio"])

        # remux from a silent source must fail cleanly
        bad_remux = self.root / "bad_remux.mp4"
        res_bad = self._run_cli(
            "remux",
            "--video",
            str(silent),
            "--audio-from",
            str(silent),
            "-o",
            str(bad_remux),
        )
        self.assertNotEqual(res_bad.returncode, 0)
        self.assertIn("no audio track", res_bad.stderr.lower())

        # 4. compare 4-frame contact sheet
        sheet = self.root / "compare.png"
        res_cmp = self._run_cli(
            "compare",
            "--original",
            str(self.src),
            "--generated",
            str(remuxed),
            "-o",
            str(sheet),
            "--frames",
            "4",
        )
        self.assertEqual(res_cmp.returncode, 0, res_cmp.stderr)
        cmp_data = json.loads(res_cmp.stdout)
        self.assertEqual(cmp_data["frames"], 4)
        self.assertTrue(sheet.is_file())
        self.assertGreater(sheet.stat().st_size, 1000)
        self.assertEqual(sheet.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")


if __name__ == "__main__":
    unittest.main()
