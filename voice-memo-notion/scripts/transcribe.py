#!/usr/bin/env python3
"""Chinese Voice Memos transcription. Default is a local plan; --execute uploads."""
import argparse
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
from urllib.parse import urlparse

import requests

SETTINGS_FILE = Path.home() / '.config/personal-skills/settings.json'

def owner_settings():
    if not SETTINGS_FILE.exists():
        return {}
    data = json.loads(SETTINGS_FILE.read_text())
    value = data.get('voice_memo_notion', {})
    if not isinstance(value, dict):
        raise ValueError('Invalid voice_memo_notion settings')
    return value

CONFIG = owner_settings()
ORIGIN = os.environ.get('BAILIAN_ORIGIN', CONFIG.get('origin', '')).rstrip('/')
MODEL = 'paraformer-v2'
SERVICE = CONFIG.get('keychain_service', 'voice-memo-notion.bailian')
ACCOUNT = os.environ.get('BAILIAN_KEYCHAIN_ACCOUNT', CONFIG.get('keychain_account', ''))
ROOT = Path.home() / '.local/share/voice-memo-notion/runs'
RATE = CONFIG.get('price_per_second_cny')
PRICE_CHECKED = CONFIG.get('price_checked')


def save(path, data):
    tmp = path.with_suffix(path.suffix + '.tmp')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def configured_origin():
    parsed = urlparse(ORIGIN)
    host = parsed.hostname or ''
    if (parsed.scheme != 'https' or parsed.username or parsed.password
            or parsed.path or parsed.query or parsed.fragment
            or parsed.port not in (None, 443)
            or not (host == 'dashscope.aliyuncs.com' or host.endswith('.maas.aliyuncs.com'))):
        raise RuntimeError('Configure an official HTTPS Bailian API origin before execution; no audio uploaded.')
    return ORIGIN


def keychain_key():
    value = os.environ.get('DASHSCOPE_API_KEY', '').strip()
    if value:
        return value
    if not ACCOUNT:
        raise RuntimeError('Configure the Keychain account or DASHSCOPE_API_KEY privately; no audio uploaded.')
    result = subprocess.run(['/usr/bin/security', 'find-generic-password',
                             '-s', SERVICE, '-a', ACCOUNT, '-w'], capture_output=True)
    if result.returncode:
        raise RuntimeError('Bailian credential unavailable. Configure the workflow Keychain item privately; no audio uploaded.')
    return result.stdout.decode().strip()


def store_clipboard_key():
    if not ACCOUNT:
        raise RuntimeError('Configure the intended Keychain account before storing a key.')
    try:
        result = subprocess.run(['/usr/bin/pbpaste'], capture_output=True, check=True)
        value = result.stdout.decode().strip()
        if not value.startswith('sk-') or any(c.isspace() for c in value):
            raise RuntimeError('Clipboard does not contain a single API key.')
        # Feed the interactive command over stdin, never put the secret in argv.
        command = 'add-generic-password -U -s {} -a {} -w {}\n'.format(
            shlex.quote(SERVICE), shlex.quote(ACCOUNT), shlex.quote(value))
        result = subprocess.run(['/usr/bin/security', '-i'], input=command.encode(), capture_output=True)
        if result.returncode:
            raise RuntimeError('Keychain write failed; complete any macOS authorization prompt and retry.')
        if keychain_key() != value:
            raise RuntimeError('Keychain readback did not match.')
        print('Credential stored and read back from macOS Keychain. Secret omitted.')
    finally:
        subprocess.run(['/usr/bin/pbcopy'], input=b'', check=False)


def checked(response):
    if not response.ok:
        raise RuntimeError(f'Bailian HTTP {response.status_code}; state retained. No automatic resubmission.')
    return response.json()


def official(url):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or not (parsed.hostname or '').endswith('.aliyuncs.com'):
        raise RuntimeError('Unexpected upload/result host; stopped.')
    return url


def redact(value):
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items()
                if k not in {'file_url', 'file_urls', 'audio_url', 'transcription_url', 'upload_url'}}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


def stamp(value):
    return f'{int(value)//60:02}:{value%60:05.2f}'


def write_result(folder, plan, state, raw, metadata):
    turns = [{'start':s['begin_time']/1000 + plan['start_seconds'],
              'end':s['end_time']/1000 + plan['start_seconds'],
              'speaker':str(s.get('speaker_id', 'unknown')), 'text':s['text']}
             for t in raw.get('transcripts', []) for s in t.get('sentences', [])]
    if not turns:
        raise RuntimeError('Provider returned no timed speech; inspect the task before creating meeting notes.')
    if any(u['end'] < u['start'] or u['start'] < plan['start_seconds'] - 1 or
           u['end'] > plan['start_seconds'] + plan['duration_seconds'] + 2 for u in turns):
        raise RuntimeError('Provider timestamps fall outside the selected audio.')
    usage = raw.get('usage', {}).get('duration')
    if usage is None:
        durations = [r.get('usage', {}).get('duration') for r in metadata.get('results', [])]
        if durations and all(isinstance(d, (int, float)) for d in durations):
            usage = sum(durations)
    report = {'plan': plan, 'job_id': state['job_id'], 'status':'completed',
              'utterances':turns, 'speaker_clusters':len({u['speaker'] for u in turns}),
              'raw_result':redact(raw), 'provider_task_metadata':redact(metadata),
              'provider_usage_seconds':usage,
              'usage_list_price_cny':round(usage * RATE, 6) if isinstance(usage, (int, float)) and isinstance(RATE, (int, float)) else None,
              'actual_cash_cost_cny':None, 'invoice_amount_verified':False,
              'manual_accuracy_verified':False}
    save(folder / 'result.json', report)
    lines = [f"{plan['title']} | {MODEL} | 自动转写，未经人工核听", '',
             '时间戳对应原始录音；说话人编号仅代表本段录音的匿名聚类。', '']
    lines += [f"[{stamp(u['start'])}–{stamp(u['end'])}] 说话人 {u['speaker']}: {u['text']}" for u in turns]
    target = folder / 'transcript.txt'
    target.write_text('\n'.join(lines) + '\n')
    target.chmod(0o600)


def run(args):
    source = Path(args.input).expanduser().resolve(strict=True)
    probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                            '-of', 'json', str(source)], capture_output=True, check=True)
    total = float(json.loads(probe.stdout)['format']['duration'])
    duration = total - args.start if args.duration is None else args.duration
    if not all(math.isfinite(v) for v in [total, args.start, duration]) or args.start < 0 or duration <= 0 or args.start + duration > total + .05:
        raise RuntimeError('Invalid selected audio interval.')
    fingerprint = sha(source)
    identity = {'source_sha256':fingerprint, 'start_seconds':args.start,
                'duration_seconds':duration, 'model':MODEL,
                'language_hints':['zh'], 'diarization_enabled':True}
    run_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
    folder = ROOT / run_id
    plan = {**identity, 'run_id':run_id, 'title':args.title or source.stem,
            'memo_id':args.memo_id, 'recorded_at':args.recorded_at,
            'estimated_max_list_price_cny':round(math.ceil(duration) * RATE, 6) if isinstance(RATE, (int, float)) else None,
            'price_checked':PRICE_CHECKED,
            'price_source':'https://help.aliyun.com/zh/model-studio/model-pricing',
            'result_path':str(folder / 'result.json'),
            'transcript_path':str(folder / 'transcript.txt')}
    if not args.execute:
        print(json.dumps({'plan':plan, 'cached':(folder/'result.json').exists(),
                          'uploads_performed':0}, ensure_ascii=False, indent=2))
        return
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    folder.chmod(0o700)
    with (folder / 'run.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('This recording is already being processed by another run.')
        state_path = folder / 'state.json'
        state = json.loads(state_path.read_text()) if state_path.exists() else {'phase':'new', 'plan':plan}
        if state['plan']['run_id'] != run_id:
            raise RuntimeError('Run state mismatch.')
        plan = state['plan']
        if state['phase'] == 'complete':
            print(json.dumps({'status':'cached', 'result_path':plan['result_path'],
                              'transcript_path':plan['transcript_path'], 'new_jobs':0})); return
        if state['phase'] in {'submitting', 'failed', 'rejected'} and not state.get('job_id'):
            raise RuntimeError('Previous submission is failed or unknown. Reconcile the provider console; no new task created.')
        if state['phase'] == 'failed':
            raise RuntimeError('Task failed. Review the saved task in the console before starting another task.')
        configured_origin()
        key = keychain_key()
        headers = {'Authorization':f'Bearer {key}'}
        session = requests.Session()
        if not state.get('job_id'):
            audio = folder / 'audio.wav'
            if not audio.exists():
                temp = folder / 'audio.tmp.wav'
                subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-ss', str(args.start),
                                '-i', str(source), '-t', str(duration), '-map', '0:a:0',
                                '-ar', '16000', '-ac', '1', '-c:a', 'pcm_s16le', str(temp)],
                               capture_output=True, check=True)
                temp.chmod(0o600); os.replace(temp, audio)
            policy = checked(session.get(ORIGIN+'/api/v1/uploads', headers=headers,
                             params={'action':'getPolicy', 'model':MODEL}, timeout=30))['data']
            official(policy['upload_host'])
            if policy['x_oss_object_acl'] != 'private':
                raise RuntimeError('Upload policy is not private.')
            object_key = policy['upload_dir'] + '/' + run_id + '.wav'
            fields = {name:(None, policy[field]) for name,field in [
                ('OSSAccessKeyId','oss_access_key_id'), ('Signature','signature'),
                ('policy','policy'), ('x-oss-object-acl','x_oss_object_acl'),
                ('x-oss-forbid-overwrite','x_oss_forbid_overwrite')]}
            fields.update({'key':(None,object_key), 'success_action_status':(None,'200')})
            with audio.open('rb') as stream:
                response = session.post(policy['upload_host'],
                    files={**fields, 'file':(run_id+'.wav',stream,'audio/wav')}, timeout=(120,120))
            if response.status_code != 200:
                raise RuntimeError(f'Private upload failed: HTTP {response.status_code}.')
            state.update({'phase':'submitting', 'submitted_at_unix':time.time()})
            save(state_path, state)  # Persist before the billable request, including unknown outcomes.
            payload = {'model':MODEL, 'input':{'file_urls':['oss://'+object_key]},
                       'parameters':{'channel_id':[0], 'language_hints':['zh'],
                                     'diarization_enabled':True, 'disfluency_removal_enabled':False}}
            response = session.post(ORIGIN+'/api/v1/services/audio/asr/transcription',
                headers={**headers, 'X-DashScope-Async':'enable', 'X-DashScope-OssResourceResolve':'enable'},
                json=payload, timeout=45)
            if 400 <= response.status_code < 500:
                state['phase']='rejected'; save(state_path,state)
            submitted = checked(response)
            state.update({'phase':'submitted', 'job_id':submitted['output']['task_id']})
            save(state_path,state)
            audio.unlink()  # The source recording is untouched.
        deadline = time.monotonic() + args.poll_seconds
        while True:
            data = checked(session.get(ORIGIN+'/api/v1/tasks/'+state['job_id'], headers=headers, timeout=30))
            status = data['output']['task_status']
            if status in {'FAILED','CANCELED'}:
                state.update({'phase':'failed', 'provider_status':status}); save(state_path,state)
                raise RuntimeError('Transcription failed; saved the task ID without resubmitting.')
            if status == 'SUCCEEDED':
                results = data['output']['results']
                if len(results) != 1 or results[0]['subtask_status'] != 'SUCCEEDED':
                    raise RuntimeError('Unexpected transcription subtask result; state retained.')
                raw = checked(session.get(official(results[0]['transcription_url']), timeout=30))
                write_result(folder,plan,state,raw,data['output'])
                state.update({'phase':'complete', 'completed_at_unix':time.time()}); save(state_path,state)
                print(json.dumps({'status':'completed', 'result_path':plan['result_path'],
                                  'transcript_path':plan['transcript_path'], 'job_id':state['job_id']})); return
            if time.monotonic() >= deadline:
                print(json.dumps({'status':'pending', 'job_id':state['job_id'],
                                  'resume':'Rerun the identical command; it polls this same task.'})); return
            time.sleep(min(5, max(0,deadline-time.monotonic())))


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input')
    parser.add_argument('--title')
    parser.add_argument('--memo-id',type=int)
    parser.add_argument('--recorded-at')
    parser.add_argument('--start',type=float,default=0)
    parser.add_argument('--duration',type=float)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--poll-seconds',type=float,default=45)
    parser.add_argument('--store-key-from-clipboard',action='store_true')
    parser.add_argument('--check-credential',action='store_true')
    args=parser.parse_args()
    try:
        if args.store_key_from_clipboard:
            store_clipboard_key(); return
        if args.check_credential:
            keychain_key(); print('Credential available; value omitted.'); return
        if not args.input:
            parser.error('--input is required for planning/transcription')
        if not math.isfinite(args.poll_seconds) or not 0 <= args.poll_seconds <= 55:
            parser.error('--poll-seconds must be between 0 and 55')
        run(args)
    except (RuntimeError, OSError, ValueError, KeyError, requests.RequestException, subprocess.SubprocessError) as error:
        if isinstance(error, RuntimeError):
            print(str(error),file=sys.stderr)
        else:
            print('Processing failed. Local state retained; inspect locally without exposing credentials or signed URLs.',file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
