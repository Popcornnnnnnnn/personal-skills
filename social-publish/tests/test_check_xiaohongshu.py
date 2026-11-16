"""Unit tests for RedNote (Xiaohongshu) local package preflight checker."""
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib

SCRIPT_PATH = Path(__file__).resolve().parent.parent / 'scripts/check_xiaohongshu.py'
SPEC = importlib.util.spec_from_file_location('check_xiaohongshu', SCRIPT_PATH)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def make_png(width: int, height: int) -> bytes:
    def chunk(tag: bytes, payload: bytes) -> bytes:
        crc = zlib.crc32(tag + payload) & 0xFFFFFFFF
        return struct.pack('>I', len(payload)) + tag + payload + struct.pack('>I', crc)

    ihdr = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    # Minimal valid 1x1 scanline data is only read if fully decoded; check_xiaohongshu reads IHDR.
    raw = b'\x00\x00\x00\x00'
    idat = zlib.compress(raw)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) + chunk(b'IDAT', idat) + chunk(b'IEND', b'')


def make_jpeg_with_exif_orientation(raw_w: int, raw_h: int, orientation: int) -> bytes:
    # Minimal TIFF little-endian IFD0 with tag 0x0112 (Orientation, SHORT=3, count=1)
    ifd = struct.pack('<H', 1) + struct.pack('<HHII', 0x0112, 3, 1, orientation) + struct.pack('<I', 0)
    tiff = b'II' + struct.pack('<HI', 42, 8) + ifd
    exif_payload = b'Exif\x00\x00' + tiff
    app1 = b'\xff\xe1' + struct.pack('>H', len(exif_payload) + 2) + exif_payload
    sof_payload = b'\x08' + struct.pack('>HH', raw_h, raw_w) + b'\x03\x01\x11\x00\x02\x11\x00\x03\x11\x00'
    sof0 = b'\xff\xc0' + struct.pack('>H', len(sof_payload) + 2) + sof_payload
    return b'\xff\xd8' + app1 + sof0 + b'\xff\xd9'


VALID_POST = """# Metadata

- **Pillar**: indie-build
- **Carrier**: carousel
- **Publish channel**: creator.xiaohongshu.com (14-day schedule)
- **AIGC disclosure**: Not required — real UI screenshots and HTML/CSS cards
- **Shutiao eligible**: No — names an indie tool
- **Suggested schedule**: Tue 19:40 Asia/Shanghai
- **Conversion path**: Searchable name `Port Tools` on screen

## Title

Mac端口占用一键清理小工具

## Title options

- 写了个Mac查端口的小工具 (13 chars)
- 本地开发查端口不用再敲命令了 (14/20)

## Body

每次重启本地服务遇到端口被占都要翻半天命令。周末用 Swift + Next.js 思路在 VS Code 里迭代到了 v1.2.0，配置文件和 SKILL.md 都留在本地。

1.AI 辅助排查配置冲突
2.状态栏直接看占用进程

界面叫 Port Tools，纯本地运行不联网。欢迎在评论区聊聊你平时怎么管理本地端口。

#独立开发 #Mac效率工具 #编程日常 #开发者工具
"""


class CheckXiaohongshuTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pkg = Path(self.tmp.name) / 'xiaohongshu'
        self.pkg.mkdir(parents=True)
        (self.pkg / 'assets').mkdir()
        (self.pkg / 'CHECKLIST.md').write_text('- [x] Verified manual upload only\n', encoding='utf-8')
        (self.pkg / 'assets/01-cover.png').write_bytes(make_png(1242, 1660))
        self.addCleanup(self.tmp.cleanup)

    def write_post(self, content: str):
        (self.pkg / 'POST.md').write_text(content, encoding='utf-8')

    def test_valid_indie_build_package_passes_without_false_positives(self):
        self.write_post(VALID_POST)
        res = MOD.check_package(self.pkg)
        self.assertTrue(res['ok'], res)
        self.assertEqual(res['errors'], [])
        self.assertEqual(res['warnings'], [])
        self.assertEqual(res['metrics']['title_utf16_len'], 14)
        self.assertEqual(res['metrics']['hashtag_count'], 4)

    def test_missing_or_empty_files_fail_cleanly(self):
        missing = MOD.check_package(self.pkg / 'nonexistent')
        self.assertFalse(missing['ok'])
        (self.pkg / 'POST.md').write_text('   \n', encoding='utf-8')
        empty = MOD.check_package(self.pkg)
        self.assertFalse(empty['ok'])
        self.assertIn('Missing or empty POST.md', empty['errors'])

    def test_title_utf16_boundary_counts_surrogate_emoji_like_js(self):
        # 20 CJK chars -> 20 UTF-16 units (exact boundary pass)
        exact_20 = '一二三四五六七八九十一二三四五六七八九十'
        self.write_post(VALID_POST.replace('Mac端口占用一键清理小工具', exact_20))
        res_ok = MOD.check_package(self.pkg)
        self.assertTrue(res_ok['ok'], res_ok)
        self.assertEqual(res_ok['metrics']['title_utf16_len'], 20)

        # 19 CJK chars + '🚀' (2 UTF-16 units) -> Python len == 20, but JS UTF-16 length == 21 -> MUST FAIL
        emoji_21 = '一二三四五六七八九十一二三四五六七八九🚀'
        self.assertEqual(len(emoji_21), 20)
        self.assertEqual(MOD.utf16_len(emoji_21), 21)
        self.write_post(VALID_POST.replace('Mac端口占用一键清理小工具', emoji_21))
        res_fail = MOD.check_package(self.pkg)
        self.assertFalse(res_fail['ok'])
        self.assertTrue(any('21/20' in e for e in res_fail['errors']))

    def test_body_1000_char_boundary_and_code_fence_headings(self):
        body_1000 = '测' * 1000
        fenced_post = VALID_POST.split('## Body')[0] + f'## Body\n\n```text\n{body_1000}\n```\n'
        self.write_post(fenced_post)
        self.assertTrue(MOD.check_package(self.pkg)['ok'])

        body_1001 = '测' * 1001
        self.write_post(VALID_POST.split('## Body')[0] + f'## Body\n\n{body_1001}\n')
        res = MOD.check_package(self.pkg)
        self.assertFalse(res['ok'])
        self.assertTrue(any('1001/1000' in e for e in res['errors']))

        # Heading inside a code fence does not split ## Body prematurely
        fenced_heading = '先看配置结构：\n## 内部示例标题\n#AI科普'
        self.write_post(VALID_POST.split('## Body')[0] + f'## Body\n\n```markdown\n{fenced_heading}\n```\n')
        res_fenced = MOD.check_package(self.pkg)
        self.assertTrue(res_fenced['ok'], res_fenced)

    def test_diversion_urls_domains_cli_and_contact_hooks_are_caught(self):
        bad_snippets = [
            '开源地址 https://github.com/example/demo',
            '直接去 github.com/example 看源码',
            '打开 claude.ai 或者 demo.app 试试',
            '终端跑一行 brew install porttools 就能装好',
            '也可以 npx create-demo-app 一键初始化',
            '想要的评论区扣1',
            '加V领安装包，或者绿泡泡找我',
        ]
        for snippet in bad_snippets:
            with self.subTest(snippet=snippet):
                self.write_post(VALID_POST + '\n' + snippet + '\n')
                res = MOD.check_package(self.pkg)
                self.assertFalse(res['ok'], f'Expected failure for {snippet!r}')

    def test_xhs_anti_scraping_combination_is_caught_across_copy_and_ocr(self):
        # Mentioning 小红书 for normal design discussion is fine
        benign = VALID_POST + '\n最近研究小红书双列封面留白很有意思。\n'
        self.write_post(benign)
        self.assertTrue(MOD.check_package(self.pkg)['ok'])

        # Pairing 小红书 in body with 无水印下载 in slide OCR triggers anti-scraping error
        fake_vision = lambda paths: [{'path': str(paths[0]), 'barcodes': [], 'text': '支持一键无水印下载保存'}]
        res = MOD.check_package(self.pkg, ocr=True, vision_runner=fake_vision)
        self.assertFalse(res['ok'])
        self.assertTrue(any('Anti-scraping' in e for e in res['errors']), res['errors'])

    def test_ocr_catches_slide_qr_code_and_slide_url(self):
        self.write_post(VALID_POST)
        fake_vision = lambda paths: [{
            'path': str(paths[0]),
            'barcodes': ['VNBarcodeSymbologyQR:https://example.com'],
            'text': 'brew install hidden-tool',
        }]
        res = MOD.check_package(self.pkg, ocr=True, vision_runner=fake_vision)
        self.assertFalse(res['ok'])
        self.assertTrue(any('QR/barcode' in e for e in res['errors']))
        self.assertTrue(any('CLI install' in e for e in res['errors']))

    def test_exif_rotated_portrait_jpeg_and_live_photo_channel_gate(self):
        # Raw sensor 4032x3024 rotated 90 CW (Orientation=6) -> 3024x4032 (3:4 vertical)
        (self.pkg / 'assets/01-cover.png').unlink()
        (self.pkg / 'assets/IMG_0001.JPG').write_bytes(make_jpeg_with_exif_orientation(4032, 3024, 6))

        live_web = (
            VALID_POST
            .replace('Pillar**: indie-build', 'Pillar**: personal-life')
            .replace('Carrier**: carousel', 'Carrier**: live-photo')
        )
        self.write_post(live_web)
        res_bad_channel = MOD.check_package(self.pkg)
        self.assertFalse(res_bad_channel['ok'])
        self.assertTrue(any('flattens Live Photos' in e for e in res_bad_channel['errors']))

        live_mobile = live_web.replace('creator.xiaohongshu.com (14-day schedule)', 'Mobile app (iPhone Live Photos)')
        self.write_post(live_mobile)
        res_ok = MOD.check_package(self.pkg)
        self.assertTrue(res_ok['ok'], res_ok)
        self.assertEqual(res_ok['warnings'], [])

    def test_carousel_slide_limits_and_landscape_warning(self):
        self.write_post(VALID_POST)
        for idx in range(2, 20):
            (self.pkg / f'assets/{idx:02d}.png').write_bytes(make_png(1242, 1660))
        res_19 = MOD.check_package(self.pkg)
        self.assertFalse(res_19['ok'])
        self.assertTrue(any('18-image limit' in e for e in res_19['errors']))

        for p in (self.pkg / 'assets').iterdir():
            p.unlink()
        # Empty assets fails normally, passes with copy_only=True
        self.assertFalse(MOD.check_package(self.pkg)['ok'])
        self.assertTrue(MOD.check_package(self.pkg, copy_only=True)['ok'])

        # 16:9 slide emits a landscape warning
        (self.pkg / 'assets/01-wide.png').write_bytes(make_png(1920, 1080))
        res_wide = MOD.check_package(self.pkg)
        self.assertTrue(res_wide['ok'])
        self.assertTrue(any('landscape' in w for w in res_wide['warnings']))

    def test_missing_aigc_disclosure_and_ai_slop_warnings(self):
        self.write_post(VALID_POST.replace('Not required — real UI screenshots and HTML/CSS cards', 'TBD'))
        res = MOD.check_package(self.pkg)
        self.assertFalse(res['ok'])
        self.assertTrue(any('AIGC disclosure' in e for e in res['errors']))

        slop = VALID_POST + '\n在当今时代，这套底层逻辑不仅提升了效率，更是实现了闭环。\n🔥 第一点\n🚀 第二点\n💡 第三点\n✨ 第四点\n'
        self.write_post(slop)
        res_slop = MOD.check_package(self.pkg)
        self.assertTrue(res_slop['ok'])
        self.assertGreaterEqual(len(res_slop['warnings']), 3)

    def test_cli_ocr_fails_closed_when_swift_unavailable(self):
        self.write_post(VALID_POST)
        with patch.object(MOD.shutil, 'which', return_value=None):
            code = MOD.main([str(self.pkg), '--ocr', '--json'])
        self.assertEqual(code, 2)


if __name__ == '__main__':
    unittest.main()
