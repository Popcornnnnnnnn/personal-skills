#!/usr/bin/env python3
"""Offline preflight linter for local RedNote (Xiaohongshu) packages."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys

VALID_PILLARS = {'indie-build', 'tech-explainer', 'personal-life'}
VALID_CARRIERS = {'carousel', 'video', 'live-photo'}
IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.webp', '.heic'}
VIDEO_EXTS = {'.mp4', '.mov'}

SECTION_ALIASES = {
    '标题': 'title',
    '备选标题': 'title options',
    '正文': 'body',
    '配图': 'assets',
    '素材': 'assets',
}

URL_TAIL = r'[A-Za-z0-9._~:/?#\[\]@!$&\'()*+,;=%-]'
URL_SCHEME_RE = re.compile(rf'(?i)(?<![A-Za-z0-9_.-])(?:https?://|www\.){URL_TAIL}+')
EMAIL_RE = re.compile(
    r'(?i)(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z]{2,})+(?![A-Za-z0-9_-])'
)
DOMAIN_RE = re.compile(
    r'(?i)(?<![A-Za-z0-9_.:/@-])'
    r'(?:'
    r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*'
    r'(?:[a-z0-9-]*[a-z][a-z0-9-]*\.'
    r'(?:com|cn|net|org|io|dev|app|ai|co|me|cc|xyz|top|link|site|online|store|tech|gg|tv|ly|be|land)'
    r'|(?:brew|bun|astral|cursor)\.sh'
    r'|(?:notion|ray)\.so)'
    r'|(?:[a-z0-9-]+\.)*\d{2,}\.(?:com|cn)'
    r')'
    r'(?![A-Za-z0-9_-])'
    rf'(?:/{URL_TAIL}*)?'
)
CLI_INSTALL_RE = re.compile(
    r'(?i)(?<![A-Za-z0-9_-])(?:'
    r'(?:brew|pip3?|pipx|npm|pnpm|yarn|bun|cargo|gem|go|mas|winget|scoop|apt(?:-get)?)\s+install(?![A-Za-z0-9_-])'
    r'|(?:pnpm|yarn|bun|cargo|uv)\s+add(?![A-Za-z0-9_-])'
    r'|(?:npm|pnpm|bun)\s+i(?![A-Za-z0-9_-])'
    r'|uv\s+(?:tool\s+install|pip\s+install)(?![A-Za-z0-9_-])'
    r'|npx\s+[a-z0-9@/_-]+'
    r'|git\s+clone(?![A-Za-z0-9_-])'
    r'|(?:curl|wget)\s+[^\n|]*\|\s*(?:ba|z)?sh(?![A-Za-z0-9_-])'
    r')'
)
DIVERSION_RE = re.compile(
    r'(?:绿泡泡|地球号|绿色软件|微信号|加微|私微|同名公众号'
    r'|(?:加|私|留|扣|滴滴)\s*(?:[vV][xX]?|[wW][xX]|威|微|薇)(?![A-Za-z])'
    r'|(?<![A-Za-z])[vV][xX]\s*[:：]'
    r'|私信(?:我|领|发|拿|获取)'
    r'|评论区(?:扣|刷)\s*[0-9A-Za-z一二三]+'
    r'|评论区(?:留|留言|回复)\s*[0-9A-Za-z一二三]*\s*(?:领|发你|发链接|拿|送)'
    r'|扫码(?:领|进群|加|下载|获取))'
)
XHS_NAME_RE = re.compile(r'(?i)(?:小红书|红薯|(?<![A-Za-z0-9_-])xhs(?![A-Za-z0-9_-]))')
XHS_SENSITIVE_RE = re.compile(r'(?:无水印|去水印|爬虫|抓包|逆向|自动发帖|批量起号|绕过审核|去除AI标识|去AI标识)')
AI_SLOP_PHRASES = (
    '在当今时代', '在这个信息爆炸', '众所周知', '不言而喻',
    '底层逻辑', '赋能', '抓手', '组合拳', '闭环', '颠覆性', '里程碑式',
)
AI_CONTRAST_RE = re.compile(
    r'(?i)(?:不仅[^，。！？!?\n]{1,24}[，,]?\s*更是'
    r'|不是[^，。！？!?\n]{1,24}[，,]?\s*而是'
    r'|(?<![A-Za-z])not\s+(?:just|only|merely)\b[^.!?\n]{1,40}\bbut\b'
    r'|(?<![A-Za-z])it[\'’]s\s+not\s+[^,.;!?\n]{1,30}[,;]\s*it[\'’]s\b)'
)
MARKDOWN_SYNTAX_RE = re.compile(r'(\*\*[^*\n]+\*\*|\[[^\]\n]+\]\([^)\n]+\))')
EMOJI_LINE_RE = re.compile(r'^\s*[\U0001f300-\U0001faff\u2600-\u27bf]')
HASHTAG_RE = re.compile(r'(?<![A-Za-z0-9_&])#([^\s#\[，。！？；：、（）()]+)(?:\[话题\]#?|#)?')
OPTION_COUNTER_RE = re.compile(r'\s*(?:\(\d+(?:/\d+)?(?:\s*(?:chars?|字))?\)|（\d+(?:/\d+)?字?）)\s*$')

SWIFT_VISION_SCRIPT = r"""
import Foundation
import Vision
import ImageIO

var output: [[String: Any]] = []
for path in CommandLine.arguments.dropFirst() {
    let url = URL(fileURLWithPath: path)
    guard let src = CGImageSourceCreateWithURL(url as CFURL, nil),
          let cgImage = CGImageSourceCreateImageAtIndex(src, 0, nil) else {
        output.append(["path": path, "error": "unreadable image"])
        continue
    }
    let props = CGImageSourceCopyPropertiesAtIndex(src, 0, nil) as? [CFString: Any]
    let rawOrient = (props?[kCGImagePropertyOrientation] as? NSNumber)?.uint32Value ?? 1
    let orient = CGImagePropertyOrientation(rawValue: rawOrient) ?? .up

    var barcodes: [String] = []
    let barcodeReq = VNDetectBarcodesRequest { req, _ in
        for obs in (req.results as? [VNBarcodeObservation]) ?? [] {
            barcodes.append("\(obs.symbology.rawValue):\(obs.payloadStringValue ?? "")")
        }
    }
    var lines: [String] = []
    let textReq = VNRecognizeTextRequest { req, _ in
        for obs in (req.results as? [VNRecognizedTextObservation]) ?? [] {
            if let top = obs.topCandidates(1).first {
                lines.append(top.string)
            }
        }
    }
    textReq.recognitionLevel = .accurate
    textReq.recognitionLanguages = ["zh-Hans", "en-US"]
    textReq.usesLanguageCorrection = true
    let handler = VNImageRequestHandler(cgImage: cgImage, orientation: orient, options: [:])
    do {
        try handler.perform([barcodeReq, textReq])
        output.append(["path": path, "barcodes": barcodes, "text": lines.joined(separator: "\n")])
    } catch {
        output.append(["path": path, "error": error.localizedDescription])
    }
}
let data = try JSONSerialization.data(withJSONObject: output)
FileHandle.standardOutput.write(data)
"""


def utf16_len(text: str) -> int:
    return len(text.encode('utf-16-le')) // 2


def strip_single_fence(text: str) -> str:
    stripped = text.strip()
    match = re.match(r'^```[A-Za-z0-9_-]*\n(.*)\n```\s*$', stripped, re.S)
    if match and '\n```' not in match.group(1):
        return match.group(1).strip()
    return stripped


def parse_post_md(raw: str) -> dict:
    text = raw.replace('\r\n', '\n')
    sections: dict[str, list[str]] = {'_meta': []}
    current = '_meta'
    in_fence = False
    for line in text.split('\n'):
        if line.lstrip().startswith('```'):
            in_fence = not in_fence
        heading = None if in_fence else re.match(r'^#{1,2}\s+(.+?)\s*$', line)
        if heading:
            sec = heading.group(1).strip().lower()
            current = SECTION_ALIASES.get(sec, sec)
            sections.setdefault(current, [])
        else:
            sections[current].append(line)

    meta: dict[str, str] = {}
    meta_lines = sections.get('_meta', []) + sections.get('metadata', [])
    for line in meta_lines:
        m = re.match(
            r'^\s*(?:[-*]\s*)?(?:\*\*)?([A-Za-z][A-Za-z0-9 /_-]*?)(?:\*\*)?\s*[:：]\s*(?:\*\*\s*)?(.+?)\s*$',
            line,
        )
        if m:
            meta[m.group(1).strip().lower()] = m.group(2).strip()

    title = strip_single_fence('\n'.join(sections.get('title', []))) or meta.get('title', '')
    body = strip_single_fence('\n'.join(sections.get('body', []))) or meta.get('body', '')

    options: list[str] = []
    for line in sections.get('title options', []):
        item = re.sub(r'^\s*(?:[-*]|\d+\.)\s*', '', line).strip()
        item = item.strip('`').strip()
        item = OPTION_COUNTER_RE.sub('', item).strip()
        if item and item.lower() not in {'none', 'n/a', '无'}:
            options.append(item)

    return {'meta': meta, 'title': title, 'title_options': options, 'body': body}


def _exif_orientation(app1: bytes) -> int:
    if not app1.startswith(b'Exif\x00\x00') or len(app1) < 14:
        return 1
    tiff = app1[6:]
    endian = '<' if tiff[:2] == b'II' else ('>' if tiff[:2] == b'MM' else '')
    if not endian:
        return 1
    magic, ifd_offset = struct.unpack(endian + 'HI', tiff[2:8])
    if magic != 42 or ifd_offset + 2 > len(tiff):
        return 1
    count = struct.unpack(endian + 'H', tiff[ifd_offset:ifd_offset + 2])[0]
    pos = ifd_offset + 2
    for _ in range(count):
        if pos + 12 > len(tiff):
            break
        tag, field_type, _, _ = struct.unpack(endian + 'HHII', tiff[pos:pos + 12])
        if tag == 0x0112 and field_type == 3:
            raw_val = tiff[pos + 8:pos + 10]
            return struct.unpack(endian + 'H', raw_val)[0]
        pos += 12
    return 1


def _iter_isobmff_boxes(buf: bytes, start: int = 0, end: int | None = None):
    end = len(buf) if end is None else min(end, len(buf))
    pos = start
    while pos + 8 <= end:
        size, btype = struct.unpack('>I4s', buf[pos:pos + 8])
        hdr = 8
        if size == 1:
            if pos + 16 > end:
                break
            size = struct.unpack('>Q', buf[pos + 8:pos + 16])[0]
            hdr = 16
        elif size == 0:
            size = end - pos
        if size < hdr or pos + size > end:
            break
        yield btype, pos + hdr, pos + size
        pos += size


def _read_heic_size(data: bytes) -> tuple[int, int] | None:
    if len(data) < 16 or data[4:8] != b'ftyp':
        return None
    for btype, body_start, body_end in _iter_isobmff_boxes(data):
        if btype != b'meta' or body_start + 4 > body_end:
            continue
        pitm_id: int | None = None
        props: list[tuple[bytes, bytes]] = []
        assoc: dict[int, list[int]] = {}
        for mtype, ms, me in _iter_isobmff_boxes(data, body_start + 4, body_end):
            if mtype == b'pitm' and ms + 6 <= me:
                ver = data[ms]
                if ver == 0:
                    pitm_id = struct.unpack('>H', data[ms + 4:ms + 6])[0]
                elif ms + 8 <= me:
                    pitm_id = struct.unpack('>I', data[ms + 4:ms + 8])[0]
            elif mtype == b'iprp':
                for ptype, ps, pe in _iter_isobmff_boxes(data, ms, me):
                    if ptype == b'ipco':
                        for ctype, cs, ce in _iter_isobmff_boxes(data, ps, pe):
                            props.append((ctype, data[cs:ce]))
                    elif ptype == b'ipma' and ps + 8 <= pe:
                        ver = data[ps]
                        flags = int.from_bytes(data[ps + 1:ps + 4], 'big')
                        entry_count = struct.unpack('>I', data[ps + 4:ps + 8])[0]
                        cur = ps + 8
                        for _ in range(entry_count):
                            if ver < 1:
                                if cur + 3 > pe:
                                    break
                                item_id = struct.unpack('>H', data[cur:cur + 2])[0]
                                cur += 2
                            else:
                                if cur + 5 > pe:
                                    break
                                item_id = struct.unpack('>I', data[cur:cur + 4])[0]
                                cur += 4
                            acount = data[cur]
                            cur += 1
                            idxs = assoc.setdefault(item_id, [])
                            for _ in range(acount):
                                if flags & 1:
                                    if cur + 2 > pe:
                                        break
                                    idx = struct.unpack('>H', data[cur:cur + 2])[0] & 0x7FFF
                                    cur += 2
                                else:
                                    if cur + 1 > pe:
                                        break
                                    idx = data[cur] & 0x7F
                                    cur += 1
                                idxs.append(idx)
        target_props = (
            [props[i - 1] for i in assoc[pitm_id] if 1 <= i <= len(props)]
            if pitm_id is not None and pitm_id in assoc
            else props
        )
        dims: tuple[int, int] | None = None
        rot = 0
        for ctype, payload in target_props:
            if ctype == b'ispe' and len(payload) >= 12:
                w, h = struct.unpack('>II', payload[4:12])
                if w > 0 and h > 0:
                    dims = (w, h)
            elif ctype == b'irot' and len(payload) >= 1:
                rot = payload[0] & 0x03
        if dims:
            return (dims[1], dims[0]) if rot in (1, 3) else dims
    return None


def read_image_size(path: Path) -> tuple[int, int] | None:
    data = path.read_bytes()
    dims: tuple[int, int] | None = None
    if len(data) >= 24 and data[:8] == b'\x89PNG\r\n\x1a\n' and data[12:16] == b'IHDR':
        dims = struct.unpack('>II', data[16:24])
    elif len(data) >= 4 and data[:2] == b'\xff\xd8':
        orientation = 1
        idx = 2
        while idx + 4 <= len(data):
            if data[idx] != 0xFF:
                break
            while idx < len(data) and data[idx] == 0xFF:
                idx += 1
            if idx >= len(data):
                break
            marker = data[idx]
            idx += 1
            if marker in (0xD8, 0xD9, 0x01) or 0xD0 <= marker <= 0xD7:
                continue
            if idx + 2 > len(data):
                break
            seg_len = struct.unpack('>H', data[idx:idx + 2])[0]
            if seg_len < 2 or idx + seg_len > len(data):
                break
            seg = data[idx + 2:idx + seg_len]
            if marker == 0xE1 and seg.startswith(b'Exif\x00\x00'):
                orientation = _exif_orientation(seg)
            elif marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                if len(seg) >= 5:
                    h, w = struct.unpack('>HH', seg[1:5])
                    dims = (h, w) if orientation in (5, 6, 7, 8) else (w, h)
                    break
            idx += seg_len
    elif len(data) >= 30 and data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        chunk = data[12:16]
        if chunk == b'VP8X' and len(data) >= 30:
            w = 1 + int.from_bytes(data[24:27], 'little')
            h = 1 + int.from_bytes(data[27:30], 'little')
            dims = (w, h)
        elif chunk == b'VP8L' and len(data) >= 25 and data[20] == 0x2F:
            bits = struct.unpack('<I', data[21:25])[0]
            dims = ((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)
        elif chunk == b'VP8 ' and len(data) >= 30 and data[23:26] == b'\x9d\x01\x2a':
            w, h = struct.unpack('<HH', data[26:30])
            dims = (w & 0x3FFF, h & 0x3FFF)
    elif path.suffix.lower() == '.heic':
        dims = _read_heic_size(data)
    if dims is not None and dims[0] > 0 and dims[1] > 0:
        return dims
    return None


def read_video_size(path: Path) -> tuple[int, int] | None:
    if not shutil.which('ffprobe'):
        return None
    proc = subprocess.run(
        [
            'ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height:stream_tags=rotate:stream_side_data=rotation',
            '-of', 'json', str(path),
        ],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        return None
    try:
        streams = json.loads(proc.stdout).get('streams', [])
        if not streams or 'width' not in streams[0] or 'height' not in streams[0]:
            return None
        w = int(streams[0]['width'])
        h = int(streams[0]['height'])
        if w <= 0 or h <= 0:
            return None
        rot = 0.0
        for sd in streams[0].get('side_data_list') or []:
            if 'rotation' in sd:
                rot = float(sd['rotation'])
                break
        else:
            tag_rot = (streams[0].get('tags') or {}).get('rotate')
            if tag_rot is not None:
                rot = float(tag_rot)
        return (h, w) if abs(round(rot)) % 180 == 90 else (w, h)
    except (ValueError, TypeError, KeyError):
        return None


def scan_published_text(
    text: str, label: str, errors: list[str], warnings: list[str], *, check_slop: bool = True
) -> None:
    for m in URL_SCHEME_RE.finditer(text):
        errors.append(f'{label}: external URL detected ({m.group(0)!r})')
    for m in EMAIL_RE.finditer(text):
        errors.append(f'{label}: email address detected ({m.group(0)!r})')
    for m in DOMAIN_RE.finditer(text):
        errors.append(f'{label}: external domain token detected ({m.group(0)!r}); use plain brand/tool names on Xiaohongshu')
    for m in CLI_INSTALL_RE.finditer(text):
        errors.append(f'{label}: CLI install/download command detected ({m.group(0)!r})')
    for m in DIVERSION_RE.finditer(text):
        errors.append(f'{label}: off-platform contact/lead-gen hook detected ({m.group(0)!r})')

    if not check_slop:
        return
    for m in MARKDOWN_SYNTAX_RE.finditer(text):
        warnings.append(f'{label}: literal Markdown syntax detected ({m.group(0)!r}); Xiaohongshu renders plain text')
    for phrase in AI_SLOP_PHRASES:
        if phrase in text:
            warnings.append(f'{label}: stock AI cliché detected ({phrase!r})')
    for m in AI_CONTRAST_RE.finditer(text):
        warnings.append(f'{label}: stock contrast phrasing detected ({m.group(0)!r})')
    streak = 0
    for line in text.split('\n'):
        if line.strip():
            streak = streak + 1 if EMOJI_LINE_RE.match(line) else 0
            if streak == 4:
                warnings.append(f'{label}: 4+ consecutive emoji-prefixed bullet lines look LLM-generated')


def run_vision_ocr(image_paths: list[Path]) -> list[dict]:
    if not shutil.which('swift'):
        raise RuntimeError('macOS swift toolchain unavailable for --ocr Vision scan')
    proc = subprocess.run(
        ['swift', '-e', SWIFT_VISION_SCRIPT, *[str(p) for p in image_paths]],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f'Vision OCR failed: {proc.stderr.strip() or proc.stdout.strip()}')
    return json.loads(proc.stdout)


def _check_images(image_files: list[Path], errors: list[str], warnings: list[str], *, check_34_ratio: bool) -> None:
    for img in image_files:
        dims = read_image_size(img)
        if dims is None:
            errors.append(f'Unreadable or corrupt image asset: {img.name}')
            continue
        w, h = dims
        ratio = w / h
        if w > h:
            warnings.append(f'{img.name} is landscape ({w}x{h}); frame onto 3:4 vertical (e.g. 1242x1660) for dual-column feeds')
        elif check_34_ratio and not (0.70 <= ratio <= 0.80):
            warnings.append(f'{img.name} aspect ratio is {w}x{h} ({ratio:.2f}); 3:4 vertical (0.75) is recommended')


def check_package(pkg_dir: Path, *, copy_only: bool = False, ocr: bool = False, vision_runner=run_vision_ocr) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    metrics: dict[str, object] = {}

    if not pkg_dir.is_dir():
        return {'ok': False, 'errors': [f'Package directory not found: {pkg_dir}'], 'warnings': [], 'metrics': {}}

    post_path = pkg_dir / 'POST.md'
    checklist_path = pkg_dir / 'CHECKLIST.md'
    assets_dir = pkg_dir / 'assets'

    if not post_path.is_file() or not post_path.read_text(encoding='utf-8').strip():
        errors.append('Missing or empty POST.md')
        return {'ok': False, 'errors': errors, 'warnings': warnings, 'metrics': metrics}
    if not checklist_path.is_file() or not checklist_path.read_text(encoding='utf-8').strip():
        errors.append('Missing or empty CHECKLIST.md')

    parsed = parse_post_md(post_path.read_text(encoding='utf-8'))
    meta = parsed['meta']
    title = parsed['title']
    options = parsed['title_options']
    body = parsed['body']

    pillar_raw = meta.get('pillar', '')
    pillar = pillar_raw.split()[0].strip('`*,;()').lower() if pillar_raw else ''
    if pillar not in VALID_PILLARS:
        errors.append(f'Metadata Pillar must start with one of {sorted(VALID_PILLARS)} (got {pillar_raw!r})')

    carrier_raw = meta.get('carrier', '')
    carrier = carrier_raw.split()[0].strip('`*,;()').lower() if carrier_raw else ''
    if carrier not in VALID_CARRIERS:
        errors.append(f'Metadata Carrier must start with one of {sorted(VALID_CARRIERS)} (got {carrier_raw!r})')

    aigc_raw = meta.get('aigc disclosure', '')
    aigc_norm = aigc_raw.strip('`').lower()
    if not (aigc_norm.startswith('required') or aigc_norm.startswith('not required')):
        errors.append('Metadata AIGC disclosure must explicitly start with "Required" or "Not required"')
    else:
        basis = re.sub(r'^(?:not\s+required|required)\b', '', aigc_norm).strip(' \t:—–-,;()')
        if not basis:
            warnings.append('Metadata AIGC disclosure should briefly state the media basis')

    channel_raw = meta.get('publish channel', '')
    if not channel_raw:
        errors.append('Metadata Publish channel is required')
    elif carrier == 'live-photo':
        ch_low = channel_raw.lower()
        has_mobile = any(k in ch_low for k in ('mobile', 'iphone', 'ios', 'android', 'app', '手机'))
        if 'creator.xiaohongshu.com' in ch_low or 'web' in ch_low or not has_mobile:
            errors.append('live-photo carrier must use the mobile app; creator.xiaohongshu.com flattens Live Photos')

    shutiao_raw = meta.get('shutiao eligible', '').strip('`').lower()
    if pillar == 'indie-build' and shutiao_raw.startswith('yes'):
        warnings.append('indie-build posts with product cues are typically rejected by standard Shutiao (内容加热)')

    if not title:
        errors.append('Missing or empty Title in POST.md')
    elif '\n' in title:
        errors.append('Title must be a single line')
    else:
        t_len = utf16_len(title)
        metrics['title_utf16_len'] = t_len
        if t_len > 20:
            errors.append(f'Title exceeds 20 UTF-16 chars ({t_len}/20): {title!r}')
        elif t_len > 16:
            warnings.append(f'Title is {t_len}/20 UTF-16 chars; mobile two-column cards truncate around ~16 chars')
        scan_published_text(title, 'Title', errors, warnings)

    for idx, opt in enumerate(options, 1):
        opt_len = utf16_len(opt)
        if opt_len > 20:
            errors.append(f'Title option #{idx} exceeds 20 UTF-16 chars ({opt_len}/20): {opt!r}')
        scan_published_text(opt, f'Title option #{idx}', errors, warnings)

    if not body:
        errors.append('Missing or empty Body in POST.md')
    else:
        b_len = utf16_len(body)
        hashtags = HASHTAG_RE.findall(body)
        metrics['body_utf16_len'] = b_len
        metrics['hashtag_count'] = len(hashtags)
        if b_len > 1000:
            errors.append(f'Body exceeds 1000 UTF-16 chars ({b_len}/1000)')
        elif hashtags and b_len + len(hashtags) * 5 > 1000:
            warnings.append(
                f'Body is {b_len}/1000 UTF-16 chars with {len(hashtags)} #话题 tags; '
                'interactive topic pills in creator.xiaohongshu.com add extra characters'
            )
        if len(hashtags) == 0:
            warnings.append('Body has no #话题 tags; 3-5 focused tags at the end are recommended')
        elif len(hashtags) > 8:
            warnings.append(f'Body has {len(hashtags)} #话题 tags; 3-5 focused tags are recommended')
        scan_published_text(body, 'Body', errors, warnings)

    combined_text = '\n'.join([title, *options, body])
    image_files: list[Path] = []
    video_files: list[Path] = []

    if not copy_only:
        if not assets_dir.is_dir():
            errors.append('Missing assets/ directory (pass --copy-only when checking draft text before asset rendering)')
        else:
            all_assets = sorted(p for p in assets_dir.iterdir() if p.is_file() and not p.name.startswith('.'))
            image_files = [p for p in all_assets if p.suffix.lower() in IMAGE_EXTS]
            video_files = [p for p in all_assets if p.suffix.lower() in VIDEO_EXTS]
            other_files = [p for p in all_assets if p.suffix.lower() not in (IMAGE_EXTS | VIDEO_EXTS)]
            metrics['image_count'] = len(image_files)
            metrics['video_count'] = len(video_files)

            for stray in other_files:
                warnings.append(f'Unsupported or stray file in assets/: {stray.name}')

            has_ffprobe = bool(shutil.which('ffprobe'))
            if video_files and not has_ffprobe:
                warnings.append('ffprobe not found; skipped video dimension/integrity checks')

            if carrier == 'carousel':
                if not image_files:
                    errors.append('carousel carrier requires 1-18 slide images in assets/')
                elif len(image_files) > 18:
                    errors.append(f'carousel exceeds 18-image limit ({len(image_files)} images)')
                if video_files:
                    warnings.append('carousel package contains video file(s) in assets/')
                _check_images(image_files, errors, warnings, check_34_ratio=True)
            elif carrier == 'video':
                if not video_files:
                    errors.append('video carrier requires an .mp4 or .mov file in assets/')
                for vid in video_files:
                    if not has_ffprobe:
                        continue
                    dims = read_video_size(vid)
                    if dims is None:
                        errors.append(f'Unreadable or corrupt video asset: {vid.name}')
                    elif dims[0] > dims[1]:
                        errors.append(
                            f'{vid.name} is landscape ({dims[0]}x{dims[1]}); '
                            'RedNote videos must be vertical (default 9:16 1080x1920)'
                        )
                if not image_files:
                    warnings.append('video package has no dedicated cover image in assets/; add a 3:4-safe cover image')
                else:
                    _check_images(image_files, errors, warnings, check_34_ratio=False)
            elif carrier == 'live-photo':
                if not image_files:
                    errors.append('live-photo carrier requires 1-18 still images (.heic/.jpg/.png) in assets/')
                elif len(image_files) > 18:
                    errors.append(f'live-photo exceeds 18-photo limit ({len(image_files)} images)')
                _check_images(image_files, errors, warnings, check_34_ratio=False)
                for vid in video_files:
                    if has_ffprobe and read_video_size(vid) is None:
                        errors.append(f'Unreadable or corrupt video asset: {vid.name}')

    ocr_slides = []
    if ocr:
        if copy_only:
            warnings.append('--ocr ignored because --copy-only was set')
        elif image_files:
            results = vision_runner(image_files)
            for item in results:
                name = Path(item['path']).name
                if 'error' in item:
                    errors.append(f'Slide OCR failed on {name}: {item["error"]}')
                    continue
                for code in item.get('barcodes', []):
                    errors.append(f'Slide {name}: QR/barcode detected ({code})')
                slide_text = item.get('text', '')
                ocr_slides.append({'file': name, 'text': slide_text})
                if slide_text:
                    scan_published_text(slide_text, f'Slide OCR ({name})', errors, warnings, check_slop=False)
                    combined_text += '\n' + slide_text
        metrics['ocr_scanned_images'] = len(ocr_slides)

    if XHS_NAME_RE.search(combined_text) and XHS_SENSITIVE_RE.search(combined_text):
        errors.append(
            'Anti-scraping/policy trigger combination detected: pairing Xiaohongshu platform terms with '
            'watermark-removal, scraping, auto-posting, or audit-evasion keywords'
        )

    return {
        'ok': not errors,
        'errors': errors,
        'warnings': warnings,
        'metrics': metrics,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Validate a local RedNote (Xiaohongshu) package directory.')
    parser.add_argument('package_dir', type=Path, help='Path to xiaohongshu/ or xiaohongshu/<note-slug>/ directory')
    parser.add_argument('--copy-only', action='store_true', help='Validate POST.md and CHECKLIST.md before assets are rendered')
    parser.add_argument('--ocr', action='store_true', help='Scan slide images for QR codes and OCR diversion text via macOS Vision')
    parser.add_argument('--json', action='store_true', help='Print JSON result')
    args = parser.parse_args(argv)

    try:
        result = check_package(args.package_dir, copy_only=args.copy_only, ocr=args.ocr)
    except RuntimeError as exc:
        if args.json:
            print(json.dumps({'ok': False, 'errors': [str(exc)], 'warnings': [], 'metrics': {}}, ensure_ascii=False))
        else:
            print(f'ERROR: {exc}', file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        status = 'PASS' if result['ok'] else 'FAIL'
        print(f'{status}: {args.package_dir} {result["metrics"]}')
        for err in result['errors']:
            print(f'  ERROR: {err}')
        for warn in result['warnings']:
            print(f'  WARN: {warn}')
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
