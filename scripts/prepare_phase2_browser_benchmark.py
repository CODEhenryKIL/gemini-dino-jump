"""Generate the local-only Phase 2 browser performance benchmark page."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "tests/fixtures/phase2-browser-benchmark.html"
DEFAULT_OUTPUT = ROOT / "public/preview-phase2-perf.html"
ENGINE_TOKEN = "__ENGINE_MODULE_URL__"
LABEL_TOKEN = "__BENCHMARK_BUILD_LABEL__"


def script_literal(value: str) -> str:
    return (
        json.dumps(value)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def local_module_url(value: str) -> str:
    if not value.startswith("/") or value.startswith("//") or any(
        marker in value for marker in ("://", "\\", "\n", "\r")
    ):
        raise argparse.ArgumentTypeError("engine URL must be a root-relative local path")
    return value


def output_path(value: str) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    candidate = candidate.resolve()
    public = (ROOT / "public").resolve()
    if candidate.parent != public or not candidate.name.startswith("preview-") or candidate.suffix != ".html":
        raise argparse.ArgumentTypeError("output must be one preview-*.html file directly under public/")
    return candidate


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=output_path, default=DEFAULT_OUTPUT)
    parser.add_argument("--engine-url", type=local_module_url, default="/js/game/engine.js")
    parser.add_argument("--label", default="current-worktree", help="Label embedded in the JSON result")
    args = parser.parse_args()

    template = TEMPLATE.read_text(encoding="utf-8")
    if template.count(ENGINE_TOKEN) != 1 or template.count(LABEL_TOKEN) != 1:
        raise RuntimeError("benchmark template placeholders are missing or duplicated")
    rendered = template.replace(ENGINE_TOKEN, script_literal(args.engine_url))
    rendered = rendered.replace(LABEL_TOKEN, script_literal(str(args.label)[:120]))
    args.output.write_text(rendered, encoding="utf-8")
    print(args.output.relative_to(ROOT))


if __name__ == "__main__":
    main()
