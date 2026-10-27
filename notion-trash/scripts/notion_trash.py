#!/usr/bin/env python3
"""A narrow Notion Trash API helper and newline-delimited STDIO MCP server."""
import argparse
import getpass
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
import uuid

TOKEN_FILE = Path.home() / '.config/notion-trash/token'
API_VERSION = '2026-03-11'
PROTOCOLS = ('2025-11-25', '2025-06-18', '2025-03-26', '2024-11-05')


class Failure(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(message)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def page_id(value):
    if not isinstance(value, str):
        raise Failure('invalid_page', 'Supply a Notion page URL or UUID.')
    try:
        return str(uuid.UUID(value))
    except ValueError:
        try:
            parsed = urlsplit(value)
            port = parsed.port
        except ValueError:
            raise Failure('invalid_page', 'Supply a valid Notion HTTPS page URL or UUID.')
        if parsed.scheme != 'https' or not parsed.hostname or not (
            parsed.hostname in ('notion.so', 'www.notion.so', 'notion.com', 'www.notion.com', 'app.notion.com')
            or parsed.hostname.endswith('.notion.site')
        ) or parsed.username or parsed.password or port not in (None, 443):
            raise Failure('invalid_page', 'Supply a Notion HTTPS page URL or UUID.')
        match = re.search(r'([0-9a-fA-F]{32}|[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})/?$', parsed.path)
        if not match:
            raise Failure('invalid_page', 'No page UUID was found in the URL path.')
        return str(uuid.UUID(match.group(1)))


def credential():
    try:
        fd = os.open(TOKEN_FILE, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd) as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
                raise Failure('unsafe_credential_file', 'The token file must be owned by you with mode 600.')
            token = handle.read(4097).strip()
    except FileNotFoundError:
        raise Failure('setup_required', 'Run notion_trash.py setup in your own terminal. Do not paste a token into chat.')
    except OSError:
        raise Failure('unsafe_credential_file', 'Could not safely open the token file. Run setup again.')
    if not token or len(token) > 4096 or any(c.isspace() for c in token):
        raise Failure('invalid_credential', 'Run setup again with a valid Notion API token.')
    return token


def api(method, path, body=None, token=None):
    token = token if token is not None else credential()
    request = Request('https://api.notion.com/v1/' + path,
                      data=json.dumps(body).encode() if body is not None else None,
                      headers={'Authorization': 'Bearer ' + token, 'Notion-Version': API_VERSION,
                               'Content-Type': 'application/json'}, method=method)
    try:
        with build_opener(NoRedirect()).open(request, timeout=20) as response:
            result = json.loads(response.read())
            if not isinstance(result, dict):
                raise ValueError('Unexpected response')
            return result
    except HTTPError as error:
        messages = {401: 'Notion API token was rejected, expired, or revoked. Run setup again.',
                    403: 'The token or its owner lacks permission. Check Notion API capability and account access.',
                    404: 'Page unavailable. Check the UUID, resource type, workspace, and token owner permissions.',
                    429: 'Notion rate limit reached. Wait before retrying.'}
        if method == 'PATCH' and error.code >= 500:
            raise Failure('outcome_unknown', 'Notion returned a server error during the write. Inspect this page before retrying.')
        raise Failure('http_' + str(error.code), messages.get(error.code, 'Notion rejected the request (HTTP %s).' % error.code))
    except (URLError, TimeoutError, ValueError, OSError):
        if method == 'PATCH':
            raise Failure('outcome_unknown', 'The write response was not received. Inspect this page before retrying.')
        raise Failure('read_failed', 'Could not read Notion. Check connectivity and try again.')


def snapshot(page):
    if page.get('object') != 'page' or not isinstance(page.get('in_trash'), bool):
        raise Failure('unexpected_response', 'Notion did not return a page with a trash status.')
    title = next((v.get('title', []) for v in page.get('properties', {}).values() if v.get('type') == 'title'), [])
    return {'page_id': page['id'], 'title': ''.join(item.get('plain_text', '') for item in title),
            'url': page.get('url'), 'in_trash': page['in_trash'],
            'last_edited_time': page.get('last_edited_time'), 'parent': page.get('parent')}


def inspect(value):
    return snapshot(api('GET', 'pages/' + page_id(value)))


def change(value, title, edited_at, target):
    if not isinstance(title, str) or not isinstance(edited_at, str) or not edited_at:
        raise Failure('guard_required', 'Pass the exact title and last_edited_time returned by inspect.')
    identifier = page_id(value)
    before = inspect(identifier)
    if before['title'] != title or before['last_edited_time'] != edited_at:
        raise Failure('page_changed', 'Page title or edit timestamp changed. Inspect again and reassess the target.')
    changed = before['in_trash'] != target
    if changed and not target and (before.get('parent') or {}).get('type') == 'workspace':
        raise Failure('restore_in_notion', 'Notion API cannot restore workspace-level pages. Use the Notion page Restore button.')
    if changed:
        api('PATCH', 'pages/' + identifier, {'in_trash': target})
    try:
        after = inspect(identifier)
    except Failure:
        raise Failure('outcome_unknown', 'Could not verify the final state. Inspect this page before retrying.')
    if after['in_trash'] != target:
        raise Failure('outcome_unknown', 'Final trash status did not match the requested state. Inspect before retrying.')
    return {**after, 'changed': changed, 'verified': True}


def setup():
    if not sys.stdin.isatty():
        raise Failure('terminal_required', 'Run setup in your own interactive terminal; input is hidden.')
    print('Create a personal access token: https://app.notion.com/developers/tokens')
    print('Enable Notion API, disable Workers, and note the expiration. No per-page bot sharing is needed.')
    token = getpass.getpass('Personal access token (hidden): ').strip()
    if not token or len(token) > 4096 or any(c.isspace() for c in token):
        raise Failure('invalid_credential', 'The token is empty or malformed. Nothing was saved.')
    api('GET', 'users/me', token=token)
    directory = TOKEN_FILE.parent
    if directory.is_symlink():
        raise Failure('unsafe_credential_directory', 'The credential directory must not be a symbolic link.')
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if directory.stat().st_uid != os.getuid():
        raise Failure('unsafe_credential_directory', 'The credential directory must be owned by you.')
    directory.chmod(0o700)
    fd, temporary = tempfile.mkstemp(dir=directory, prefix='.token-')
    try:
        with os.fdopen(fd, 'w') as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(token + '\n')
        os.replace(temporary, TOKEN_FILE)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return {'credential_validated': True, 'saved': True, 'next_step': 'Inspect a page your account can access to verify access.'}


def tools_list():
    basic = {'page': {'type': 'string', 'description': 'Exact Notion page URL or UUID identified by the user.'}}
    guards = {'expected_title': {'type': 'string', 'description': 'Exact title returned by inspect_page.'},
              'expected_edited_at': {'type': 'string', 'description': 'last_edited_time returned by inspect_page.'}}
    return [
        {'name': 'inspect_page', 'description': 'Read page identity and trash status before trashing or restoring a Notion page.',
         'inputSchema': {'type': 'object', 'properties': basic, 'required': ['page'], 'additionalProperties': False},
         'annotations': {'readOnlyHint': True, 'openWorldHint': True}},
        *[{'name': name, 'description': description,
           'inputSchema': {'type': 'object', 'properties': {**basic, **guards},
                           'required': ['page', 'expected_title', 'expected_edited_at'], 'additionalProperties': False},
           'annotations': {'readOnlyHint': False, 'destructiveHint': destructive, 'idempotentHint': True, 'openWorldHint': True}}
          for name, description, destructive in [
              ('trash_page', 'Move an explicitly selected Notion page to Trash. Nested pages are affected too. Verify final state; never permanently delete.', True),
              ('restore_page', 'Restore an explicitly selected nested Notion page or database row from Trash and verify. Workspace-level pages require the Notion UI.', False)]]]


def call_tool(name, args):
    allowed = {'page'} if name == 'inspect_page' else {'page', 'expected_title', 'expected_edited_at'}
    if name not in ('inspect_page', 'trash_page', 'restore_page'):
        raise Failure('unknown_tool', 'Unknown tool.')
    if not isinstance(args, dict) or set(args) != allowed:
        raise Failure('invalid_arguments', 'Supply exactly the required tool arguments.')
    if name == 'inspect_page':
        return inspect(args['page'])
    return change(args['page'], args['expected_title'], args['expected_edited_at'], name == 'trash_page')


def serve():
    for line in sys.stdin:
        try:
            message = json.loads(line)
        except ValueError:
            print(json.dumps({'jsonrpc': '2.0', 'id': None, 'error': {'code': -32700, 'message': 'Invalid JSON'}}), flush=True)
            continue
        if not isinstance(message, dict):
            print(json.dumps({'jsonrpc': '2.0', 'id': None, 'error': {'code': -32600, 'message': 'Invalid request'}}), flush=True)
            continue
        if 'id' not in message:
            continue
        reply = {'jsonrpc': '2.0', 'id': message['id']}
        method, params = message.get('method'), message.get('params', {})
        try:
            if not isinstance(params, dict):
                raise Failure('invalid_params', 'Parameters must be an object.')
            if method == 'initialize':
                version = params.get('protocolVersion')
                reply['result'] = {'protocolVersion': version if version in PROTOCOLS else PROTOCOLS[0],
                                   'capabilities': {'tools': {}}, 'serverInfo': {'name': 'notion-trash', 'version': '1.0.0'},
                                   'instructions': 'Only trash or restore pages the user explicitly selected. Inspect first; pass exact title and edit timestamp. Trashing a parent affects nested pages. No permanent deletion. On outcome_unknown inspect before retrying. Missing credential: ask user to run notion_trash.py setup locally; never ask for tokens in chat.'}
            elif method == 'ping':
                reply['result'] = {}
            elif method == 'tools/list':
                reply['result'] = {'tools': tools_list()}
            elif method == 'tools/call':
                result = call_tool(params.get('name'), params.get('arguments', {}))
                reply['result'] = {'content': [{'type': 'text', 'text': json.dumps(result, ensure_ascii=False)}], 'isError': False}
            else:
                reply['error'] = {'code': -32601, 'message': 'Method not found'}
        except Failure as error:
            if method == 'tools/call':
                reply['result'] = {'content': [{'type': 'text', 'text': json.dumps({'error': error.code, 'message': error.message})}], 'isError': True}
            else:
                reply['error'] = {'code': -32602, 'message': error.message}
        except Exception:
            reply['error'] = {'code': -32603, 'message': 'Internal error; no credentials are included in errors.'}
        print(json.dumps(reply, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description='Inspect, trash, or restore explicitly selected Notion pages. Never permanently deletes.',
                                     epilog='Examples: notion_trash.py setup; notion_trash.py inspect PAGE_URL; notion_trash.py serve. Token: ~/.config/notion-trash/token (mode 600). Network timeout: 20 seconds per request. Setup hides input; there are no interactive commands in serve mode.')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('setup', help='Validate and save a personal access token from a hidden terminal prompt.')
    sub.add_parser('serve', help='Run the STDIO MCP server.')
    for command in ('inspect', 'trash', 'restore'):
        child = sub.add_parser(command, help=command.capitalize() + ' one Notion page.')
        child.add_argument('page', help='Notion page HTTPS URL or UUID.')
        if command != 'inspect':
            child.add_argument('--expected-title', required=True, help='Exact title returned by inspect.')
            child.add_argument('--expected-edited-at', required=True, help='last_edited_time returned by inspect.')
    args = parser.parse_args()
    try:
        if args.command == 'serve':
            serve()
            return
        if args.command == 'setup':
            result = setup()
        elif args.command == 'inspect':
            result = inspect(args.page)
        else:
            result = change(args.page, args.expected_title, args.expected_edited_at, args.command == 'trash')
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (Failure, KeyboardInterrupt) as error:
        value = {'error': error.code, 'message': error.message} if isinstance(error, Failure) else {'error': 'cancelled', 'message': 'Cancelled.'}
        print(json.dumps(value), file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
