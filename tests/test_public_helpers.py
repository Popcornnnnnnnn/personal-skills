"""Offline acceptance of configuration boundaries and claimed send evidence."""
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PublicHelperTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.home_patch = patch.object(Path, 'home', return_value=self.home)
        self.home_patch.start()
        self.addCleanup(self.home_patch.stop)
        self.addCleanup(self.tmp.cleanup)

    def configure(self, value):
        p = self.home / '.config/personal-skills/settings.json'
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(value))

    def test_fresh_install_has_no_preconfigured_accounts(self):
        module = load('empty_accounts', 'saved-content-review/scripts/state.py')
        self.assertEqual(module.ACCOUNTS, {'xhs': '', 'douyin': '', 'bilibili': ''})
        self.assertFalse(module.nonblocking_unavailable({'platform': 'xhs', 'account': ''}))

    def test_explicit_account_configuration_is_loaded(self):
        self.configure({'saved_content_review': {'accounts': {'xhs': 'fixture-owner'}}})
        module = load('configured_accounts', 'saved-content-review/scripts/state.py')
        self.assertEqual(module.ACCOUNTS['xhs'], 'fixture-owner')
        self.assertEqual(module.ACCOUNTS['douyin'], '')

    def test_dry_run_neither_needs_recipient_nor_starts_bridge(self):
        module = load('handoff_preview', 'tell-dot/scripts/send_to_finn.py')
        with patch.object(module.subprocess, 'Popen') as child:
            result = module.run_codex_send('selected topic', dry_run=True)
        self.assertTrue(result['ok'])
        self.assertEqual(result['messages_sent'], 0)
        child.assert_not_called()

    def test_send_without_recipient_stops_before_bridge(self):
        module = load('handoff_missing_target', 'tell-dot/scripts/send_to_finn.py')
        with patch.object(module.subprocess, 'Popen') as child:
            with self.assertRaises(ValueError):
                module.run_codex_send('selected topic')
        child.assert_not_called()

    def test_delivery_requires_exact_tool_receipt(self):
        module = load('handoff_evidence', 'tell-dot/scripts/send_to_finn.py')
        target = {'conversation_id': 'DTEST'}
        report = {'ok': True, 'channel_id': 'DTEST', 'message_ts': '123.456'}
        self.assertFalse(module.verified_delivery(report, [], target))
        call = {'tool': 'slack_send_message', 'status': 'completed', 'result': {'content': [{'text': json.dumps({'channel_id': 'DTEST', 'ts': '123.456'})}]}}
        self.assertTrue(module.verified_delivery(report, [call], target))
        call['result']['content'][0]['text'] = json.dumps({'channel_id': 'DOTHER', 'ts': '123.456'})
        self.assertFalse(module.verified_delivery(report, [call], target))

    def test_failed_receipt_and_echoed_message_do_not_prove_delivery(self):
        module = load('handoff_rejected_evidence', 'tell-dot/scripts/send_to_finn.py')
        target = {'conversation_id': 'DTEST'}
        report = {'ok': True, 'channel_id': 'DTEST', 'message_ts': '123.456'}
        failed = {'tool': 'slack_send_message', 'status': 'completed', 'result': {'isError': True, 'channel_id': 'DTEST', 'ts': '123.456'}}
        self.assertFalse(module.verified_delivery(report, [failed], target))
        echoed = {'tool': 'slack_send_message', 'status': 'completed', 'result': {'channel_id': 'DOTHER', 'ts': '789.000', 'message': {'text': json.dumps({'channel_id': 'DTEST', 'ts': '123.456'})}}}
        self.assertFalse(module.verified_delivery(report, [echoed], target))

    def test_bridge_uses_normal_permissions_and_rejects_model_only_success(self):
        self.configure({'tell_dot': {'workspace_id': 'TTEST', 'recipient_user_id': 'UTEST', 'conversation_id': 'DTEST'}})
        module = load('handoff_bridge', 'tell-dot/scripts/send_to_finn.py')
        stdout = json.dumps({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': '```json\n{"ok":true,"channel_id":"DTEST","message_ts":"123.456"}\n```'}})
        process = types.SimpleNamespace(returncode=0, communicate=lambda **kw: (stdout, ''))
        with patch.object(module.subprocess, 'Popen', return_value=process) as child:
            result = module.run_codex_send('selected topic')
        self.assertFalse(result['ok'])
        command = child.call_args.args[0]
        self.assertFalse(any('bypass' in item or 'danger-full-access' in item for item in command))

    def test_asr_origin_and_credential_binding_are_explicit(self):
        # The test needs no provider package or network; the module only references
        # requests while executing, so supply a harmless stub during import.
        with patch.dict(sys.modules, {'requests': types.SimpleNamespace(RequestException=Exception)}):
            module = load('voice_origin', 'voice-memo-notion/scripts/transcribe.py')
        self.assertEqual(module.ORIGIN, '')
        self.assertIsNone(module.RATE)
        with self.assertRaises(RuntimeError):
            module.configured_origin()
        for value in ['http://dashscope.aliyuncs.com', 'https://unrelated.example', 'https://dashscope.aliyuncs.com/private', 'https://dashscope.aliyuncs.com@unrelated.example']:
            module.ORIGIN = value
            with self.assertRaises(RuntimeError):
                module.configured_origin()
        module.ORIGIN = 'https://dashscope.aliyuncs.com'
        self.assertEqual(module.configured_origin(), module.ORIGIN)
        with patch.dict(os.environ, {}, clear=True), patch.object(module.subprocess, 'run') as command:
            with self.assertRaises(RuntimeError):
                module.keychain_key()
        command.assert_not_called()

    def test_release_check_finds_private_home_and_broken_reference(self):
        module = load('release_check', 'tools/check_release.py')
        package = self.home / 'release'
        skill = package / 'sample'
        skill.mkdir(parents=True)
        (package / 'LICENSE').write_text('fixture license')
        (skill / 'SKILL.md').write_text('---\nname: sample\ndescription: "Use for fixture checks"\n---\n[missing](missing.md)\n' + '/Users/' + 'someone' + '/private\n')
        errors, _, _ = module.check(package)
        self.assertTrue(any('machine-specific home' in item for item in errors))
        self.assertTrue(any('unresolved' in item for item in errors))


if __name__ == '__main__':
    unittest.main()
