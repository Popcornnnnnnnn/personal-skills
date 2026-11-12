import json
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from datetime import datetime
from unittest.mock import patch
import night_watch as nw


class NightWatchTest(unittest.TestCase):
    def setUp(self):
        self.accounts_patch = patch('state.ACCOUNTS', {'xhs': 'fixture-xhs', 'douyin': 'fixture-douyin', 'bilibili': 'fixture-bilibili'})
        self.accounts_patch.start()
        self.addCleanup(self.accounts_patch.stop)

    def finished_with_unavailable_xhs(self, root):
        snapshot = {'platform': 'xhs', 'account': 'fixture-xhs', 'displayed_total': 2,
                    'accessible_count': 0, 'unknown_count': 2, 'pagination_complete': True, 'coverage_complete': False}
        classified = {**snapshot, 'visibility': {'status': 'content_unavailable', 'non_blocking': True,
            'reason_confirmed': False, 'basis': 'user_confirmed_empty_collection',
            'confirmed_displayed_total': 2, 'user_confirmation': 'User repeatedly checked official client: empty'}}
        run = {'id': 'r1', 'date': '2026-10-19', 'kind': 'collect', 'status': 'finished',
               'scheduled_for': '2026-10-19T04:00:00+08:00', 'started_at': '2026-10-19T04:04:00+08:00',
               'finished_at': '2026-10-19T04:12:00+08:00', 'platforms': {'xhs': snapshot},
               'coverage': {'xhs': snapshot, 'douyin': {'coverage_complete': True}, 'bilibili': {'coverage_complete': True}},
               'audits': [{'channel_observations': {'xhs': classified}}],
               'blockers': [{'type': 'xhs_unidentified_count_gap'}, {'type': 'phone_start_failure', 'stage': 'xhs_mobile_inventory'},
                            {'type': 'same_date_daily_page_not_yet_present'}],
               'counts': {'notes_created': 0}, 'brief_delivered': False}
        folder = root / 'runs/r1'
        folder.mkdir(parents=True)
        (folder / 'voice-memos.json').write_text(json.dumps({'coverage_complete': True, 'outcomes': []}))
        (folder / 'trigger.json').write_text(json.dumps({'actual_trigger_beijing': '2026-10-19T04:03:00+08:00'}))
        return run

    def test_unavailable_channel_preserves_other_successes_and_delivery_pending(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            run = self.finished_with_unavailable_xhs(root)
            h = nw.health({'runs': {'r1': run}}, datetime.fromisoformat('2026-10-19T08:00:00+08:00'), root)
            self.assertEqual(h['channels']['xhs']['result'], 'unavailable')
            self.assertFalse(h['channels']['xhs']['coverage']['coverage_complete'])
            for name in ('douyin', 'bilibili', 'voice_memos'):
                self.assertEqual(h['channels'][name]['result'], 'success')
            self.assertTrue(h['attention'])  # Missing delivery, not the invisible count.
            self.assertIn('No verified daily report delivery receipt', h['issues'])
            run.update(brief_url='https://app.notion.com/p/daily', brief_date='2026-10-19', brief_delivered=True)
            h = nw.health({'runs': {'r1': run}}, datetime.fromisoformat('2026-10-19T08:00:00+08:00'), root)
            self.assertFalse(h['attention'])
            self.assertTrue(h['delivery']['delivered'])
            self.assertEqual(len(h['failure_history']), 3)
            self.assertEqual(h['execution']['actual_trigger_beijing'], '2026-10-19T04:03:00+08:00')

    def test_real_channel_failure_and_unreadable_voice_do_not_hide_other_channels(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            run = self.finished_with_unavailable_xhs(root)
            run['coverage']['douyin'] = {'scanned': False, 'coverage_complete': False}
            (root / 'runs/r1/voice-memos.json').write_text('invalid json')
            h = nw.health({'runs': {'r1': run}}, datetime.fromisoformat('2026-10-19T08:00:00+08:00'), root)
            self.assertEqual(h['channels']['douyin']['result'], 'failed')
            self.assertEqual(h['channels']['bilibili']['result'], 'success')
            self.assertTrue(h['attention'])
            self.assertTrue(any('Unreadable Voice' in str(i) for i in h['issues']))
            # A changed observation cannot inherit the old human-confirmed empty-list waiver.
            run['platforms']['xhs']['displayed_total'] = 3
            h = nw.health({'runs': {'r1': run}}, datetime.fromisoformat('2026-10-19T08:00:00+08:00'), root)
            self.assertEqual(h['channels']['xhs']['result'], 'failed')

    def test_no_run_is_failure_not_empty(self):
        h = nw.health({'runs': {}}, datetime.fromisoformat('2026-10-19T08:00:00+08:00'), Path('/unused'))
        self.assertEqual(h['state'], 'missing_run')
        self.assertTrue(h['attention'])
        self.assertFalse(h['model_used'])

    def test_uncertain_handoff_is_distinct_from_missing_receipt(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            path = root / 'handoffs/2026-10-19/processing.json'
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({'date': '2026-10-19', 'outcome': 'unknown',
                'observed_at': '2026-10-19T04:00:30+08:00', 'request_id': 'fixture-request',
                'collector_thread_id': 'fixture-thread'}))
            h = nw.health({'runs': {}}, datetime.fromisoformat('2026-10-19T08:00:00+08:00'), root)
            self.assertEqual(h['state'], 'handoff_unknown')
            path.write_text('{}')
            self.assertEqual(nw.health({'runs': {}}, datetime.fromisoformat('2026-10-19T08:00:00+08:00'), root)['state'], 'missing_run')

    def test_missing_channel_and_expired_run_are_visible(self):
        r = {'id': 'r1', 'date': '2026-10-19', 'kind': 'collect', 'status': 'running', 'started_at': '2026-10-19T04:00:00+08:00'}
        h = nw.health({'runs': {'r1': r}}, datetime.fromisoformat('2026-10-19T08:00:00+08:00'), Path('/unused'))
        self.assertEqual(h['state'], 'completion_unconfirmed')
        self.assertEqual(h['channels']['voice_memos']['state'], 'unverified')

    def test_empty_requires_finished_run_two_inventories_and_unchanged_evidence(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            run = self.finished_with_unavailable_xhs(root)
            folder = root / 'runs/r1'
            receipt = {'run_id': 'r1', 'date': run['date'], 'platform': 'douyin',
                       'account': 'fixture-douyin', 'account_verified': True, 'positive_empty': True,
                       'accessible_count': 0, 'displayed_total': 0, 'unknown_count': 0,
                       'pagination_complete': True}
            for key, name, when in [('source_access', 'before.json', '04:05:00'),
                                    ('independent_readback', 'after.json', '04:10:00')]:
                (folder / name).write_text(key)
                receipt[key] = {'path': name, 'observed_at': f'2026-10-19T{when}+08:00',
                                'sha256': hashlib.sha256(key.encode()).hexdigest()}
            (folder / 'empty-douyin.json').write_text(json.dumps(receipt))
            snapshot = {'account': 'fixture-douyin', 'accessible_count': 0, 'displayed_total': 0,
                        'unknown_count': 0, 'pagination_complete': True, 'items': []}
            run['inventories'] = {'douyin': [dict(snapshot, phase='before'), dict(snapshot, phase='after')]}
            stage = {'id': 'verified_empty', 'platform': 'douyin', 'source_key': None,
                     'status': 'success', 'started_at': receipt['source_access']['observed_at'],
                     'ended_at': receipt['independent_readback']['observed_at'], 'cause_proven': False,
                     'next_step': '', 'evidence': [{'path': str(folder / receipt[k]['path']),
                        'sha256': receipt[k]['sha256']} for k in ('source_access', 'independent_readback')]}
            audit = {'version': 1, 'run_id': 'r1', 'date': run['date'], 'stages': [stage],
                     'counts': {k: 0 for k in ('discovered', 'fully_read', 'saved_verified', 'unfavorited', 'remaining')}}
            run['audits'] = [{'execution_audit': audit}]
            instant = datetime.fromisoformat('2026-10-19T08:00:00+08:00')
            def empty():
                return nw.health({'runs': {'r1': run}}, instant, root)['channels']['douyin']['empty_list']
            self.assertEqual(empty(), 'verified_empty')
            run['status'] = 'running'
            self.assertEqual(empty(), 'unverified')
            run['status'] = 'finished'
            run['inventories']['douyin'][1]['unknown_count'] = None
            self.assertEqual(empty(), 'unverified')
            run['inventories']['douyin'][1]['unknown_count'] = 0
            stage['status'] = 'unknown'
            self.assertEqual(empty(), 'unverified')
            stage['status'] = 'success'
            (folder / 'after.json').write_text('changed')
            self.assertEqual(empty(), 'unverified')

    def test_release_preserves_replacement_session(self):
        p = {'amphetamine_owned': True, 'deadline': '2026-10-19T05:40:00+08:00'}
        with patch.object(nw, 'amph', return_value='0') as call:
            nw.release(p, datetime.fromisoformat('2026-10-19T05:00:00+08:00'))
        call.assert_called_once_with('get session time remaining')

    def test_release_owned_unchanged_session_only(self):
        p = {'amphetamine_owned': True, 'deadline': '2026-10-19T05:40:00+08:00'}
        with patch.object(nw, 'amph', side_effect=['2400', '']) as call:
            nw.release(p, datetime.fromisoformat('2026-10-19T05:00:00+08:00'))
        self.assertEqual(call.call_args_list[-1].args, ('end session',))

    def test_preexisting_session_is_not_ended(self):
        with TemporaryDirectory() as d, patch.object(nw, 'amph', return_value='true') as call:
            root = Path(d)
            (root / 'state.json').write_text('{"runs":{}}')
            nw.tick(root, datetime.fromisoformat('2026-10-19T03:50:00+08:00'))
            nw.tick(root, datetime.fromisoformat('2026-10-19T04:20:00+08:00'))
            self.assertEqual(call.call_count, 1)
            self.assertIn('released_at', json.loads((root / 'health/power.json').read_text()))

    def test_wake_grace_and_fail_release_without_model_or_network(self):
        with TemporaryDirectory() as d, patch.object(nw, 'amph', side_effect=['false', '', '4800', '']) as call:
            root = Path(d)
            (root / 'state.json').write_text('{"runs":{}}')
            nw.tick(root, datetime.fromisoformat('2026-10-19T03:50:00+08:00'))
            nw.tick(root, datetime.fromisoformat('2026-10-19T04:20:00+08:00'))
            self.assertEqual(call.call_args_list[-1].args, ('end session',))
            self.assertEqual(json.loads((root / 'health/latest.json').read_text())['state'], 'missing_run')


if __name__ == '__main__':
    unittest.main()
