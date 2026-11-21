import importlib.util
import json
import os
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/collect.py'
spec = importlib.util.spec_from_file_location('collector', SCRIPT)
collect = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collect)
START = collect.timestamp('2026-11-03T00:00:00+08:00')
END = collect.timestamp('2026-11-04T00:00:00+08:00')

def write_lines(path, rows, tail=b''):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b''.join(json.dumps(row).encode()+b'\n' for row in rows) + tail)

def record(when, text, kind='user.text'):
    return {'type':'response_item', 'timestamp':when, 'payload':{'type':'message', 'role':'user', 'content':[{'type':'input_text','text':text}], 'internal_chat_message_metadata_passthrough':{'content_item_kinds':[kind]}}}

class CollectorTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        self.review = collect.Review(self.home, START, END)
    def tearDown(self):
        self.temp.cleanup()
    def test_codex_user_provenance_dates_forks_and_partial_tail(self):
        root = self.home / '.codex/sessions'
        header = {'type':'session_meta','payload':{'source':'vscode'}}
        at = '2026-11-02T16:00:00Z'
        valid = record(at, 'Why you not working?')
        rows = [header, record('2026-11-02T15:59:59Z', 'earlier'), valid,
                {'type':'event_msg','timestamp':at,'payload':{'type':'user_message','message':'mirror'}},
                record(at, 'injected rules', 'agents_md.instructions'),
                record('2026-11-03T16:00:00Z', 'next day')]
        write_lines(root/'one.jsonl', rows, b'{"type":')
        write_lines(root/'fork.jsonl', [header, valid])
        write_lines(root/'agent.jsonl', [{'type':'session_meta','payload':{'source':{'subagent':{'thread_spawn':{}}}}},record(at,'agent request')])
        self.review.codex()
        self.assertEqual([m['text'] for m in self.review.messages], ['Why you not working?'])
        self.assertEqual(self.review.coverage['Codex']['status'], 'partial')
    def test_pi_user_text_only_and_duplicate_forks(self):
        root = self.home / '.pi/agent/sessions/project'
        header = {'type':'session'}
        human = {'type':'message','timestamp':'2026-11-02T17:00:00Z','message':{'role':'user','content':[{'type':'text','text':'Please help me.'}]}}
        assistant = {'type':'message','timestamp':'2026-11-02T17:01:00Z','message':{'role':'assistant','content':[{'type':'text','text':'Not the user.'}]}}
        write_lines(root/'a.jsonl',[header,human,assistant])
        write_lines(root/'b.jsonl',[header,human])
        self.review.pi()
        self.assertEqual([m['text'] for m in self.review.messages], ['Please help me.'])
    def test_codex_question_form_keeps_free_text_not_suggested_choice(self):
        root = self.home/'.codex/sessions'
        at = '2026-11-02T17:00:00Z'
        call = {'type':'response_item','payload':{'type':'function_call','name':'request_user_input_async','call_id':'call-1','arguments':json.dumps({'questions':[{'title':'Pick one','options':['Yes','No']}]})}}
        def reply(value, callid='call-1'):
            answer = [{'questionItemId':json.dumps(['request_user_input_async',callid,0]),'question':'Pick one','answer':value}]
            return record(at, '<send_user_message_question_reply>'+json.dumps(answer)+'</send_user_message_question_reply>\n')
        write_lines(root/'a.jsonl',[{'type':'session_meta','payload':{'source':'vscode'}}, call, reply('Yes'), reply('My own words'), reply('unknown','missing-call')])
        self.review.codex()
        self.assertEqual([m['text'] for m in self.review.messages], ['My own words'])
        self.assertEqual(self.review.coverage['Codex']['status'], 'partial')
    def test_dsh_uses_source_kind_and_ignores_subagent(self):
        root = self.home / '.dsh/sessions'
        def compressed(path, depth):
            rows = [{'type':'session','delegationDepth':depth},
                    {'type':'user/message','time':int(START*1000),'data':{'source':{'kind':'user'},'content':[{'type':'text','text':'Can you help?'}]}},
                    {'type':'user/message','time':int(START*1000),'data':{'source':{'kind':'agent-instructions'},'content':[{'type':'text','text':'injected'}]}}]
            path.parent.mkdir(parents=True, exist_ok=True)
            data = b''.join(json.dumps(r).encode()+b'\n' for r in rows)
            path.write_bytes(subprocess.run(['zstd','-q','-c'],input=data,stdout=subprocess.PIPE,check=True).stdout)
        compressed(root/'root/session.v4.jsonl.zstd',0)
        compressed(root/'child/session.v4.jsonl.zstd',1)
        self.review.dsh()
        self.assertEqual([m['text'] for m in self.review.messages], ['Can you help?'])
    def test_opencode_root_and_unverified_child_coverage(self):
        p = self.home/'.local/share/opencode/opencode.db'
        p.parent.mkdir(parents=True)
        db = sqlite3.connect(p)
        db.executescript('CREATE TABLE session_v2(id TEXT,parent_id TEXT); CREATE TABLE session_message(session_id TEXT,type TEXT,time_created INTEGER,data TEXT);')
        db.executemany('INSERT INTO session_v2 VALUES (?,?)',[('root',None),('child','root')])
        db.executemany('INSERT INTO session_message VALUES (?,?,?,?)',[(s,'user',int(START*1000),json.dumps({'text':text})) for s,text in [('root','Why is this slow?'),('child','A delegated task')]])
        db.commit();db.close()
        self.review.opencode()
        self.assertEqual([m['text'] for m in self.review.messages], ['Why is this slow?'])
        self.assertEqual(self.review.coverage['OpenCode']['status'], 'partial')
    def test_zcode_uses_real_user_parts_and_drops_synthetic(self):
        p = self.home/'.zcode/cli/db/db.sqlite'
        p.parent.mkdir(parents=True)
        db = sqlite3.connect(p)
        db.executescript('CREATE TABLE session(id TEXT,parent_id TEXT); CREATE TABLE message(id TEXT,session_id TEXT,time_created INTEGER,data TEXT); CREATE TABLE part(message_id TEXT,data TEXT,sequence INTEGER);')
        db.execute('INSERT INTO session VALUES (?,?)',('s',None))
        msgs = [('u', {'role':'user','semantics':{'origin':'real_user'}}, {'type':'text','text':'Please open it.'}), ('synthetic', {'role':'user','synthetic':True}, {'type':'text','text':'Ignore me.'})]
        for ident,msg,part in msgs:
            db.execute('INSERT INTO message VALUES (?,?,?,?)',(ident,'s',int(START*1000),json.dumps(msg)))
            db.execute('INSERT INTO part VALUES (?,?,?)',(ident,json.dumps(part),0))
        db.commit();db.close()
        self.review.zcode()
        self.assertEqual([m['text'] for m in self.review.messages], ['Please open it.'])
    def test_attachments_redaction_and_batch_coverage(self):
        text = '# Applications mentioned by the user:\n<appshot>private rendered content</appshot>\n## My request:\nPlease try this.'
        self.assertEqual(collect.clean(text).strip(), 'Please try this.')
        annotation = '# Response annotations:\n<response-annotations>'+json.dumps([{'text':'assistant wording','annotation':'I do not understand'}])+'</response-annotations>\n## My request:\nPlease explain.'
        self.assertEqual(collect.clean(annotation).strip(), 'I do not understand\n\nPlease explain.')
        self.assertNotIn('topsecretvalue', collect.clean('password=topsecretvalue'))
        messages = [{'source':'test','time':'t','text':'x' * 12500}] + [{'source':'test','time':'t','text':str(i)} for i in range(35)]
        parts = [p for batch in collect.batches(messages) for p in batch]
        self.assertEqual(''.join(p['text'] for p in parts if p['message']==1), messages[0]['text'])
        self.assertTrue(all(len(batch)<=30 for batch in collect.batches(messages)))
    def test_raycast_say_in_english_default_sync_path_tombstones_and_errors(self):
        default_path = self.home/'.config/say-in-english/history.json'
        default_path.parent.mkdir(parents=True)
        in_ms = int(START*1000) + 1000
        out_ms = int((START - 1)*1000)
        payload = {
            'version': 1,
            'entries': [
                {'query': '续费', 'phrases': ['renew'], 'subtitle': 'renew', 'ipa': '', 'updatedAt': in_ms},
                {'query': 'situated', 'phrases': ['situated'], 'subtitle': '/ˈsɪtʃueɪtɪd/  Located in a particular place.', 'ipa': '/ˈsɪtʃueɪtɪd/', 'updatedAt': in_ms + 1000},
                {'query': 'gantry', 'phrases': ['gantry'], 'subtitle': 'A supporting frame.', 'ipa': '/ˈɡæntri/', 'updatedAt': in_ms + 2000},
                {'query': 'deleted-item', 'phrases': ['gone'], 'updatedAt': in_ms},
                {'query': 're-queried', 'phrases': ['back again'], 'updatedAt': in_ms + 5000},
                {'query': 'yesterday', 'phrases': ['old'], 'updatedAt': out_ms},
            ],
            'deleted': {'Deleted-Item': in_ms, 're-queried': in_ms},
        }
        default_path.write_text(json.dumps(payload))
        self.review.raycast_say_in_english()
        texts = [m['text'] for m in self.review.messages]
        self.assertEqual(texts, [
            '[Raycast "Say in English" lookup] Query: 续费 | Suggested English: renew',
            '[Raycast "Say in English" lookup] Query: situated | Meaning: /ˈsɪtʃueɪtɪd/  Located in a particular place.',
            '[Raycast "Say in English" lookup] Query: gantry | Meaning: A supporting frame. | IPA: /ˈɡæntri/',
            '[Raycast "Say in English" lookup] Query: re-queried | Suggested English: back again',
        ])
        self.assertEqual(self.review.coverage['Raycast Say in English']['status'], 'available')

        # Custom sync-path with ~/ expansion and a malformed entry
        custom_dir = self.home/'custom-sync'
        custom_dir.mkdir()
        sync_file = custom_dir/'hist.json'
        (self.home/'.config/say-in-english/sync-path').write_text('\n~/custom-sync/hist.json\n')
        sync_file.write_text(json.dumps({
            'version': 1,
            'entries': [
                {'query': '人机验证', 'phrases': ['CAPTCHA'], 'updatedAt': in_ms + 2000},
                {'query': '', 'updatedAt': in_ms},
            ],
        }))
        r2 = collect.Review(self.home, START, END)
        r2.raycast_say_in_english()
        self.assertEqual([m['text'] for m in r2.messages], ['[Raycast "Say in English" lookup] Query: 人机验证 | Suggested English: CAPTCHA'])
        self.assertEqual(r2.coverage['Raycast Say in English']['status'], 'partial')

        # Missing configured sync-path target reports partial
        sync_file.unlink()
        r3 = collect.Review(self.home, START, END)
        r3.raycast_say_in_english()
        self.assertEqual(r3.coverage['Raycast Say in English']['status'], 'partial')
    def test_antigravity_transcripts_main_sidechat_truncation_and_sidecar_filter(self):
        cfg = self.home/'.gemini/config/config.json'
        cfg.parent.mkdir(parents=True)
        cfg.write_text(json.dumps({'sidecars': {'watcher': {'projectId': 'sidecar-proj'}}}))
        sdb = self.home/'.gemini/antigravity/conversation_summaries.db'
        sdb.parent.mkdir(parents=True)
        db = sqlite3.connect(sdb)
        db.executescript('CREATE TABLE conversation_summaries(conversation_id TEXT PRIMARY KEY, nesting_depth INTEGER, project_id TEXT); CREATE TABLE conversation_parents(conversation_id TEXT PRIMARY KEY, parent_id TEXT);')
        db.executemany('INSERT INTO conversation_summaries VALUES (?,?,?)', [
            ('main-chat', 0, 'user-proj'),
            ('sidecar-chat', 0, 'sidecar-proj'),
        ])
        db.executemany('INSERT INTO conversation_parents VALUES (?,?)', [
            ('side-chat', 'main-chat'),
            ('sidecar-child', 'sidecar-chat'),
        ])
        db.commit()
        db.close()

        at = '2026-11-02T17:00:00Z'
        def write_transcript(cid, rows, full_rows=None):
            logs = self.home/f'.gemini/antigravity/brain/{cid}/.system_generated/logs'
            write_lines(logs/'transcript.jsonl', rows)
            if full_rows is not None:
                write_lines(logs/'transcript_full.jsonl', full_rows)

        long_req = '<USER_REQUEST>\nFull truncated question here.\n</USER_REQUEST>\n<ADDITIONAL_METADATA>\nignored\n</ADDITIONAL_METADATA>'
        write_transcript('main-chat', [
            {'type': 'USER_INPUT', 'source': 'USER_EXPLICIT', 'created_at': at, 'content': '<USER_REQUEST>\nWhy is this cut off?\n</USER_REQUEST>\n<ADDITIONAL_METADATA>\nmeta\n</ADDITIONAL_METADATA>'},
            {'type': 'USER_INPUT', 'source': 'USER_EXPLICIT', 'created_at': '2026-11-02T17:01:00Z', 'truncated_fields': ['content'], 'content': 'Full trunc...'},
            {'type': 'USER_INPUT', 'source': 'USER_EXPLICIT', 'created_at': '2026-11-02T15:59:59Z', 'content': '<USER_REQUEST>\nYesterday\n</USER_REQUEST>'},
        ], full_rows=[
            {'type': 'USER_INPUT', 'source': 'USER_EXPLICIT', 'created_at': at, 'content': '<USER_REQUEST>\nWhy is this cut off?\n</USER_REQUEST>'},
            {'type': 'USER_INPUT', 'source': 'USER_EXPLICIT', 'created_at': '2026-11-02T17:01:00Z', 'content': long_req},
            {'type': 'USER_INPUT', 'source': 'USER_EXPLICIT', 'created_at': '2026-11-02T15:59:59Z', 'content': '<USER_REQUEST>\nYesterday\n</USER_REQUEST>'},
        ])
        write_transcript('side-chat', [
            {'type': 'USER_INPUT', 'source': 'USER_EXPLICIT', 'created_at': '2026-11-02T17:02:00Z', 'content': '<USER_REQUEST>\nSide chat question.\n</USER_REQUEST>'},
        ])
        write_transcript('subagent-chat', [
            {'type': 'SYSTEM_MESSAGE', 'source': 'SYSTEM', 'created_at': at, 'content': 'Subagent prompt'},
        ])
        write_transcript('sidecar-chat', [
            {'type': 'USER_INPUT', 'source': 'USER_EXPLICIT', 'created_at': at, 'content': '<USER_REQUEST>\nSidecar prompt.\n</USER_REQUEST>'},
        ])
        write_transcript('sidecar-child', [
            {'type': 'USER_INPUT', 'source': 'USER_EXPLICIT', 'created_at': at, 'content': '<USER_REQUEST>\nSidecar child prompt.\n</USER_REQUEST>'},
        ])

        self.review.antigravity()
        self.assertEqual([m['text'].strip() for m in self.review.messages], [
            'Why is this cut off?',
            'Full truncated question here.',
            'Side chat question.',
        ])
        self.assertEqual(self.review.coverage['Antigravity']['status'], 'available')
        self.assertEqual(self.review.coverage['Antigravity']['files_scanned'], 3)

if __name__ == '__main__':
    unittest.main()
