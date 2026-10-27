#!/usr/bin/env python3
"""Validate learning schema, evidence, and exact recorded write authorization."""
import argparse
import copy
import hashlib
import json
import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()


def payload_digest(record):
    content = copy.deepcopy(record)
    content.pop('publication_authorization', None)
    return hashlib.sha256(json_bytes(content)).hexdigest()


def batch_policy_digest(manifest):
    return hashlib.sha256(json_bytes({key: manifest[key] for key in
                                     ['batch_id', 'window', 'authorization']})).hexdigest()


@lru_cache(maxsize=1)
def schema_data():
    try:
        from jsonschema import Draft202012Validator
    except ImportError as exc:
        raise ValueError('jsonschema unavailable; run with uv run --with jsonschema -- python') from exc
    schema = json.loads((Path(__file__).resolve().parent.parent /
                         'references/record-schema.json').read_text())
    Draft202012Validator.check_schema(schema)
    return schema, Draft202012Validator


def validate_kind(value, kind, *, allow_archival_verdict=False):
    schema, validator = schema_data()
    if allow_archival_verdict:
        schema = copy.deepcopy(schema)
        projection = schema['$defs']['RecordDraft']['properties']['observation']['properties']['reader_projection']
        projection['properties']['Verdict']['enum'] += [None, 'Blocked', 'Completed']
    errors = validator({'$ref': '#/$defs/' + kind,
                        '$defs': schema['$defs']}).iter_errors(value)
    first = next(errors, None)
    if first is not None:
        location = '.'.join(map(str, first.absolute_path)) or '<root>'
        raise ValueError(f'{kind} schema violation at {location} ({first.validator})')


def load_hashed(root, folder, digest):
    if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
        raise ValueError('invalid content digest')
    body = (root / folder / f'{digest}.json').read_bytes()
    if hashlib.sha256(body).hexdigest() != digest:
        raise ValueError(f'{folder} checksum mismatch')
    return json.loads(body)


def verify_authorization(root, record, evidence, store):
    auth = record['publication_authorization']
    digest = payload_digest(record)
    if auth['payload_sha256'] != digest:
        raise ValueError('reviewed payload does not match current record')
    context = record['capture_context']
    if context['flow'] != auth['flow']:
        raise ValueError('capture flow and authorization flow differ')
    if auth['flow'] == 'interactive':
        if context['selection_method'] != 'interactive_selected_item':
            raise ValueError('interactive record has a non-interactive selection method')
        approval = load_hashed(root, 'approvals', auth['approval_sha256'])
        validate_kind(approval, 'Approval')
        if approval['reviewed_payload_sha256'] != digest:
            raise ValueError('approval is for a different payload')
        if 'save_record' not in approval['approved_actions']:
            raise ValueError('approval does not authorize save_record')
        return
    if context['selection_method'] != 'authorized_timeline_batch':
        raise ValueError('a separately selected old case is not a timeline-batch assignment')
    batch_id = auth['batch_id']
    if context.get('historical_batch_id') != batch_id or not context.get('task_key'):
        raise ValueError('historical record lacks assigned batch/task provenance')
    if record['task']['id'] != context['task_key'] or record['observation']['task_id'] != context['task_key']:
        raise ValueError('historical record identity differs from its assigned task')
    folder = f'batches/{batch_id}'
    manifest = json.loads((root / folder / 'manifest.json').read_text())
    grant = manifest.get('authorization') or {}
    if not (grant.get('post_review_record_capture')
            and grant.get('source', {}).get('origin') == 'direct_human'
            and grant.get('source', {}).get('quote')
            and 'save_record' in grant.get('allowed_actions', [])):
        raise ValueError('batch has no human post-review authorization')
    if auth['batch_policy_sha256'] != batch_policy_digest(manifest):
        raise ValueError('historical batch policy changed')
    assignment = load_hashed(root, folder + '/assignments', auth['assignment_sha256'])
    validate_kind(assignment, 'HistoricalAssignment')
    if assignment['batch_id'] != batch_id:
        raise ValueError('assignment belongs to a different batch')
    index = load_hashed(root, folder + '/task-index', auth['task_index_sha256'])
    validate_kind(index, 'HistoricalTaskIndex')
    if index['task_key'] != context['task_key']:
        raise ValueError('qualifying events belong to a different task')
    scope = assignment['scope']
    if not (index['task_key'] in scope['task_keys'] or index['owner_day'] in scope['day_partitions']):
        raise ValueError('task is outside the human-assigned partitions/tasks')
    declared_date = record['task'].get('session_date')
    if declared_date and index['original_session_date'] != declared_date:
        raise ValueError('original session date differs from the task index')
    target, destinations = record['notion'], store.get('destinations') or {}
    if target['workspace_id'] != destinations.get('workspace_id') or target['data_source_id'] != destinations.get('cases_data_source_id'):
        raise ValueError('historical exception cannot change publication destination')
    start = datetime.fromisoformat(manifest['window']['start'])
    end = datetime.fromisoformat(manifest['window']['end_exclusive'])
    allowed = {entry['sha256']: entry['event_time'] for entry in index['qualifying_evidence']}
    in_window = False
    for digest_key, item in evidence.items():
        if digest_key not in allowed:
            continue
        locator = item['source_locator']
        raw = locator.get('event_time') or locator.get('time')
        if not raw or raw != allowed[digest_key]:
            continue
        try:
            event = datetime.fromisoformat(raw.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            continue
        if event.tzinfo is None:
            continue
        if declared_date and event.astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat() < declared_date:
            raise ValueError('qualifying event predates the declared original session')
        if start <= event < end:
            in_window = True
    if not in_window:
        raise ValueError('no assigned-task source event supports the historical exception')


def validate_record(root, record, store, revision_digest=None, evidence_root=None, draft=False):
    archival = (store.get('verdict_policy') or {}).get('legacy_canonical_read_revisions') or {}
    allow_archival_verdict = bool(
        not draft and revision_digest and record.get('schema_version') == 2
        and archival.get(record.get('case_id')) == revision_digest
        and hashlib.sha256(json_bytes(record)).hexdigest() == revision_digest)
    if draft:
        validate_kind(record, 'RecordDraft')
    else:
        validate_kind(record, 'CaseRecord', allow_archival_verdict=allow_archival_verdict)
    evidence_root = evidence_root or root
    evidence = {}
    for ref in record['evidence']:
        if ref['path'] != f"evidence/{ref['sha256']}.json":
            raise ValueError('unexpected evidence path')
        value = load_hashed(evidence_root, 'evidence', ref['sha256'])
        validate_kind(value, 'EvidenceObject')
        if value['evidence_id'] != ref['evidence_id']:
            raise ValueError('evidence identity differs from its reference')
        evidence[ref['sha256']] = value
    verdict = record['observation']['reader_projection'].get('Verdict')
    if verdict == 'Good practice':
        nomination = record.get('human_nomination') or {}
        nominated = evidence.get(nomination.get('evidence_sha256'))
        if not nominated or nominated['kind'] not in ['user', 'visible_user_message', 'human_comment']:
            raise ValueError('specific nomination is not attached human evidence')
    if draft:
        return len(evidence)
    if record['schema_version'] == 1:
        if not revision_digest or store.get('legacy_frozen_revisions', {}).get(record['case_id']) != revision_digest:
            raise ValueError('version 1 cannot bypass approval: not a frozen legacy revision')
    else:
        verify_authorization(root, record, evidence, store)
    return len(evidence)


def check(root):
    errors, case_count, evidence_refs = [], 0, 0
    try:
        store = json.loads((root / 'store.json').read_text())
        schema_data()
    except (OSError, ValueError) as exc:
        return {'ok': False, 'cases': 0, 'evidence_references': 0,
                'errors': [{'error': str(exc)}]}
    for pointer in sorted((root / 'cases').glob('*/current.json')):
        case_id = pointer.parent.name
        try:
            current = json.loads(pointer.read_text())
            validate_kind(current, 'CurrentPointer')
            digest = current['revision_sha256']
            if current['revision_path'] != f'revisions/{digest}.json':
                raise ValueError('unexpected revision path')
            record = load_hashed(pointer.parent, 'revisions', digest)
            if record['case_id'] != case_id or current['case_id'] != case_id:
                raise ValueError('case identity mismatch')
            evidence_refs += validate_record(root, record, store, revision_digest=digest)
            case_count += 1
        except (KeyError, ValueError, OSError, TypeError) as exc:
            errors.append({'case_id': case_id, 'error': str(exc)})
    return {'ok': not errors, 'cases': case_count,
            'evidence_references': evidence_refs, 'errors': errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('~/.local/share/workflow-notes').expanduser())
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--candidate', type=Path, help='Verify authorization before canonical writes')
    group.add_argument('--draft', type=Path, help='Validate staging only; does not authorize writes')
    parser.add_argument('--evidence-root', type=Path, help='Staged evidence base for candidate/draft validation')
    args = parser.parse_args()
    root = args.root.expanduser()
    if args.candidate or args.draft:
        try:
            record = json.loads((args.candidate or args.draft).read_text())
            store = json.loads((root / 'store.json').read_text())
            count = validate_record(root, record, store, evidence_root=args.evidence_root,
                                    draft=bool(args.draft))
            result = {'ok': True, 'evidence_references': count,
                      'write_authorized': bool(args.candidate)}
        except (KeyError, ValueError, OSError, TypeError) as exc:
            result = {'ok': False, 'write_authorized': False, 'error': str(exc)}
    else:
        result = check(root)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
