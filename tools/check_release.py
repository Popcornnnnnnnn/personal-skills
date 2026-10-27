#!/usr/bin/env python3
"""Check a skill release tree; this does not sanitize remote Git history."""
from pathlib import Path
import re
import subprocess
import sys

PATTERNS = {
    'machine-specific home': re.compile(r'/Users/[A-Za-z0-9_.-]+/'),
    'Slack routing ID': re.compile(r'\b[TDWU][0-9][A-Z0-9]{7,}\b'),
    'private Notion destination': re.compile(r'https://(?:app\.)?notion\.(?:com|so)/(?:p/)?[0-9a-f-]{32,}'),
    'account-specific ASR endpoint': re.compile(r'https://ws-[a-z0-9]+\.cn-[a-z0-9-]+\.maas\.aliyuncs\.com'),
}
MANUAL_ONLY = {'agent-browser', 'mac-app-replacement', 'notion-trash', 'tell-dot', 'ui-preferences'}
SKIP = {'.git', '.local', '__pycache__', 'node_modules', '.venv'}


def release_files(root):
    if (root / '.git').exists():
        result = subprocess.run(['git', 'ls-files', '--cached', '--others', '--exclude-standard'], cwd=root, capture_output=True, text=True, check=True)
        paths = [root / item for item in result.stdout.splitlines()]
    else:
        paths = list(root.rglob('*'))
    return sorted({p for p in paths if p.is_file() and not p.is_symlink()
                   and not any(part in SKIP for part in p.relative_to(root).parts)
                   and '.bak' not in p.name and p.suffix not in {'.pyc', '.pyo'}})


def check(root):
    errors = []
    files = release_files(root)
    skills = sorted(p for p in files if p.name == 'SKILL.md' and len(p.relative_to(root).parts) == 2)
    if not skills:
        errors.append('No skill manifests found')
    for p in files:
        text = p.read_text(errors='replace')
        for label, pattern in PATTERNS.items():
            for i, line in enumerate(text.splitlines(), 1):
                if pattern.search(line):
                    errors.append(f'{p.relative_to(root)}:{i}: {label}')
        if p.suffix == '.md':
            for match in re.finditer(r'\]\(([^\s)]+)\)', text):
                ref = match.group(1).split('#', 1)[0]
                if not ref or '://' in ref or ref.startswith(('/', '~', 'mailto:')):
                    continue
                target = (p.parent / ref).resolve()
                if not target.is_relative_to(root.resolve()) or not target.exists():
                    errors.append(f'{p.relative_to(root)}: unresolved packaged reference: {ref}')
    for p in skills:
        name = p.parent.name
        text = p.read_text()
        if not re.match(r'---\n', text) or '\n---\n' not in text[4:]:
            errors.append(f'{name}: missing frontmatter')
            continue
        header = text.split('---', 2)[1]
        if name in MANUAL_ONLY and not re.search(r'^disable-model-invocation:\s*true\s*$', header, re.M):
            errors.append(f'{name}: existing manual-invocation restriction is missing')
        actual = re.search(r'^name:\s*([a-z0-9-]+)\s*$', header, re.M)
        description = re.search(r'^description:\s*\S.+$', header, re.M)
        if not actual or actual.group(1) != name or not description:
            errors.append(f'{name}: invalid name/description')
    if not (root / 'LICENSE').is_file():
        errors.append('Missing license')
    return errors, len(skills), len(files)


if __name__ == '__main__':
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
    errors, skills, files = check(root)
    if errors:
        print('\n'.join(errors))
        sys.exit(1)
    print(f'PASS: {skills} skill packages, {files} release files; structure, packaged references and publication indicators checked. Remote history and live behavior need separate verification.')
