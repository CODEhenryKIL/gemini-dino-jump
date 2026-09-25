#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/python ]]; then
  echo "Python 환경이 없습니다. README의 로컬 실행 준비를 먼저 완료해 주세요." >&2
  exit 1
fi
exec .venv/bin/python scripts/run_local.py
