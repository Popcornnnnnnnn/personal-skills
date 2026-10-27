#!/usr/bin/env python3
"""Local, model-free power lease and failure receipts. Never forces system sleep."""
import argparse
from datetime import datetime, timedelta
import fcntl
import json
import os
from pathlib import Path
import subprocess
from zoneinfo import ZoneInfo
from state import nonblocking_unavailable

TZ = ZoneInfo('Asia/Shanghai')
ROOT = Path.home() / 'Library/Application Support/saved-content-review'


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temp.chmod(0o600)
    os.replace(temp, path)


def command(args):
    return subprocess.run(args, capture_output=True, text=True, timeout=15)


def amph(script):
    result = command(['/usr/bin/osascript', '-e', 'tell application "Amphetamine" to ' + script])
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    return result.stdout.strip()


def health(data, instant, root):
    """Only describes receipts. It never claims independent remote verification."""
    day = instant.date().isoformat()
    runs = sorted([r for r in data.get('runs', {}).values()
                   if r.get('date') == day and r.get('kind') in ('collect', 'repair')],
                  key=lambda r: r['started_at'])
    result = {'date': day, 'observed_at': instant.isoformat(), 'model_used': False,
              'remote_verification': False, 'channels': {}, 'issues': [], 'notices': [],
              'run_ids': [r['id'] for r in runs]}
    if not runs:
        result['state'] = 'not_started' if instant.hour < 4 else 'missing_run'
        result['issues'].append('No collection run receipt; this does not mean empty sources.')
    else:
        latest = runs[-1]
        observations = dict(latest.get('platforms', {}))
        for audit in latest.get('audits', []):
            for name, snapshot in audit.get('channel_observations', {}).items():
                original = observations.get(name, {})
                if (nonblocking_unavailable(snapshot)
                        and all(snapshot.get(k) == original.get(k) for k in
                                ('account', 'displayed_total', 'accessible_count', 'pagination_complete', 'coverage_complete'))):
                    observations[name] = snapshot
        unavailable = nonblocking_unavailable(observations.get('xhs', {}))
        delivered = (bool(latest.get('brief_url')) and latest.get('brief_date') == day
                     and latest.get('brief_delivered') is not False)
        trigger = {}
        try:
            trigger_path = root / 'runs' / latest['id'] / 'trigger.json'
            if trigger_path.is_file():
                trigger = json.loads(trigger_path.read_text())
        except (OSError, ValueError):
            result['issues'].append('Unreadable original trigger receipt')
        result['execution'] = {k: latest.get(k) for k in
                               ('id', 'scheduled_for', 'started_at', 'finished_at', 'status', 'outcome')}
        result['execution'].update({k: trigger.get(k) for k in ('actual_trigger_iso', 'actual_trigger_beijing', 'late_seconds')})
        result['delivery'] = {'date': latest.get('brief_date', day), 'delivered': delivered,
                              'status': 'delivered' if delivered else 'pending',
                              'url': latest.get('brief_url'), 'checked_at': latest.get('brief_updated_at'),
                              'receipt_path': latest.get('brief_delivery_path'),
                              'draft_path': latest.get('brief_report_path')}
        elapsed = instant - datetime.fromisoformat(latest['started_at'])
        result['state'] = ('interrupted' if elapsed >= timedelta(minutes=90) else 'running') if latest['status'] == 'running' else latest['status']
        result['failure_history'] = [
            {'run_id': run['id'], 'blocker': blocker}
            for run in runs for blocker in run.get('blockers', [])]
        for entry in result['failure_history']:
            blocker = entry['blocker']
            kind = blocker.get('type') if isinstance(blocker, dict) else None
            if unavailable and (kind == 'xhs_unidentified_count_gap' or
                                (kind == 'phone_start_failure' and blocker.get('stage') == 'xhs_mobile_inventory')):
                result['notices'].append({'historical_blocker': blocker, 'disposition': 'nonblocking_content_unavailable'})
                continue
            if delivered and kind == 'same_date_daily_page_not_yet_present':
                continue  # The original failure remains in failure_history.
            key = blocker.get('key') if isinstance(blocker, dict) else None
            current = data.get('items', {}).get(key, {}) if key else {}
            if current.get('status') not in ('complete', 'discarded'):
                result['issues'].append(blocker)
        for name in ('xhs', 'douyin', 'bilibili'):
            evidence = next((r.get('coverage', {}).get(name) for r in reversed(runs)
                             if isinstance(r.get('coverage', {}).get(name), dict)), None)
            result['channels'][name] = {'state': 'receipt_present' if evidence is not None else 'unverified', 'coverage': evidence}
            snapshot = observations.get(name, evidence or {})
            result['channels'][name]['result'] = ('unavailable' if nonblocking_unavailable(snapshot) else
                'success' if (evidence or {}).get('coverage_complete') is True else
                'failed' if evidence is not None else 'unverified')
            if nonblocking_unavailable(snapshot):
                result['channels'][name]['visibility'] = snapshot['visibility']
        manifests = []
        for run in runs:
            path = root / 'runs' / run['id'] / 'voice-memos.json'
            if path.exists():
                try:
                    manifests.append(json.loads(path.read_text()))
                except (OSError, ValueError):
                    result['issues'].append('Unreadable Voice Memos manifest: ' + run['id'])
        result['channels']['voice_memos'] = {'state': 'receipt_present' if manifests else 'unverified', 'manifests': manifests,
            'result': 'success' if manifests and all(m.get('coverage_complete') is True and
                all(i.get('status') == 'complete' for i in m.get('outcomes', [])) for m in manifests) else 'unverified'}
        for name, channel in result['channels'].items():
            if channel['state'] == 'unverified':
                result['issues'].append(name + ': no structured coverage receipt')
            c = channel.get('coverage') or {}
            if c.get('pagination_complete') is False or c.get('coverage_complete') is False or c.get('unknown_count', 0):
                if name == 'xhs' and unavailable:
                    result['notices'].append('xhs: content unavailable, cause unconfirmed; coverage remains incomplete; no phone retry required')
                else:
                    result['issues'].append(name + ': incomplete coverage')
        for manifest in manifests:
            if manifest.get('coverage_complete') is not True:
                result['issues'].append('voice_memos: coverage not confirmed')
            for item in manifest.get('outcomes', []):
                if item.get('status') != 'complete':
                    result['issues'].append({'channel': 'voice_memos', **item})
        result['counts'] = dict(latest.get('counts', {}))
        result['counts']['brief_delivered'] = delivered
        result['brief_url'] = latest.get('brief_url')
        if result['state'] == 'finished' and not delivered:
            result['issues'].append('No verified daily report delivery receipt')
    result['attention'] = bool(result['issues']) or result['state'] in ('missing_run', 'interrupted')
    return result


def write_health(root, result):
    directory = root / 'health' / result['date']
    atomic(directory / 'status.json', result)
    lines = [f"# 夜间任务状态 · {result['date']}", '',
             f"状态：{result['state']}；检查时间：{result['observed_at']}",
             '由本机代码读取回执生成，未调用模型，未重新检查远端内容。', '', '## 失败与未完成事项', '']
    lines += ['- ' + (i if isinstance(i, str) else json.dumps(i, ensure_ascii=False)) for i in result['issues']]
    if not result['issues']:
        lines += ['- 无已记录异常；这不等于独立审计通过。']
    lines += ['', '## 渠道回执', '']
    lines += [f"- {name}: {value['state']} / {value.get('result', 'unverified')}" for name, value in result['channels'].items()]
    lines += ['', '## 非阻塞说明', ''] + ['- ' + (n if isinstance(n, str) else json.dumps(n, ensure_ascii=False))
                                        for n in result.get('notices', [])]
    for key in ('execution', 'counts', 'delivery'):
        if key in result:
            lines += ['', '## ' + key, '', json.dumps(result[key], ensure_ascii=False)]
    lines += ['', '原始状态：status.json；来源未确认或未处理时保留，白天可手动接续。', '']
    (directory / 'report.md').write_text('\n'.join(lines))
    (root / 'health' / 'latest.md').write_text('\n'.join(lines))
    atomic(root / 'health' / 'latest.json', result)


def release(power, instant):
    # End only our unchanged finite session. A user-created replacement stays alone.
    if power.get('amphetamine_owned'):
        try:
            remaining = int(amph('get session time remaining'))
            expected = (datetime.fromisoformat(power['deadline']) - instant).total_seconds()
            if remaining > 0 and abs(remaining - expected) < 15:
                amph('end session')
            else:
                power['release_note'] = 'Session expired or changed; left untouched.'
        except (RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
            power['release_error'] = str(error)
    power['released_at'] = instant.isoformat()


def tick(root, instant):
    directory = root / 'health'
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / 'watch.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        day = instant.date().isoformat()
        minute = instant.hour * 60 + instant.minute
        power_path = directory / 'power.json'
        power = json.loads(power_path.read_text()) if power_path.exists() else {}
        if power and power.get('date') != day and not power.get('released_at'):
            release(power, instant)
            atomic(directory / (power['date'] + '-power.json'), power)
            power = {}
        if 230 <= minute < 260 and power.get('date') != day:
            deadline = instant.replace(hour=5, minute=40, second=0, microsecond=0)
            seconds = int((deadline - instant).total_seconds())
            power = {'date': day, 'started_at': instant.isoformat(), 'deadline': deadline.isoformat()}
            try:
                # Do not replace a session that belongs to the user or another task.
                if amph('get session is active') == 'false':
                    duration = max(1, (seconds + 59) // 60)
                    amph('start new session with options {duration:' + str(duration) + ', interval:minutes, displaySleepAllowed:true}')
                    power['amphetamine_owned'] = True
                    power['deadline'] = (instant + timedelta(minutes=duration)).isoformat()
                else:
                    power['preexisting_session'] = True
            except (RuntimeError, subprocess.TimeoutExpired) as error:
                power['power_error'] = str(error)
            atomic(power_path, power)
        # Outside the nightly window, this job never starts collection or prevents sleep.
        if minute < 230:
            return
        try:
            data = json.loads((root / 'state.json').read_text())
            result = health(data, instant, root)
        except (OSError, ValueError, KeyError, TypeError) as error:
            result = {'date': day, 'observed_at': instant.isoformat(), 'model_used': False,
                      'state': 'ledger_error', 'channels': {}, 'attention': True, 'issues': [str(error)]}
        if power.get('date') == day and power.get('power_error'):
            result['issues'].append({'power_error': power['power_error']})
            result['attention'] = True
        write_health(root, result)
        done = result['state'] == 'finished' or minute >= 340 or (minute >= 260 and result['state'] == 'missing_run')
        if power.get('date') == day and not power.get('released_at') and done:
            release(power, instant)
            atomic(power_path, power)
        # StartInterval does not wake a sleeping Mac: report at/after 08:00 on next awake tick.
        notice = directory / day / 'notified.json'
        if minute >= 480 and result['attention'] and not notice.exists():
            message = '有失败、未启动或待确认项；原来源已保留。查看夜间任务状态报告。'
            receipt = {'at': instant.isoformat(), 'delivery_confirmed': False,
                       'report_path': str(directory / day / 'report.md')}
            try:
                response = command(['/usr/bin/osascript', '-e', 'display notification ' + json.dumps(message, ensure_ascii=False) + ' with title "夜间任务未完成"'])
                receipt['requested'] = response.returncode == 0
                if response.returncode:
                    receipt['error'] = response.stderr.strip()
            except (OSError, subprocess.TimeoutExpired) as error:
                receipt.update(requested=False, error=str(error))
            atomic(notice, receipt)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--render-only', action='store_true')
    args = parser.parse_args()
    instant = datetime.now(TZ)
    if args.render_only:
        result = health(json.loads((args.root / 'state.json').read_text()), instant, args.root)
        write_health(args.root, result)
        print(json.dumps(result, ensure_ascii=False))
    else:
        tick(args.root, instant)


if __name__ == '__main__':
    try:
        main()
    except BlockingIOError:
        pass
