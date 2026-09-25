"""Load local configuration as literal text, then run the local HTTP server."""
import argparse
import os
from pathlib import Path
import re
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]


def load_env(path):
    values = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, separator, value = line.partition("=")
        name = name.strip()
        if not separator or not re.fullmatch(r"[A-Z][A-Z0-9_]*", name):
            raise ValueError(f"Invalid environment assignment on line {number}")
        value = value.strip()
        if value.startswith(("'", '"')):
            if len(value) < 2 or value[-1] != value[0]:
                raise ValueError(f"Unclosed quote on line {number}")
            value = value[1:-1]
        if name in values:
            raise ValueError(f"Duplicate environment name on line {number}")
        values[name] = value
    for name, value in values.items():
        os.environ.setdefault(name, value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env.local")
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 12):
        parser.error("Use Python 3.12, matching .python-version and Preview.")
    if not args.env_file.is_file():
        parser.error("Local environment file is missing; start from .env.example.")
    try:
        load_env(args.env_file)
    except ValueError as exc:
        parser.error(str(exc))
    if os.environ.get("APP_ENV") not in {"local", "test"}:
        parser.error("Local launcher requires APP_ENV=local or test.")
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "server"))
    runpy.run_path(str(ROOT / "server/app.py"), run_name="__main__")


if __name__ == "__main__":
    main()
