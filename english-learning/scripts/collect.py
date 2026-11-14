#!/usr/bin/env python3
"""Collect dated, human-authored local agent messages into a private review file."""
import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
HOME_DIR = Path.home()
BATCH_CHARS = 6000
SECRET_PATTERNS = [
    (r'-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----', '[private key removed]'),
    (r'\b(?:sk[-_]|oc_sk_|gh[pousr]_|github_pat_|xox[baprs]-)[A-Za-z0-9_-]{12,}', '[credential removed]'),
    (r'(?i)\bBearer\s+[A-Za-z0-9._-]{16,}', 'Bearer [credential removed]'),
    (r'\beyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}', '[credential removed]'),
    (r'''(?i)(\b(?:api[_-]?key|password|passwd|access[_-]?token|refresh[_-]?token|client[_-]?secret|authorization)\b["']?\s*[=:]\s*["']?)[^\s"'`,;\}\]]+''', r'\1[credential removed]'),
    (r'https?://[^\s<>]+', '[link removed]'),
    (r'\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b', '[email removed]'),
]

def clean(text):
    # Desktop attachment wrappers contain rendered application content rather
    # than something the user wrote; retain the actual request after them.
    if text.lstrip().startswith(('# Applications mentioned by the user:', '# Files mentioned by the user:')) and '## My request:' in text:
        text = text.split('## My request:', 1)[1]
    if text.lstrip().startswith('# Response annotations:'):
        match = re.search(r'<response-annotations>\s*([\s\S]*?)\s*</response-annotations>', text)
        if match:
            try:
                annotations = json.loads(match.group(1))
                comments = [a['annotation'] for a in annotations if isinstance(a, dict) and isinstance(a.get('annotation'), str)]
                request = text.split('## My request:', 1)[1] if '## My request:' in text else ''
                text = '\n'.join(comments + [request])
            except (ValueError, TypeError):
                pass  # Leave ambiguous content for the reviewer to interpret.
    text = re.sub(r'<appshot\b[^>]*>[\s\S]*?</appshot>', '[application context omitted]', text)
    text = re.sub(r'<image\b[^>]*>[\s\S]*?</image>', '[image omitted]', text)
    for pattern, replacement in SECRET_PATTERNS:
        text = re.sub(pattern, replacement, text)
    return text

def timestamp(value):
    if isinstance(value, (int, float)):
        return float(value / 1000 if value > 100000000000 else value)
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if dt.tzinfo is not None:
                return dt.timestamp()
        except ValueError:
            pass
    return None

def blocks(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return '\n'.join(x.get('text', '') for x in value if isinstance(x, dict) and x.get('type') in ('text', 'input_text'))
    return ''

def source_noise(text):
    return text.lstrip().startswith(('# AGENTS.md instructions for ', '<environment_context>', '<external_codex_apps_', '<send_user_message_question_reply>', '<permissions instructions>', '<skill_instructions>', '<user_instructions>'))

def files_since(root, patterns, start):
    if not root.is_dir():
        return []
    result = []
    for pattern in patterns:
        for path in root.rglob(pattern):
            if path.is_file() and path.stat().st_mtime >= start:
                result.append(path)
    return sorted(set(result))

def jsonl(path):
    if path.suffix in ('.zst', '.zstd'):
        proc = subprocess.run(['zstd', '-dc', str(path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode:
            raise ValueError('incomplete compressed transcript')
        data = proc.stdout
    else:
        # Read only the size present at open; a running session may append concurrently.
        with path.open('rb') as f:
            data = f.read(os.fstat(f.fileno()).st_size)
    incomplete = bool(data and not data.endswith(b'\n'))
    if incomplete:
        data = data.rsplit(b'\n', 1)[0] + b'\n' if b'\n' in data else b''
    return [json.loads(line) for line in data.splitlines() if line.strip()], incomplete

class Review:
    def __init__(self, home, start, end):
        self.home, self.start, self.end = home, start, end
        self.messages, self.coverage, self.seen = [], {}, set()
    def status(self, label, present=True):
        item = {'status': 'available' if present else 'no local history found', 'files_scanned': 0, 'messages': 0, 'issues': []}
        self.coverage[label] = item
        return item
    def add(self, label, raw_time, text, identity=None):
        stamp = timestamp(raw_time)
        item = self.coverage[label]
        if stamp is None:
            item['issues'].append('user message without a reliable timestamp')
            return
        if not self.start <= stamp < self.end or not isinstance(text, str) or not text.strip() or source_noise(text):
            return
        # A fork may repeat exactly the same original message under a new session.
        signature = (label, round(stamp, 3), hashlib.sha256(text.encode()).hexdigest())
        if signature in self.seen:
            return
        self.seen.add(signature)
        text = clean(text)
        if not text.strip():
            return
        self.messages.append({'source': label, 'time': datetime.fromtimestamp(stamp, timezone.utc).isoformat(), 'text': text})
        item['messages'] += 1
    def problem(self, item, reason):
        item['issues'].append(reason)
        item['status'] = 'partial'
    def codex(self):
        roots = [self.home/'.codex/sessions', self.home/'.codex/archived_sessions']
        item = self.status('Codex', any(r.is_dir() for r in roots))
        for path in sum((files_since(r, ['*.jsonl', '*.jsonl.zst'], self.start) for r in roots), []):
            try:
                rows, incomplete = jsonl(path)
                if incomplete:
                    self.problem(item, 'a Codex transcript had an incomplete final record')
                headers = [r.get('payload', {}) for r in rows if r.get('type') == 'session_meta']
                if not headers:
                    raise ValueError('missing session metadata')
                source = headers[0].get('source')
                if isinstance(source, dict) and source.get('subagent'):
                    continue
                item['files_scanned'] += 1
                question_calls = {}
                for row in rows:
                    p = row.get('payload') or {}
                    if row.get('type') == 'response_item' and p.get('type') == 'function_call' and str(p.get('name', '')).endswith(('request_user_input', 'request_user_input_async')):
                        try:
                            question_calls[p['call_id']] = json.loads(p['arguments'])['questions']
                        except (ValueError, TypeError, KeyError):
                            pass
                canonical, legacy = [], []
                for row in rows:
                    p = row.get('payload') or {}
                    if row.get('type') == 'response_item' and p.get('type') == 'message' and p.get('role') == 'user':
                        meta = p.get('internal_chat_message_metadata_passthrough') or {}
                        kinds = meta.get('content_item_kinds')
                        content = p.get('content') or []
                        if kinds:
                            if not isinstance(content, list) or len(kinds) != len(content):
                                self.problem(item, 'unmatched Codex message provenance')
                                continue
                            content = [b for k,b in zip(kinds,content) if k == 'user.text']
                        text = blocks(content)
                        if text.startswith('<send_user_message_question_reply>'):
                            try:
                                answers = json.loads(text.strip().removeprefix('<send_user_message_question_reply>').removesuffix('</send_user_message_question_reply>').strip())
                                for answer in answers:
                                    ref = json.loads(answer['questionItemId'])
                                    question = question_calls[ref[1]][ref[2]]
                                    choices = question.get('options') or []
                                    labels = [o if isinstance(o, str) else o['label'] for o in choices]
                                    labels = [re.sub(r'\s*\(Recommended\)$', '', s).strip().casefold() for s in labels]
                                    value = answer['answer']
                                    if not isinstance(value, str):
                                        raise ValueError('unknown answer format')
                                    if value.strip().casefold() not in labels:
                                        canonical.append((row.get('timestamp'), value))
                            except (ValueError, TypeError, KeyError, IndexError):
                                self.problem(item, 'a question-form reply could not be attributed')
                        else:
                            canonical.append((row.get('timestamp'), text))
                    elif row.get('type') == 'event_msg' and p.get('type') == 'user_message':
                        legacy.append((row.get('timestamp'), p.get('message', '')))
                for stamp, text in canonical if canonical else legacy:
                    self.add('Codex', stamp, text)
            except (OSError, ValueError, json.JSONDecodeError, FileNotFoundError):
                self.problem(item, 'a Codex transcript could not be read completely')
    def pi(self):
        root = self.home/'.pi/agent/sessions'
        item = self.status('Pi', root.is_dir())
        for path in files_since(root, ['*.jsonl'], self.start):
            try:
                rows, incomplete = jsonl(path)
                if incomplete:
                    self.problem(item, 'a Pi transcript had an incomplete final record')
                if not rows or rows[0].get('type') != 'session':
                    raise ValueError('unknown session format')
                item['files_scanned'] += 1
                for row in rows:
                    msg = row.get('message') or {}
                    if row.get('type') == 'message' and msg.get('role') == 'user':
                        self.add('Pi', row.get('timestamp'), blocks(msg.get('content')))
            except (OSError, ValueError, json.JSONDecodeError):
                self.problem(item, 'a Pi transcript could not be read completely')
    def dsh(self):
        root = self.home/'.dsh/sessions'
        item = self.status('DeepSeek Harness', root.is_dir())
        for path in files_since(root, ['*.jsonl.zstd'], self.start):
            try:
                rows, incomplete = jsonl(path)
                if incomplete:
                    self.problem(item, 'a DeepSeek Harness transcript had an incomplete final record')
                if not rows or rows[0].get('type') != 'session':
                    raise ValueError('unknown session format')
                if rows[0].get('delegationDepth', 0):
                    continue
                item['files_scanned'] += 1
                for row in rows:
                    data = row.get('data') or {}
                    if row.get('type') == 'user/message' and (data.get('source') or {}).get('kind') == 'user':
                        self.add('DeepSeek Harness', row.get('time'), blocks(data.get('content')))
            except (OSError, ValueError, json.JSONDecodeError):
                self.problem(item, 'a DeepSeek Harness transcript could not be read completely')
    def opencode(self):
        path = self.home/'.local/share/opencode/opencode.db'
        item = self.status('OpenCode', path.is_file())
        if not path.is_file():
            return
        try:
            db = sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)
            try:
                rows = db.execute('SELECT m.time_created,m.data FROM session_message m JOIN session_v2 s ON s.id=m.session_id WHERE m.type=? AND s.parent_id IS NULL AND m.time_created>=? AND m.time_created<?', ('user', self.start*1000, self.end*1000)).fetchall()
                child_count = db.execute('SELECT count(*) FROM session_message m JOIN session_v2 s ON s.id=m.session_id WHERE m.type=? AND s.parent_id IS NOT NULL AND m.time_created>=? AND m.time_created<?', ('user', self.start*1000, self.end*1000)).fetchone()[0]
            finally:
                db.close()
            item['files_scanned'] = 1
            if child_count:
                self.problem(item, f'{child_count} child-session entries excluded because human authorship is unclear')
            for stamp, raw in rows:
                data = json.loads(raw)
                self.add('OpenCode', stamp, data.get('text', ''))
        except (sqlite3.Error, ValueError, OSError):
            self.problem(item, 'OpenCode history format or database could not be read')
    def zcode(self):
        path = self.home/'.zcode/cli/db/db.sqlite'
        item = self.status('ZCode', path.is_file())
        if not path.is_file():
            return
        try:
            db = sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)
            try:
                rows = db.execute('SELECT m.id,m.time_created,m.data,p.data FROM message m JOIN session s ON s.id=m.session_id JOIN part p ON p.message_id=m.id WHERE s.parent_id IS NULL AND m.time_created>=? AND m.time_created<? ORDER BY m.time_created,p.sequence', (self.start*1000, self.end*1000)).fetchall()
            finally:
                db.close()
            item['files_scanned'] = 1
            grouped = {}
            for ident, stamp, raw_m, raw_p in rows:
                msg, part = json.loads(raw_m), json.loads(raw_p)
                sem = msg.get('semantics') or {}
                if msg.get('role') != 'user' or msg.get('synthetic') or sem.get('origin') not in (None, 'real_user') or part.get('synthetic') or part.get('type') != 'text':
                    continue
                entry = grouped.setdefault(ident, [stamp, []])
                entry[1].append(part.get('text', ''))
            for stamp, texts in grouped.values():
                self.add('ZCode', stamp, '\n'.join(texts))
        except (sqlite3.Error, ValueError, OSError):
            self.problem(item, 'ZCode history format or database could not be read')
    def claude(self):
        root = self.home/'.claude/projects'
        item = self.status('Claude Code', root.is_dir())
        for path in files_since(root, ['*.jsonl'], self.start):
            try:
                rows, incomplete = jsonl(path)
                if incomplete:
                    self.problem(item, 'a Claude Code transcript had an incomplete final record')
                item['files_scanned'] += 1
                for row in rows:
                    msg = row.get('message') or {}
                    if row.get('type') == 'user' and msg.get('role') == 'user' and not row.get('isSidechain') and not row.get('isMeta'):
                        self.add('Claude Code', row.get('timestamp'), blocks(msg.get('content')))
            except (OSError, ValueError, json.JSONDecodeError):
                self.problem(item, 'a Claude Code transcript could not be read completely')
    def gemini(self):
        root = self.home/'.gemini/tmp'
        histories = files_since(root, ['session-*.json'], self.start)
        item = self.status('Gemini CLI', bool(histories))
        for path in histories:
            try:
                data = json.loads(path.read_text())
                if not isinstance(data.get('messages'), list):
                    raise ValueError('unknown Gemini chat format')
                item['files_scanned'] += 1
                for m in data['messages']:
                    if m.get('type') == 'user':
                        content = m.get('content')
                        if isinstance(content, list):
                            content = '\n'.join(p.get('text', '') for p in content if isinstance(p, dict))
                        self.add('Gemini CLI', m.get('timestamp'), content)
            except (OSError, ValueError, json.JSONDecodeError, AttributeError):
                self.problem(item, 'a Gemini CLI transcript could not be read completely')
    def antigravity(self):
        root = self.home/'.gemini/antigravity'
        item = self.status('Antigravity', (root/'conversations').is_dir())
        if not (root/'conversations').is_dir():
            return
        py = self.home/'.local/share/hindsight/venv/bin/python'
        if not py.is_file():
            self.problem(item, 'the verified local Antigravity decoder is unavailable')
            return
        try:
            proc = subprocess.run([str(py), '-B', str(HERE/'antigravity.py'), str(self.home), str(self.start), str(self.end)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120)
            if proc.returncode:
                raise ValueError('decoder failure')
            result = json.loads(proc.stdout)
            item['files_scanned'] = result['files_scanned']
            if result['errors'] or result['missing_time'] or result['unknown_fields']:
                self.problem(item, 'some Antigravity messages could not be verified or dated')
            for m in result['messages']:
                self.add('Antigravity', m['time'], m['text'])
        except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
            self.problem(item, 'the verified local Antigravity decoder could not read the history')
    def unknown_harnesses(self):
        # Only flag stores, not skills-only folders or auth/configuration files.
        for name, paths in {
            'GitHub Copilot CLI': ['.copilot/session-state'],
            'Grok CLI': ['.grok/sessions'],
            'Kiro': ['.kiro/sessions'],
            'Continue': ['.continue/sessions'],
            'Aider Desk': ['.aider-desk/sessions'],
            'Cursor': ['.cursor/sessions'],
        }.items():
            if any((self.home/p).exists() for p in paths):
                item = self.status(name)
                self.problem(item, 'local history detected but no reader is configured')

def batches(messages):
    result, current, used = [], [], 0
    for index, msg in enumerate(messages, 1):
        content = msg['text']
        pieces = [content[i:i+BATCH_CHARS] for i in range(0, len(content), BATCH_CHARS)] or ['']
        for number, piece in enumerate(pieces, 1):
            if current and (used + len(piece) > BATCH_CHARS or len(current) >= 30):
                result.append(current)
                current, used = [], 0
            current.append({'message': index, 'part': f'{number}/{len(pieces)}', 'source': msg['source'], 'time': msg['time'], 'text': piece})
            used += len(piece)
    if current:
        result.append(current)
    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--date')
    parser.add_argument('--timezone')
    parser.add_argument('--output')
    parser.add_argument('--show')
    parser.add_argument('--batch', type=int)
    args = parser.parse_args()
    if args.show:
        if args.batch is None or args.batch < 1:
            parser.error('--show requires a positive --batch')
        data = json.loads(Path(args.show).read_text())
        pieces = batches(data['messages'])
        if args.batch > len(pieces):
            parser.error('batch is out of range')
        print(json.dumps(pieces[args.batch-1], ensure_ascii=False, indent=2))
        return
    if not args.date or not args.timezone or not args.output:
        parser.error('collection requires --date, --timezone, and --output')
    zone = ZoneInfo(args.timezone)
    day = date.fromisoformat(args.date)
    start = datetime.combine(day, time.min, zone).timestamp()
    now = datetime.now(timezone.utc).timestamp()
    if start > now:
        parser.error('the requested day has not started yet')
    end = min(datetime.combine(day + timedelta(days=1), time.min, zone).timestamp(), now)
    review = Review(HOME_DIR, start, end)
    for adapter in (review.codex, review.pi, review.opencode, review.dsh, review.zcode, review.antigravity, review.claude, review.gemini, review.unknown_harnesses):
        adapter()
    review.messages.sort(key=lambda m: (m['time'], m['source']))
    for item in review.coverage.values():
        item['issues'] = dict(Counter(item['issues']))
        if item['issues'] and item['status'] == 'available':
            item['status'] = 'partial'
    result = {'date': args.date, 'timezone': args.timezone, 'window_start': datetime.fromtimestamp(start, zone).isoformat(), 'window_end': datetime.fromtimestamp(end, zone).isoformat(), 'selection': 'transcript files modified on or after the start of the requested day', 'coverage': review.coverage, 'messages': review.messages}
    fd = os.open(args.output, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as out:
        json.dump(result, out, ensure_ascii=False)
    print(json.dumps({k:v for k,v in result.items() if k != 'messages'} | {'message_count': len(review.messages), 'batches': len(batches(review.messages))}, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
