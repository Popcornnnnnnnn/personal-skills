"""Unit tests for RedNote (Xiaohongshu) local package preflight checker."""
import importlib.util
from pathlib import Path
import shutil
import struct
import subprocess
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
    raw = b'\x00\x00\x00\x00'
    idat = zlib.compress(raw)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) + chunk(b'IDAT', idat) + chunk(b'IEND', b'')


def make_jpeg_with_exif_orientation(raw_w: int, raw_h: int, orientation: int, *, big_endian: bool = False) -> bytes:
    endian = '>' if big_endian else '<'
    bom = b'MM' if big_endian else b'II'
    val_bytes = struct.pack(endian + 'HH', orientation, 0)
    ifd = struct.pack(endian + 'H', 1) + struct.pack(endian + 'HHI', 0x0112, 3, 1) + val_bytes + struct.pack(endian + 'I', 0)
    tiff = bom + struct.pack(endian + 'HI', 42, 8) + ifd
    exif_payload = b'Exif\x00\x00' + tiff
    app1 = b'\xff\xe1' + struct.pack('>H', len(exif_payload) + 2) + exif_payload
    sof_payload = b'\x08' + struct.pack('>HH', raw_h, raw_w) + b'\x03\x01\x11\x00\x02\x11\x00\x03\x11\x00'
    sof0 = b'\xff\xc0' + struct.pack('>H', len(sof_payload) + 2) + sof_payload
    return b'\xff\xd8' + app1 + sof0 + b'\xff\xd9'


def make_heic_with_grid_and_irot(raw_w: int, raw_h: int, irot_angle: int) -> bytes:
    """Build a multi-item HEIC header (512x512 tile + primary item #2 with irot) like Apple ImageIO."""
    def box(btype: bytes, payload: bytes) -> bytes:
        return struct.pack('>I4s', len(payload) + 8, btype) + payload

    ftyp = box(b'ftyp', b'heic\x00\x00\x00\x00mif1heic')
    pitm = box(b'pitm', b'\x00\x00\x00\x00' + struct.pack('>H', 2))
    tile_ispe = box(b'ispe', b'\x00\x00\x00\x00' + struct.pack('>II', 512, 512))
    main_ispe = box(b'ispe', b'\x00\x00\x00\x00' + struct.pack('>II', raw_w, raw_h))
    irot = box(b'irot', bytes([irot_angle & 0x03]))
    ipco = box(b'ipco', tile_ispe + main_ispe + irot)
    # Item 1 -> prop 1 (tile_ispe); Primary Item 2 -> props 2 (main_ispe) and 3 (irot)
    ipma_body = (
        b'\x00\x00\x00\x00'
        + struct.pack('>I', 2)
        + struct.pack('>HB', 1, 1) + bytes([0x81])
        + struct.pack('>HB', 2, 2) + bytes([0x82, 0x83])
    )
    iprp = box(b'iprp', ipco + box(b'ipma', ipma_body))
    meta = box(b'meta', b'\x00\x00\x00\x00' + pitm + iprp)
    return ftyp + meta


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

每次重启本地服务遇到端口被占都要翻半天命令。周末用 Swift + Next.js 思路在 VS Code 里迭代到了 v1.2.0，以前写 C# 也遇到过同类问题，配置文件和 SKILL.md 都留在本地。

On the go I check logs locally without cloud sync.

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

    def test_bold_colon_metadata_and_chinese_headings_parse_cleanly(self):
        alt_post = """# Metadata

- **Pillar:** tech-explainer
- **Carrier**：carousel
- **Publish channel:** creator.xiaohongshu.com
- **AIGC disclosure:** Not required—真实终端截图与排版卡片

## 标题

一张图讲清本地代理分流规则

## 正文

把国内直连和海外分流拆成两条清晰规则后，延迟稳定了很多。

#网络排查 #AI编程 #技术科普
"""
        self.write_post(alt_post)
        res = MOD.check_package(self.pkg)
        self.assertTrue(res['ok'], res)
        self.assertEqual(res['warnings'], [])

    def test_missing_or_empty_files_fail_cleanly(self):
        missing = MOD.check_package(self.pkg / 'nonexistent')
        self.assertFalse(missing['ok'])
        (self.pkg / 'POST.md').write_text('   \n', encoding='utf-8')
        empty = MOD.check_package(self.pkg)
        self.assertFalse(empty['ok'])
        self.assertIn('Missing or empty POST.md', empty['errors'])

    def test_title_utf16_boundary_counts_surrogate_emoji_like_js(self):
        exact_20 = '一二三四五六七八九十一二三四五六七八九十'
        self.write_post(VALID_POST.replace('Mac端口占用一键清理小工具', exact_20))
        res_ok = MOD.check_package(self.pkg)
        self.assertTrue(res_ok['ok'], res_ok)
        self.assertEqual(res_ok['metrics']['title_utf16_len'], 20)

        emoji_21 = '一二三四五六七八九十一二三四五六七八九🚀'
        self.assertEqual(len(emoji_21), 20)
        self.assertEqual(MOD.utf16_len(emoji_21), 21)
        self.write_post(VALID_POST.replace('Mac端口占用一键清理小工具', emoji_21))
        res_fail = MOD.check_package(self.pkg)
        self.assertFalse(res_fail['ok'])
        self.assertTrue(any('21/20' in e for e in res_fail['errors']))

    def test_body_1000_char_boundary_hashtag_pill_headroom_and_code_fences(self):
        body_1000 = '测' * 995 + '#测试话题'
        fenced_post = VALID_POST.split('## Body')[0] + f'## Body\n\n```text\n{body_1000}\n```\n'
        self.write_post(fenced_post)
        res_near = MOD.check_package(self.pkg)
        self.assertTrue(res_near['ok'], res_near)
        self.assertEqual(res_near['metrics']['body_utf16_len'], 1000)
        self.assertTrue(any('topic pills' in w for w in res_near['warnings']), res_near['warnings'])

        body_1001 = '测' * 1001
        self.write_post(VALID_POST.split('## Body')[0] + f'## Body\n\n{body_1001}\n')
        res = MOD.check_package(self.pkg)
        self.assertFalse(res['ok'])
        self.assertTrue(any('1001/1000' in e for e in res['errors']))

        fenced_heading = '先看配置结构：\n## 内部示例标题\n#AI科普'
        self.write_post(VALID_POST.split('## Body')[0] + f'## Body\n\n```markdown\n{fenced_heading}\n```\n')
        res_fenced = MOD.check_package(self.pkg)
        self.assertTrue(res_fenced['ok'], res_fenced)

    def test_diversion_urls_cjk_adjacent_subdomains_emails_cli_and_hooks_are_caught(self):
        bad_snippets = [
            '开源地址 https://github.com/example/demo',
            '开源地址https://claude.ai试试',
            '直接去github.com看源码',
            '打开claude.ai试试',
            '文档放在 docs.github.com 和 pan.baidu.com/s/12345',
            '笔记放 notion.so/demo 了',
            '有问题发邮件到 maker@studio.org 交流',
            '终端跑一行brew install porttools就能装好',
            '一键npm install安装或者npm i试用',
            '也可以 npx create-demo-app 一键初始化',
            '想要的评论区扣1',
            '加V领安装包，或者绿泡泡找我',
        ]
        for snippet in bad_snippets:
            with self.subTest(snippet=snippet):
                self.write_post(VALID_POST + '\n' + snippet + '\n')
                res = MOD.check_package(self.pkg)
                self.assertFalse(res['ok'], f'Expected failure for {snippet!r}')

    def test_xhs_anti_scraping_combination_is_caught_across_cjk_copy_and_ocr(self):
        benign = VALID_POST + '\n最近研究小红书双列封面留白很有意思。\n'
        self.write_post(benign)
        self.assertTrue(MOD.check_package(self.pkg)['ok'])

        cjk_xhs = VALID_POST + '\n用xhs工具测试无水印保存。\n'
        self.write_post(cjk_xhs)
        res_cjk = MOD.check_package(self.pkg)
        self.assertFalse(res_cjk['ok'])
        self.assertTrue(any('Anti-scraping' in e for e in res_cjk['errors']))

        self.write_post(benign)
        fake_vision = lambda paths: [{'path': str(paths[0]), 'barcodes': [], 'text': '支持一键无水印下载保存'}]
        res = MOD.check_package(self.pkg, ocr=True, vision_runner=fake_vision)
        self.assertFalse(res['ok'])
        self.assertTrue(any('Anti-scraping' in e for e in res['errors']), res['errors'])

    def test_ocr_catches_slide_qr_code_and_cjk_adjacent_slide_cli(self):
        self.write_post(VALID_POST)
        fake_vision = lambda paths: [{
            'path': str(paths[0]),
            'barcodes': ['VNBarcodeSymbologyQR:https://example.com'],
            'text': '终端输入brew install hidden-tool',
        }]
        res = MOD.check_package(self.pkg, ocr=True, vision_runner=fake_vision)
        self.assertFalse(res['ok'])
        self.assertTrue(any('QR/barcode' in e for e in res['errors']))
        self.assertTrue(any('CLI install' in e for e in res['errors']))

    def test_exif_rotated_jpegs_and_heic_irot_on_carousel_and_live_photo(self):
        # 1. Test both little-endian (II) and big-endian (MM) EXIF Orientation=6 JPEGs on carousel
        (self.pkg / 'assets/01-cover.png').unlink()
        (self.pkg / 'assets/01-le.jpg').write_bytes(make_jpeg_with_exif_orientation(4032, 3024, 6, big_endian=False))
        (self.pkg / 'assets/02-be.jpg').write_bytes(make_jpeg_with_exif_orientation(4032, 3024, 6, big_endian=True))
        # Multi-tile HEIC: coded 4032x3024 with irot=3 (90 CW) -> displayed 3024x4032 (3:4 vertical)
        (self.pkg / 'assets/03-iphone.heic').write_bytes(make_heic_with_grid_and_irot(4032, 3024, 3))
        self.write_post(VALID_POST)
        res_carousel = MOD.check_package(self.pkg)
        self.assertTrue(res_carousel['ok'], res_carousel)
        self.assertEqual(res_carousel['warnings'], [])

        # Unrotated landscape HEIC (irot=0 -> 4032x3024) warns as landscape
        (self.pkg / 'assets/04-wide.heic').write_bytes(make_heic_with_grid_and_irot(4032, 3024, 0))
        res_wide_heic = MOD.check_package(self.pkg)
        self.assertTrue(any('04-wide.heic is landscape (4032x3024)' in w for w in res_wide_heic['warnings']))
        (self.pkg / 'assets/04-wide.heic').unlink()

        # 2. Live Photo channel gate rejects web, desktop, and 'creator.xiaohongshu.com web app'
        live_post = (
            VALID_POST
            .replace('Pillar**: indie-build', 'Pillar**: personal-life')
            .replace('Carrier**: carousel', 'Carrier**: live-photo')
        )
        for bad_ch in ('creator.xiaohongshu.com (14-day schedule)', 'creator.xiaohongshu.com web app', 'Desktop browser'):
            self.write_post(live_post.replace('creator.xiaohongshu.com (14-day schedule)', bad_ch))
            res_bad = MOD.check_package(self.pkg)
            self.assertFalse(res_bad['ok'], bad_ch)
            self.assertTrue(any('Live Photos' in e for e in res_bad['errors']))

        live_mobile = live_post.replace('creator.xiaohongshu.com (14-day schedule)', 'Mobile app (iPhone Live Photos)')
        self.write_post(live_mobile)
        res_ok = MOD.check_package(self.pkg)
        self.assertTrue(res_ok['ok'], res_ok)
        self.assertEqual(res_ok['warnings'], [])

        # Corrupt image inside live-photo must fail
        (self.pkg / 'assets/99-corrupt.jpg').write_bytes(b'\xff\xd8not-a-valid-jpeg')
        res_corrupt = MOD.check_package(self.pkg)
        self.assertFalse(res_corrupt['ok'])
        self.assertTrue(any('99-corrupt.jpg' in e for e in res_corrupt['errors']))

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'ffmpeg/ffprobe required')
    def test_video_and_live_photo_mov_dimensions_rotation_and_corrupt_rejection(self):
        video_post = (
            VALID_POST
            .replace('Pillar**: indie-build', 'Pillar**: tech-explainer')
            .replace('Carrier**: carousel', 'Carrier**: video')
        )
        self.write_post(video_post)

        # 1. Landscape 1920x1080 MP4 -> rejected
        landscape_mp4 = self.pkg / 'assets/walkthrough.mp4'
        subprocess.run(
            ['ffmpeg', '-y', '-f', 'lavfi', '-i', 'color=c=black:s=320x180:d=0.1',
             '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(landscape_mp4)],
            capture_output=True, check=True,
        )
        res_land = MOD.check_package(self.pkg)
        self.assertFalse(res_land['ok'])
        self.assertTrue(any('is landscape (320x180)' in e for e in res_land['errors']), res_land['errors'])

        # 2. Stream-rotated iPhone vertical MOV (coded 320x180 + display_rotation 90 -> 180x320 vertical) -> accepted!
        iphone_mov = self.pkg / 'assets/iphone_vertical.mov'
        subprocess.run(
            ['ffmpeg', '-y', '-display_rotation', '90', '-i', str(landscape_mp4),
             '-c', 'copy', str(iphone_mov)],
            capture_output=True, check=True,
        )
        landscape_mp4.unlink()
        self.assertEqual(MOD.read_video_size(iphone_mov), (180, 320))
        res_vert = MOD.check_package(self.pkg)
        self.assertTrue(res_vert['ok'], res_vert)
        self.assertEqual(res_vert['warnings'], [])

        # 3. Live Photo pair (.heic + .mov) -> accepted on Mobile app
        (self.pkg / 'assets/01-cover.png').unlink()
        (self.pkg / 'assets/IMG_0001.HEIC').write_bytes(make_heic_with_grid_and_irot(4032, 3024, 3))
        live_pair_post = (
            VALID_POST
            .replace('Pillar**: indie-build', 'Pillar**: personal-life')
            .replace('Carrier**: carousel', 'Carrier**: live-photo')
            .replace('creator.xiaohongshu.com (14-day schedule)', 'iPhone app')
        )
        self.write_post(live_pair_post)
        res_pair = MOD.check_package(self.pkg)
        self.assertTrue(res_pair['ok'], res_pair)

        # 4. Corrupt MP4 -> rejected
        iphone_mov.write_bytes(b'corrupt-mp4-bytes')
        res_bad_vid = MOD.check_package(self.pkg)
        self.assertFalse(res_bad_vid['ok'])
        self.assertTrue(any('Unreadable or corrupt video asset' in e for e in res_bad_vid['errors']))

    def test_carousel_slide_limits_and_landscape_warning(self):
        self.write_post(VALID_POST)
        for idx in range(2, 20):
            (self.pkg / f'assets/{idx:02d}.png').write_bytes(make_png(1242, 1660))
        res_19 = MOD.check_package(self.pkg)
        self.assertFalse(res_19['ok'])
        self.assertTrue(any('18-image limit' in e for e in res_19['errors']))

        for p in (self.pkg / 'assets').iterdir():
            p.unlink()
        self.assertFalse(MOD.check_package(self.pkg)['ok'])
        self.assertTrue(MOD.check_package(self.pkg, copy_only=True)['ok'])

        (self.pkg / 'assets/01-wide.png').write_bytes(make_png(1920, 1080))
        res_wide = MOD.check_package(self.pkg)
        self.assertTrue(res_wide['ok'])
        self.assertTrue(any('landscape' in w for w in res_wide['warnings']))

    def test_missing_aigc_disclosure_markdown_and_ai_slop_warnings(self):
        self.write_post(VALID_POST.replace('Not required — real UI screenshots and HTML/CSS cards', 'TBD'))
        res = MOD.check_package(self.pkg)
        self.assertFalse(res['ok'])
        self.assertTrue(any('AIGC disclosure' in e for e in res['errors']))

        slop = (
            VALID_POST
            + '\n在当今时代，**这套底层逻辑**不是简单的脚本，而是实现了闭环。\n'
            + '🔥 第一点\n🚀 第二点\n💡 第三点\n✨ 第四点\n'
        )
        self.write_post(slop)
        res_slop = MOD.check_package(self.pkg)
        self.assertTrue(res_slop['ok'])
        self.assertTrue(any('Markdown syntax' in w for w in res_slop['warnings']))
        self.assertTrue(any('不是' in w for w in res_slop['warnings']))
        self.assertGreaterEqual(len(res_slop['warnings']), 5)

    def test_cli_ocr_fails_closed_when_swift_unavailable(self):
        self.write_post(VALID_POST)
        with patch.object(MOD.shutil, 'which', return_value=None):
            code = MOD.main([str(self.pkg), '--ocr', '--json'])
        self.assertEqual(code, 2)


if __name__ == '__main__':
    unittest.main()
