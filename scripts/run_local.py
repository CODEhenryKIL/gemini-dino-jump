#!/usr/bin/env python3
"""Start the local API/static server with literal, untracked .env.local values."""
import os
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
env_file = root / '.env.local'
if not env_file.exists():
    raise SystemExit('Copy .env.example to .env.local and provision the local PostgreSQL database first.')
for line in env_file.read_text().splitlines():
    if not line.strip() or line.lstrip().startswith('#'):
        continue
    key, separator, value = line.partition('=')
    if not separator or not re.fullmatch(r'[A-Z][A-Z0-9_]*', key.strip()):
        raise SystemExit('Invalid .env.local line; use literal NAME=value entries.')
    os.environ.setdefault(key.strip(), value.strip())
if os.environ.get('APP_ENV') not in ('local', 'test'):
    raise SystemExit('This runner accepts local/test only. Preview uses Vercel environment variables.')
os.execv(sys.executable, [sys.executable, str(root / 'server/app.py')])
