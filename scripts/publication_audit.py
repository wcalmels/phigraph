from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {'.git', '.venv', 'dist', 'build'}
PATTERNS = {
    'private_key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'openai_key': re.compile(r'\bsk-[A-Za-z0-9_-]{20,}\b'),
    'github_token': re.compile(r'\bgh[pousr]_[A-Za-z0-9]{20,}\b'),
    'aws_access_key': re.compile(r'\bAKIA[0-9A-Z]{16}\b'),
}

findings: list[str] = []
for path in ROOT.rglob('*'):
    if not path.is_file() or any(part in EXCLUDED for part in path.parts):
        continue
    if path.suffix.lower() in {'.png','.jpg','.jpeg','.gif','.pdf','.whl','.gz','.zip','.graphml'}:
        continue
    try:
        text = path.read_text(encoding='utf-8', errors='ignore')
    except OSError:
        continue
    for name, pattern in PATTERNS.items():
        if pattern.search(text):
            findings.append(f'{name}: {path.relative_to(ROOT)}')

for forbidden in ['data/phigraph.db', '.env']:
    if (ROOT/forbidden).exists():
        findings.append(f'forbidden_file: {forbidden}')

if findings:
    print('Publication audit failed:')
    print('\n'.join(f'- {item}' for item in findings))
    sys.exit(1)
print('Publication audit passed.')
