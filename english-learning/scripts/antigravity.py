#!/usr/bin/env python3
"""Read visible human input using the existing pinned Antigravity decoder."""
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

home, start, end = Path(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3])
root = home / '.local/share/hindsight/integration'
sys.path.insert(0, str(root / 'history'))
from decode_antigravity import schema_pool
from google.protobuf import message_factory

pool, _ = schema_pool(root / 'research/antigravity-history/main.js')
step_class = message_factory.GetMessageClass(pool.FindMessageTypeByName('gemini_coder.Step'))
meta_class = message_factory.GetMessageClass(pool.FindMessageTypeByName('exa.cortex_pb.CortexStepMetadata'))
summary_db = home / '.gemini/antigravity/conversation_summaries.db'
folder = home / '.gemini/antigravity/conversations'
conn = sqlite3.connect(summary_db.as_uri() + '?mode=ro', uri=True)
parents = {r[0]: r[1] for r in conn.execute('SELECT conversation_id,nesting_depth FROM conversation_summaries')}
conn.close()
messages, errors, scanned, missing_time, unknown = [], [], 0, 0, 0
for path in folder.glob('*.db'):
    if path.stat().st_mtime < start and (not path.with_suffix('.db-wal').exists() or path.with_suffix('.db-wal').stat().st_mtime < start):
        continue
    if path.stem not in parents:
        errors.append('conversation metadata unavailable')
        continue
    if parents[path.stem]:
        continue
    try:
        db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
        try:
            rows = db.execute('SELECT idx,step_type,status,step_format,metadata,step_payload FROM steps WHERE step_type=14 ORDER BY idx').fetchall()
        finally:
            db.close()
        scanned += 1
        for idx, kind, status, fmt, metadata, payload in rows:
            if fmt != 0:
                raise ValueError('unknown step format')
            step = step_class.FromString(payload or b'')
            meta = meta_class.FromString(metadata or b'')
            before = step.ByteSize() + meta.ByteSize()
            step.DiscardUnknownFields()
            meta.DiscardUnknownFields()
            if before != step.ByteSize() + meta.ByteSize():
                unknown += 1
            if step.type != kind or step.status != status or step.metadata.SerializeToString(deterministic=True) != meta.SerializeToString(deterministic=True):
                raise ValueError('message metadata mismatch')
            if not meta.HasField('created_at'):
                missing_time += 1
                continue
            stamp = meta.created_at.ToDatetime(tzinfo=timezone.utc).timestamp()
            if not start <= stamp < end:
                continue
            value = step.user_input
            text = value.user_response or value.query or '\n'.join(x.text for x in value.items)
            if text.strip():
                messages.append({'time': datetime.fromtimestamp(stamp, timezone.utc).isoformat(), 'text': text, 'id': f'{path.stem}:{idx}'})
    except Exception as exc:
        errors.append(type(exc).__name__)
print(json.dumps({'messages': messages, 'files_scanned': scanned, 'errors': errors, 'missing_time': missing_time, 'unknown_fields': unknown}, ensure_ascii=False))
