"""Offline source-carrier, retry and recovery acceptance checks."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch

import state


class ReadingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.evidence = self.root / 'observed.txt'
        self.evidence.write_text('fictional source evidence')
        self.item = {'key': 'douyin:123', 'route': 'knowledge', 'status': 'pending_read'}
        history = self.root / 'attempt-history.json'
        history.write_text(json.dumps({'source_key': self.item['key'], 'history_complete': True, 'prior_attempts': []}))
        self.item['reading_attempt_history_evidence'] = str(history)
        classification = self.root / 'classification.json'
        classification.write_text(json.dumps(self.receipt('speech')))
        self.item['reading_receipt'] = str(classification)
        (self.root / 'trial.json').write_text('{}')

    def receipt(self, carrier='captions'):
        return {'version': 1, 'source_key': self.item['key'], 'carrier': carrier,
                'audio_kind': 'music_only' if carrier == 'captions' else 'speech',
                'basis': 'manual_inspection', 'evidence_path': str(self.evidence),
                'duration_seconds': 2, 'visuals_verified': True,
                'captions': {'sample_times': [n / 4 for n in range(9)],
                             'all_text_reviewed': True, 'changes_reviewed': True,
                             'unresolved_low_confidence': 0, 'unreadable_intervals': []},
                'speech': {'method': 'asr', 'recognition_verified': True,
                           'reviewed_ranges': [[0, 2]], 'language': 'zh',
                           'expected_language': 'zh', 'segments': [{'text': 'A fictional sentence.'}]}}

    def check(self, receipt):
        path = self.root / 'reading.json'
        path.write_text(json.dumps(receipt))
        return state.validate_reading({**self.item, 'reading_receipt': str(path)}, required=True)

    def test_music_and_captions_need_no_speech_recognition(self):
        r = self.receipt()
        r['audio_kind'] = 'music_only'
        del r['speech']
        self.assertTrue(self.check(r))

    def test_speech_and_mixed_require_their_actual_carriers(self):
        r = self.receipt('speech')
        del r['captions']
        self.assertTrue(self.check(r))
        r['speech']['recognition_verified'] = False
        with self.assertRaises(ValueError): self.check(r)
        r = self.receipt('mixed')
        self.assertTrue(self.check(r))
        del r['captions']
        with self.assertRaises(ValueError): self.check(r)

    def test_repeated_hallucinations_and_wrong_language_fail(self):
        r = self.receipt('speech')
        r['speech']['segments'] = [{'text': 'Repeated hallucination.'}] * 5
        with self.assertRaises(ValueError): self.check(r)
        r = self.receipt('speech')
        r['speech']['language'] = 'ko'
        with self.assertRaises(ValueError): self.check(r)

    def test_sparse_or_low_confidence_or_incomplete_captions_fail(self):
        for change in ({'sample_times': [0, 2]}, {'unresolved_low_confidence': 1},
                       {'changes_reviewed': False}, {'unreadable_intervals': [[1, 1.5]]}):
            r = self.receipt(); r['captions'].update(change)
            with self.assertRaises(ValueError): self.check(r)
        r = self.receipt(); r['source_key'] = 'douyin:456'
        with self.assertRaises(ValueError): self.check(r)

    def test_unknown_carrier_and_missing_receipt_cannot_complete(self):
        with self.assertRaises(ValueError): self.check(self.receipt('unknown'))
        missing = dict(self.item); missing.pop('reading_receipt')
        with self.assertRaises(ValueError): state.validate_reading(missing, required=True)
        r = self.receipt(); r['audio_kind'] = 'unknown'
        with self.assertRaises(ValueError): self.check(r)

    def test_two_attempt_limit_and_materially_different_alternative(self):
        first = {'engine': 'local', 'model': 'small', 'source_revision': 'v1', 'estimated_cost': 0}
        item = {**self.item, 'reading_attempts': [first]}
        state.validate_attempts(item, {})
        with self.assertRaises(ValueError):
            state.validate_attempts({**item, 'reading_attempts': [first, {**first, 'language': 'zh'}]}, item)
        second = {**first, 'model': 'larger', 'difference_evidence': 'Different installed model'}
        two = {**item, 'reading_attempts': [first, second]}
        state.validate_attempts(two, item)
        with self.assertRaises(ValueError): state.validate_attempts({**two, 'reading_attempts': [first, second, second]}, two)
        with self.assertRaises(ValueError): state.validate_attempts({**item, 'reading_attempts': []}, item)
        with self.assertRaises(ValueError): state.validate_attempts({**item, 'reading_attempts': [{**first, 'estimated_cost': .01}]}, {})

    def test_unchanged_pending_reenters_only_with_authorized_condition(self):
        item = {**self.item, 'unchanged': True, 'reading_blocker': {'gap': 'Carrier needs confirmation'}}
        self.assertEqual(state.item_plan(item, {})['action'], 'report')
        for reason in ('user_clarification', 'source_changed', 'tool_changed', 'manual_request'):
            result = state.item_plan(item, {'resume_reason': reason, 'authorization': 'Current human request'})
            self.assertEqual(result['action'], 'resume')

    def test_completed_dedup_and_unknown_mutations_never_retry(self):
        request = {'resume_reason': 'manual_request', 'authorization': 'Current human request'}
        for item in ({**self.item, 'status': 'complete'}, {**self.item, 'save_outcome': 'unknown'},
                     {**self.item, 'cleanup_outcome': 'unknown'}):
            result = state.item_plan(item, request)
            self.assertEqual(result['action'], 'reconcile')
            self.assertFalse(result['allow_external_retry'])

    def cli(self, command, payload=None, *args):
        argv = ['state.py', '--root', str(self.root), command, *args]
        if payload is not None:
            path = self.root / 'request.json'; path.write_text(json.dumps(payload))
            argv += ['--file', str(path)]
        output = io.StringIO()
        with patch.object(sys, 'argv', argv), contextlib.redirect_stdout(output):
            state.main()
        return json.loads(output.getvalue())

    def test_existing_record_and_ready_commands_enforce_new_acceptance(self):
        run = self.cli('begin')['run']['id']
        item = {**self.item, 'status': 'archived', 'archive_verified': True,
                'coverage_complete': True, 'index_verified': True,
                'index_url': 'https://app.notion.com/p/article', 'note_url': 'https://app.notion.com/p/article'}
        item.pop('reading_receipt')
        before = (self.root / 'state.json').read_bytes()
        with self.assertRaises(ValueError): self.cli('record', item, '--run', run)
        self.assertEqual(before, (self.root / 'state.json').read_bytes())
        self.check(self.receipt())
        item['reading_receipt'] = str(self.root / 'reading.json')
        saved = self.cli('record', item, '--run', run)
        self.assertTrue(saved['reading_contract_required'])
        self.assertTrue(self.cli('ready', None, '--key', item['key'])['cleanup_ready'])
        self.cli('record', {**item, 'save_outcome': 'unknown', 'save_intent_id': 'save-1'}, '--run', run)
        request = {'resume_reason': 'manual_request', 'authorization': 'Current human request'}
        self.assertEqual(self.cli('plan', request, '--key', item['key'])['action'], 'reconcile')
        before = (self.root / 'state.json').read_bytes()
        with self.assertRaises(ValueError): self.cli('record', {**item, 'save_outcome': 'verified'}, '--run', run)
        self.assertEqual(before, (self.root / 'state.json').read_bytes())
        with self.assertRaises(ValueError): self.cli('ready', None, '--key', item['key'])

    def test_paid_limit_is_explicit_and_reentry_does_not_reset_attempts(self):
        first = {'engine': 'existing-provider', 'model': 'model-a', 'estimated_cost': .1, 'currency': 'USD'}
        item = {**self.item, 'reading_attempts': [first], 'reading_cost_limit': .1,
                'reading_cost_authorization': 'Explicit bounded human grant', 'reading_cost_currency': 'USD'}
        state.validate_attempts(item, {})
        request = {'resume_reason': 'tool_changed', 'authorization': 'Current human request',
                   'next_attempt': {**first, 'model': 'model-b', 'difference_evidence': 'Different model'}}
        self.assertEqual(state.item_plan(item, request)['action'], 'report')
        self.assertEqual(len(item['reading_attempts']), 1)

    def test_excluded_source_or_folder_cannot_start_recognition(self):
        request = {'resume_reason': 'tool_changed', 'authorization': 'Current human request',
                   'next_attempt': {'engine': 'local', 'model': 'first', 'estimated_cost': 0}}
        policy = {'bilibili_scope': {'folder_ids': ['11']}}
        for item in ({**self.item, 'scope_excluded': True},
                     {**self.item, 'key': 'bilibili:BV1w1pb6yEBn', 'folder_ids': ['22']}):
            result = state.item_plan(item, request, policy)
            self.assertEqual(result['reason'], 'outside_authorized_source_scope')
            self.assertFalse(result['allow_external_retry'])

    def test_reconciliation_is_bound_to_source_stage_and_latest_intent(self):
        run = self.cli('begin')['run']['id']
        item = {**self.item, 'index_url': 'https://app.notion.com/p/article',
                'save_outcome': 'unknown', 'save_intent_id': 'save-1'}
        self.cli('record', item, '--run', run)
        receipt = {'source_key': item['key'], 'stage': 'save', 'intent_id': 'save-1',
                   'outcome': 'verified', 'evidence_path': str(self.evidence)}
        path = self.root / 'reconciled.json'; path.write_text(json.dumps(receipt))
        self.cli('record', {**item, 'save_outcome': 'verified', 'reconciliation_evidence': str(path)}, '--run', run)
        self.cli('record', {'key': item['key'], 'status': 'pending_read',
                           'cleanup_outcome': 'unknown', 'cleanup_intent_id': 'cleanup-1'}, '--run', run)
        before = (self.root / 'state.json').read_bytes()
        for change in ({}, {'reconciliation_evidence': str(path)}):
            with self.assertRaises(ValueError):
                self.cli('record', {'key': item['key'], 'status': 'pending_read',
                                   'cleanup_outcome': 'not_applied', **change}, '--run', run)
            self.assertEqual(before, (self.root / 'state.json').read_bytes())
        receipt.update(stage='cleanup', intent_id='stale-cleanup', outcome='not_applied')
        path.write_text(json.dumps(receipt))
        with self.assertRaises(ValueError):
            self.cli('record', {'key': item['key'], 'status': 'pending_read',
                               'cleanup_outcome': 'not_applied', 'reconciliation_evidence': str(path)}, '--run', run)
        receipt['intent_id'] = 'cleanup-1'; path.write_text(json.dumps(receipt))
        self.cli('record', {'key': item['key'], 'status': 'pending_read',
                           'cleanup_outcome': 'not_applied', 'reconciliation_evidence': str(path)}, '--run', run)
        with self.assertRaises(ValueError):
            self.cli('record', {'key': item['key'], 'status': 'pending_read',
                               'cleanup_outcome': 'pending', 'cleanup_intent_id': 'cleanup-1'}, '--run', run)

    def test_legacy_attempts_are_not_reset_or_granted_another_pair(self):
        first = {'engine': 'local', 'model': 'small', 'source_revision': 'v1', 'estimated_cost': 0}
        item = {**self.item, 'reading_attempts': [first]}
        item.pop('reading_attempt_history_evidence')
        with self.assertRaises(ValueError): state.validate_attempts(item, {})
        history = {'source_key': self.item['key'], 'history_complete': True, 'prior_attempts': [first, first]}
        Path(self.item['reading_attempt_history_evidence']).write_text(json.dumps(history))
        item = {**self.item, 'reading_attempts': [first, first]}
        state.validate_attempts(item, {})  # Preserve old nonconforming attempts as history.
        request = {'resume_reason': 'tool_changed', 'authorization': 'Current human request',
                   'next_attempt': {**first, 'model': 'larger', 'difference_evidence': 'Different model'}}
        self.assertEqual(state.item_plan(item, request)['action'], 'report')

    def test_rewriting_external_history_cannot_expand_sealed_budget(self):
        first = {'engine': 'local', 'model': 'small', 'source_revision': 'v1', 'estimated_cost': 0}
        second = {**first, 'model': 'larger', 'difference_evidence': 'Different model'}
        old = {**self.item, 'reading_attempts': [first, second]}
        state.validate_attempts(old, {})
        self.assertEqual(old['reading_prior_attempts'], [])
        third = {**first, 'model': 'another', 'difference_evidence': 'Another model'}
        history = {'source_key': old['key'], 'history_complete': True, 'prior_attempts': [first, second, third]}
        Path(old['reading_attempt_history_evidence']).write_text(json.dumps(history))
        with self.assertRaises(ValueError):
            state.validate_attempts({**old, 'reading_attempts': [first, second, third]}, old)

    def test_music_or_unclassified_source_cannot_plan_asr(self):
        request = {'resume_reason': 'manual_request', 'authorization': 'Current human request',
                   'next_attempt': {'engine': 'local', 'model': 'first', 'estimated_cost': 0}}
        item = dict(self.item); item.pop('reading_receipt')
        self.assertFalse(state.item_plan(item, request)['allow_external_retry'])
        Path(self.item['reading_receipt']).write_text(json.dumps(self.receipt('captions')))
        self.assertFalse(state.item_plan(self.item, request)['allow_external_retry'])
        Path(self.item['reading_receipt']).write_text(json.dumps(self.receipt('speech')))
        self.assertTrue(state.item_plan(self.item, request)['allow_external_retry'])


if __name__ == '__main__':
    unittest.main()
