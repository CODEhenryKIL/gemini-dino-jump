#!/usr/bin/env python3
"""One bounded Phase 3 remediation run, bound to the preserved failed run."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import phase3_load as original  # noqa: E402

PHASE = 3
PLAN_REVISION = "final-v21-remediation-v1"
PRIOR_PLAN_REVISION = original.PLAN_REVISION
GAME_VERSION = original.GAME_VERSION
MAX_API_CALLS = 7_000
MAX_CUMULATIVE_SECONDS = 390
PRIOR_API_CALLS = 462
PRIOR_CURSOR = 100
PRIOR_ACTUAL_SECONDS = 11.52
PRIOR_CHARGED_SECONDS = math.ceil(PRIOR_ACTUAL_SECONDS)
THINK_TIME_SECONDS = 50.0
RUN_OVERHEAD_SECONDS = 90
PROFILES = (
    (100, 150, False, "100-remediation"),
    (200, 30, True, "200-remediation-burst"),
)
REMEDIATION_RESERVED_SECONDS = sum(seconds + RUN_OVERHEAD_SECONDS for _, seconds, _, _ in PROFILES)
FLOW_CEILING = 500
RUNNER_CALL_CEILING = original.PREFLIGHT_CALLS + FLOW_CEILING * original.BASE_FLOW_CALLS
CUMULATIVE_CALL_CEILING = PRIOR_API_CALLS + RUNNER_CALL_CEILING
CUMULATIVE_SECONDS_CEILING = PRIOR_CHARGED_SECONDS + REMEDIATION_RESERVED_SECONDS

SafetyError = original.SafetyError
BudgetExceeded = original.BudgetExceeded


def _private_bytes(path: Path, label: str) -> bytes:
    original.base.read_private_text(path, label)
    return path.read_bytes()


def _sha(path: Path, label: str) -> str:
    return hashlib.sha256(_private_bytes(path, label)).hexdigest()


def _json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(original.base.read_private_text(path, label))
    except json.JSONDecodeError as error:
        raise SafetyError(f"Invalid {label} JSON") from error
    if not isinstance(value, dict):
        raise SafetyError(f"Invalid {label}")
    return value


def estimate() -> dict[str, Any]:
    stages = []
    flows = 0
    for virtual_users, seconds, burst, label in PROFILES:
        stage_flows = virtual_users if burst else virtual_users * math.ceil(seconds / THINK_TIME_SECONDS)
        flows += stage_flows
        stages.append({
            "label": label,
            "virtual_users": virtual_users,
            "seconds": seconds,
            "drain_seconds": RUN_OVERHEAD_SECONDS,
            "burst": burst,
            "flow_attempts_ceiling": stage_flows,
        })
    if flows != FLOW_CEILING:
        raise SafetyError("Remediation flow ceiling changed")
    return {
        "stages": stages,
        "flow_attempts_ceiling": flows,
        "new_runner_api_calls_ceiling": RUNNER_CALL_CEILING,
        "prior_api_calls": PRIOR_API_CALLS,
        "cumulative_api_calls_ceiling": CUMULATIVE_CALL_CEILING,
        "prior_actual_seconds": PRIOR_ACTUAL_SECONDS,
        "prior_charged_seconds": PRIOR_CHARGED_SECONDS,
        "new_reserved_seconds": REMEDIATION_RESERVED_SECONDS,
        "cumulative_seconds_ceiling": CUMULATIVE_SECONDS_CEILING,
        "remaining_api_calls": MAX_API_CALLS - CUMULATIVE_CALL_CEILING,
        "remaining_seconds": MAX_CUMULATIVE_SECONDS - CUMULATIVE_SECONDS_CEILING,
        "automatic_retry_calls": 0,
    }


def load_prior_evidence(report_path: Path, ledger_path: Path) -> dict[str, Any]:
    report = _json(report_path, "prior report")
    ledger = _json(ledger_path, "prior ledger")
    if (
        report.get("phase") != PHASE
        or report.get("plan_revision") != PRIOR_PLAN_REVISION
        or report.get("failure") != {"type": "SeriousFailure", "reason": "Server 5xx safety stop"}
        or report.get("actual_duration_seconds") != PRIOR_ACTUAL_SECONDS
        or report.get("budget", {}).get("admitted_api_calls") != PRIOR_API_CALLS
        or report.get("budget", {}).get("completed_api_calls") != PRIOR_API_CALLS
        or report.get("budget", {}).get("duration_reserved_seconds") != 390
        or report.get("metrics", {}).get("api_calls") != 460
        or report.get("stages") != []
    ):
        raise SafetyError("Prior failed report does not match the reviewed remediation baseline")
    fingerprint = report.get("cohort_fingerprint")
    state = ledger.get("cohorts", {}).get(fingerprint)
    runs = ledger.get("runs", [])
    if (
        ledger.get("phase") != PHASE
        or ledger.get("plan_revision") != PRIOR_PLAN_REVISION
        or ledger.get("admitted_api_calls") != PRIOR_API_CALLS
        or ledger.get("completed_api_calls") != PRIOR_API_CALLS
        or len(runs) != 1
        or runs[0].get("deployment_id") != report.get("deployment_id")
        or runs[0].get("cohort_fingerprint") != fingerprint
        or ledger.get("external_cohort_calls", {}).get(fingerprint) != 2
        or not isinstance(state, dict)
        or state.get("next_index") != PRIOR_CURSOR
        or state.get("total") != original.base.MAX_COHORT_SIZE
        or state.get("campaign_id") != report.get("campaign_id", "gemini_dino_phase1_test")
    ):
        raise SafetyError("Prior ledger does not match the reviewed remediation baseline")
    return {
        "report_sha256": _sha(report_path, "prior report"),
        "ledger_sha256": _sha(ledger_path, "prior ledger"),
        "old_deployment_id": report.get("deployment_id"),
        "old_base_url": report.get("base_url"),
        "old_cohort_fingerprint": fingerprint,
        "campaign_id": state["campaign_id"],
        "prior_cursor": PRIOR_CURSOR,
    }


def bind_cohorts(
    prior_cohort_path: Path,
    new_cohort_path: Path,
    evidence: dict[str, Any],
    new_base_url: str,
    new_deployment_id: str,
    expected_project_ref: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    prior = original.base.load_cohort(
        prior_cohort_path, "remote", evidence["old_base_url"], expected_project_ref,
        evidence["old_deployment_id"],
    )
    current = original.base.load_cohort(
        new_cohort_path, "remote", new_base_url, expected_project_ref, new_deployment_id,
    )
    old_fingerprint = original.base.cohort_fingerprint(prior)
    if old_fingerprint != evidence["old_cohort_fingerprint"]:
        raise SafetyError("Prior cohort fingerprint changed")
    identity = original.base.participant_identity_fingerprint(prior)
    if original.base.participant_identity_fingerprint(current) != identity:
        raise SafetyError("Remediation cohort changed participant identities or ordering")
    if prior["campaign_id"] != current["campaign_id"] or current["campaign_id"] != evidence["campaign_id"]:
        raise SafetyError("Remediation cohort campaign changed")
    binding = {
        **evidence,
        "prior_cohort_sha256": _sha(prior_cohort_path, "prior cohort"),
        "new_cohort_sha256": _sha(new_cohort_path, "remediation cohort"),
        "new_cohort_fingerprint": original.base.cohort_fingerprint(current),
        "participant_identity_sha256": identity,
        "new_base_url": new_base_url,
        "new_deployment_id": new_deployment_id,
    }
    return current, binding


def load_approval_marker(path: Path, binding: dict[str, Any]) -> dict[str, Any]:
    marker = _json(path, "remediation approval marker")
    expected = {
        "phase": PHASE,
        "plan_revision": PLAN_REVISION,
        "approved_remote": True,
        "game_version": GAME_VERSION,
        "max_cumulative_api_calls": MAX_API_CALLS,
        "max_cumulative_seconds": MAX_CUMULATIVE_SECONDS,
        "prior_api_calls": PRIOR_API_CALLS,
        "prior_charged_seconds": PRIOR_CHARGED_SECONDS,
        "prior_cursor": PRIOR_CURSOR,
        "stages": ["100-remediation", "200-remediation-burst"],
        **binding,
    }
    exact_keys = {*expected, "run_id"}
    if set(marker) != exact_keys or any(marker.get(key) != value for key, value in expected.items()):
        raise SafetyError("Remediation approval marker does not match the exact evidence-bound run")
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,80}", str(marker.get("run_id", ""))):
        raise SafetyError("Remediation approval marker needs a new exact run_id")
    return marker


class RemediationLedger(original.base.BudgetLedger):
    def __init__(self, path: Path, binding: dict[str, Any], cohort_size: int):
        self.binding = binding
        self.cohort_size = cohort_size
        super().__init__(path)

    def _read(self) -> dict[str, Any]:
        existed = self.path.exists()
        if not existed:
            fingerprint = self.binding["new_cohort_fingerprint"]
            return {
                "version": 2,
                "phase": PHASE,
                "plan_revision": PLAN_REVISION,
                "admitted_api_calls": PRIOR_API_CALLS,
                "completed_api_calls": PRIOR_API_CALLS,
                "duration_reserved_seconds": PRIOR_CHARGED_SECONDS,
                "runs": [],
                "cohorts": {fingerprint: {
                    "next_index": PRIOR_CURSOR,
                    "total": self.cohort_size,
                    "campaign_id": self.binding["campaign_id"],
                }},
                "external_cohort_calls": {fingerprint: 2},
                "prior_evidence": dict(self.binding),
            }
        data = super()._read()
        if (
            data.get("phase") != PHASE
            or data.get("plan_revision") != PLAN_REVISION
            or data.get("prior_evidence") != self.binding
        ):
            raise SafetyError("Remediation ledger is not bound to the preserved failed run")
        return data

    def reserve_run(self, seconds: int, profile: str, cohort_fingerprint: str, deployment_id: str | None) -> None:
        with self.lock:
            if self.data.get("runs"):
                raise BudgetExceeded("The remediation permits exactly one run")
            if seconds != REMEDIATION_RESERVED_SECONDS or profile != "remediation":
                raise SafetyError("Remediation reservation changed")
            if self.data["duration_reserved_seconds"] + seconds > MAX_CUMULATIVE_SECONDS:
                raise BudgetExceeded("Cumulative 390-second remediation budget exceeded")
            self.data["duration_reserved_seconds"] += seconds
            self.data["runs"].append({
                "phase": PHASE,
                "plan_revision": PLAN_REVISION,
                "profile": profile,
                "duration_reserved_seconds": seconds,
                "cohort_fingerprint": cohort_fingerprint,
                "deployment_id": deployment_id,
                "started_at": int(time.time()),
            })
            self._write()

    def admit_call(self) -> None:
        with self.lock:
            if self.data["admitted_api_calls"] >= MAX_API_CALLS:
                raise BudgetExceeded("Cumulative 7,000 API-call remediation budget exhausted")
            self.data["admitted_api_calls"] += 1
            self._write()

    @property
    def remaining_calls(self) -> int:
        return MAX_API_CALLS - self.data["admitted_api_calls"]


def assert_evidence_unchanged(paths: dict[str, Path], binding: dict[str, Any]) -> None:
    checks = {
        "report_sha256": (paths["prior_report"], "prior report"),
        "ledger_sha256": (paths["prior_ledger"], "prior ledger"),
        "prior_cohort_sha256": (paths["prior_cohort"], "prior cohort"),
        "new_cohort_sha256": (paths["cohort"], "remediation cohort"),
    }
    if any(_sha(path, label) != binding[key] for key, (path, label) in checks.items()):
        raise SafetyError("Evidence-bound files changed during remediation")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--base-url")
    parser.add_argument("--expected-deployment-id")
    parser.add_argument("--expected-project-ref", default=original.base.EXPECTED_PROJECT_REF)
    parser.add_argument("--prior-report", type=Path)
    parser.add_argument("--prior-ledger", type=Path)
    parser.add_argument("--prior-cohort", type=Path)
    parser.add_argument("--cohort", type=Path)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--approval-marker", type=Path)
    parser.add_argument("--protection-token-file", type=Path)
    parser.add_argument("--deployment-auth-cookie-file", type=Path)
    parser.add_argument("--timeout", type=float, default=10.0)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if not args.execute:
        print(json.dumps({
            "phase": PHASE,
            "plan_revision": PLAN_REVISION,
            "mode": "dry-run",
            "network_calls": 0,
            **estimate(),
        }, ensure_ascii=False, indent=2))
        return 0
    required = (
        args.base_url, args.expected_deployment_id, args.prior_report, args.prior_ledger,
        args.prior_cohort, args.cohort, args.ledger, args.report, args.approval_marker,
    )
    if not all(required):
        raise SafetyError("Remediation execution requires both preserved evidence and new exact run files")
    base_url = original.base.validate_target(args.base_url, "remote")
    evidence = load_prior_evidence(args.prior_report, args.prior_ledger)
    cohort, binding = bind_cohorts(
        args.prior_cohort, args.cohort, evidence, base_url,
        args.expected_deployment_id, args.expected_project_ref,
    )
    load_approval_marker(args.approval_marker, binding)
    paths = {
        "prior_report": args.prior_report,
        "prior_ledger": args.prior_ledger,
        "prior_cohort": args.prior_cohort,
        "cohort": args.cohort,
    }
    assert_evidence_unchanged(paths, binding)
    protection_token, deployment_auth_cookie = original.load_platform_auth(
        args.protection_token_file, args.deployment_auth_cookie_file,
    )
    fingerprint = binding["new_cohort_fingerprint"]
    stop = threading.Event()
    metrics = original.base.Metrics()
    with RemediationLedger(args.ledger, binding, len(cohort["participants"])) as ledger:
        if RUNNER_CALL_CEILING > ledger.remaining_calls:
            raise BudgetExceeded("Remediation would exceed the cumulative 7,000-call budget")
        if FLOW_CEILING > ledger.participants_remaining(fingerprint, len(cohort["participants"])):
            raise BudgetExceeded("Remediation cohort has fewer than 500 fresh identities")
        ledger.reserve_run(REMEDIATION_RESERVED_SECONDS, "remediation", fingerprint, args.expected_deployment_id)
        started_at = time.monotonic()
        client = original.base.HttpClient(
            base_url, ledger, metrics, args.timeout, stop,
            started_at + REMEDIATION_RESERVED_SECONDS,
            protection_token, deployment_auth_cookie,
        )
        _, health = client.request("GET", "/api/health", "preflight")
        _, config = client.request("GET", "/api/config", "preflight")
        original.validate_phase3_preflight(
            "remote", health, config, args.expected_project_ref,
            args.expected_deployment_id, cohort["campaign_id"],
        )
        stages = []
        sequence = [PRIOR_CURSOR]
        sequence_lock = threading.Lock()
        failure = None
        try:
            for virtual_users, seconds, burst, label in PROFILES:
                stages.append(original.run_stage(
                    client, cohort, ledger, fingerprint, virtual_users, seconds, burst,
                    label, sequence, sequence_lock, THINK_TIME_SECONDS,
                ))
                if stop.is_set():
                    break
        except BaseException as error:
            failure = original.base.safe_failure(error)
            stop.set()
        assert_evidence_unchanged(paths, binding)
        elapsed = time.monotonic() - started_at
        metrics_report = metrics.report(elapsed)
        if failure is None:
            failure = original.metrics_failure(metrics_report)
        report = {
            "phase": PHASE,
            "plan_revision": PLAN_REVISION,
            "game_version": GAME_VERSION,
            "deployment_id": args.expected_deployment_id,
            "cohort_fingerprint": fingerprint,
            "prior_evidence": binding,
            "estimate": estimate(),
            "actual_duration_seconds": round(elapsed, 2),
            "stages": stages,
            "metrics": metrics_report,
            "failure": failure,
            "budget": {
                "admitted_api_calls": ledger.data["admitted_api_calls"],
                "completed_api_calls": ledger.data["completed_api_calls"],
                "duration_reserved_seconds": ledger.data["duration_reserved_seconds"],
                "max_api_calls": MAX_API_CALLS,
                "max_duration_seconds": MAX_CUMULATIVE_SECONDS,
            },
            "kakao_callback_calls": 0,
            "claim_mutation_calls": 0,
        }
        original.base.write_private_json(args.report, report)
        return 1 if failure else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SafetyError as error:
        print(json.dumps({"phase": PHASE, "error": type(error).__name__, "message": str(error)}), file=sys.stderr)
        raise SystemExit(2)
