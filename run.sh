#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
runtime="${DINO_PYTHON:-.venv/bin/python}"
if [[ ! -x "$runtime" ]]; then
  echo 'Python 3.12 가상환경이 필요합니다. README의 로컬 실행 절차를 확인하세요.' >&2
  exit 1
fi
exec "$runtime" scripts/run_local.py "$@"
