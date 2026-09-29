#!/usr/bin/env python3
"""One final load run after preserving both prior failed-run evidence sets."""
from __future__ import annotations

import argparse
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
import phase3_load_remediation as remediation  # noqa: E402

PHASE = 3
PLAN_REVISION = "final-v21-harness-correction-v1"
PRIOR_API_CALLS = 818
PRIOR_CURSOR = 200
PRIOR_CHARGED_SECONDS = math.ceil(11.52) + math.ceil(6.31)
MAX_API_CALLS = 7_000
MAX_CUMULATIVE_SECONDS = 390
THINK_TIME_SECONDS = 50.0
PROFILES = remediation.PROFILES
RESERVED_SECONDS = remediation.REMEDIATION_RESERVED_SECONDS
FLOW_CEILING = remediation.FLOW_CEILING
RUNNER_CALL_CEILING = remediation.RUNNER_CALL_CEILING
CUMULATIVE_CALL_CEILING = PRIOR_API_CALLS + RUNNER_CALL_CEILING
CUMULATIVE_SECONDS_CEILING = PRIOR_CHARGED_SECONDS + RESERVED_SECONDS

SafetyError = original.SafetyError
BudgetExceeded = original.BudgetExceeded


def estimate() -> dict[str, Any]:
    return {
        "flow_attempts_ceiling": FLOW_CEILING,
        "new_runner_api_calls_ceiling": RUNNER_CALL_CEILING,
        "prior_api_calls": PRIOR_API_CALLS,
        "cumulative_api_calls_ceiling": CUMULATIVE_CALL_CEILING,
        "prior_charged_seconds": PRIOR_CHARGED_SECONDS,
        "new_reserved_seconds": RESERVED_SECONDS,
        "cumulative_seconds_ceiling": CUMULATIVE_SECONDS_CEILING,
        "remaining_api_calls": MAX_API_CALLS - CUMULATIVE_CALL_CEILING,
        "remaining_seconds": MAX_CUMULATIVE_SECONDS - CUMULATIVE_SECONDS_CEILING,
        "automatic_retry_calls": 0,
    }


def load_evidence_chain(
    first_report_path: Path,
    first_ledger_path: Path,
    first_cohort_path: Path,
    remediation_report_path: Path,
    remediation_ledger_path: Path,
    remediation_cohort_path: Path,
    expected_project_ref: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    first = remediation.load_prior_evidence(first_report_path, first_ledger_path)
    remediation_report = remediation._json(remediation_report_path, "remediation report")
    new_base_url = remediation_report.get("prior_evidence", {}).get("new_base_url")
    new_deployment_id = remediation_report.get("deployment_id")
    current, first_binding = remediation.bind_cohorts(
        first_cohort_path, remediation_cohort_path, first, new_base_url,
        new_deployment_id, expected_project_ref,
    )
    remediation_ledger = remediation._json(remediation_ledger_path, "remediation ledger")
    fingerprint = first_binding["new_cohort_fingerprint"]
    state = remediation_ledger.get("cohorts", {}).get(fingerprint)
    runs = remediation_ledger.get("runs", [])
    if (
        remediation_report.get("phase") != PHASE
        or remediation_report.get("plan_revision") != remediation.PLAN_REVISION
        or remediation_report.get("prior_evidence") != first_binding
        or remediation_report.get("cohort_fingerprint") != fingerprint
        or remediation_report.get("actual_duration_seconds") != 6.31
        or remediation_report.get("failure") != {
            "type": "SeriousFailure",
            "reason": "Final-load tracking batch was not accepted exactly",
        }
        or remediation_report.get("metrics", {}).get("api_calls") != 356
        or remediation_report.get("metrics", {}).get("flows_completed") != 0
        or remediation_report.get("budget", {}).get("admitted_api_calls") != PRIOR_API_CALLS
        or remediation_report.get("budget", {}).get("completed_api_calls") != PRIOR_API_CALLS
        or remediation_report.get("budget", {}).get("duration_reserved_seconds") != 372
        or remediation_ledger.get("phase") != PHASE
        or remediation_ledger.get("plan_revision") != remediation.PLAN_REVISION
        or remediation_ledger.get("prior_evidence") != first_binding
        or remediation_ledger.get("admitted_api_calls") != PRIOR_API_CALLS
        or remediation_ledger.get("completed_api_calls") != PRIOR_API_CALLS
        or remediation_ledger.get("duration_reserved_seconds") != 372
        or len(runs) != 1
        or runs[0].get("deployment_id") != new_deployment_id
        or runs[0].get("cohort_fingerprint") != fingerprint
        or not isinstance(state, dict)
        or state.get("next_index") != PRIOR_CURSOR
        or state.get("total") != 5000
        or state.get("campaign_id") != first_binding["campaign_id"]
    ):
        raise SafetyError("Two-run evidence chain does not match the reviewed harness correction baseline")
    binding = {
        "first_report_sha256": remediation._sha(first_report_path, "first report"),
        "first_ledger_sha256": remediation._sha(first_ledger_path, "first ledger"),
        "first_cohort_sha256": remediation._sha(first_cohort_path, "first cohort"),
        "remediation_report_sha256": remediation._sha(remediation_report_path, "remediation report"),
        "remediation_ledger_sha256": remediation._sha(remediation_ledger_path, "remediation ledger"),
        "remediation_cohort_sha256": remediation._sha(remediation_cohort_path, "remediation cohort"),
        "deployment_id": new_deployment_id,
        "base_url": new_base_url,
        "cohort_fingerprint": fingerprint,
        "participant_identity_sha256": first_binding["participant_identity_sha256"],
        "campaign_id": first_binding["campaign_id"],
        "prior_cursor": PRIOR_CURSOR,
    }
    return current, binding


def load_approval_marker(path: Path, binding: dict[str, Any]) -> dict[str, Any]:
    marker = remediation._json(path, "harness correction approval marker")
    expected = {
        "phase": PHASE,
        "plan_revision": PLAN_REVISION,
        "approved_remote": True,
        "game_version": original.GAME_VERSION,
        "max_cumulative_api_calls": MAX_API_CALLS,
        "max_cumulative_seconds": MAX_CUMULATIVE_SECONDS,
        "prior_api_calls": PRIOR_API_CALLS,
        "prior_charged_seconds": PRIOR_CHARGED_SECONDS,
        "prior_cursor": PRIOR_CURSOR,
        "stages": ["100-remediation", "200-remediation-burst"],
        **binding,
    }
    if set(marker) != {*expected, "run_id"} or any(marker.get(key) != value for key, value in expected.items()):
        raise SafetyError("Harness correction marker does not match the exact two-run evidence chain")
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,80}", str(marker.get("run_id", ""))):
        raise SafetyError("Harness correction marker needs a new exact run_id")
    return marker


class CorrectionLedger(original.base.BudgetLedger):
    def __init__(self, path: Path, binding: dict[str, Any], cohort_size: int):
        self.binding = binding
        self.cohort_size = cohort_size
        super().__init__(path)

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            fingerprint = self.binding["cohort_fingerprint"]
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
                "prior_evidence_chain": dict(self.binding),
            }
        data = super()._read()
        if (
            data.get("phase") != PHASE
            or data.get("plan_revision") != PLAN_REVISION
            or data.get("prior_evidence_chain") != self.binding
        ):
            raise SafetyError("Harness correction ledger is not bound to both preserved runs")
        return data

    def reserve_run(self, seconds: int, profile: str, cohort_fingerprint: str, deployment_id: str | None) -> None:
        with self.lock:
            if self.data.get("runs"):
                raise BudgetExceeded("The harness correction permits exactly one run")
            if seconds != RESERVED_SECONDS or profile != "harness-correction":
                raise SafetyError("Harness correction reservation changed")
            if self.data["duration_reserved_seconds"] + seconds > MAX_CUMULATIVE_SECONDS:
                raise BudgetExceeded("Cumulative 390-second budget exceeded")
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
                raise BudgetExceeded("Cumulative 7,000 API-call budget exhausted")
            self.data["admitted_api_calls"] += 1
            self._write()

    @property
    def remaining_calls(self) -> int:
        return MAX_API_CALLS - self.data["admitted_api_calls"]


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--base-url")
    parser.add_argument("--expected-deployment-id")
    parser.add_argument("--expected-project-ref", default=original.base.EXPECTED_PROJECT_REF)
    for name in (
        "first-report", "first-ledger", "first-cohort", "remediation-report",
        "remediation-ledger", "remediation-cohort", "ledger", "report", "approval-marker",
        "protection-token-file", "deployment-auth-cookie-file",
    ):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--timeout", type=float, default=10.0)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if not args.execute:
        print(json.dumps({
            "phase": PHASE, "plan_revision": PLAN_REVISION, "mode": "dry-run",
            "network_calls": 0, **estimate(),
        }, indent=2))
        return 0
    required = (
        args.base_url, args.expected_deployment_id, args.first_report, args.first_ledger,
        args.first_cohort, args.remediation_report, args.remediation_ledger,
        args.remediation_cohort, args.ledger, args.report, args.approval_marker,
    )
    if not all(required):
        raise SafetyError("Harness correction requires both preserved runs and new exact run files")
    base_url = original.base.validate_target(args.base_url, "remote")
    cohort, binding = load_evidence_chain(
        args.first_report, args.first_ledger, args.first_cohort,
        args.remediation_report, args.remediation_ledger, args.remediation_cohort,
        args.expected_project_ref,
    )
    if base_url != binding["base_url"] or args.expected_deployment_id != binding["deployment_id"]:
        raise SafetyError("Harness correction must use the fixed remediation deployment")
    load_approval_marker(args.approval_marker, binding)
    evidence_paths = {
        "first_report_sha256": args.first_report,
        "first_ledger_sha256": args.first_ledger,
        "first_cohort_sha256": args.first_cohort,
        "remediation_report_sha256": args.remediation_report,
        "remediation_ledger_sha256": args.remediation_ledger,
        "remediation_cohort_sha256": args.remediation_cohort,
    }
    if any(remediation._sha(path, key) != binding[key] for key, path in evidence_paths.items()):
        raise SafetyError("Evidence-chain files changed before harness correction")
    protection_token, deployment_auth_cookie = original.load_platform_auth(
        args.protection_token_file, args.deployment_auth_cookie_file,
    )
    fingerprint = binding["cohort_fingerprint"]
    stop = threading.Event()
    metrics = original.base.Metrics()
    with CorrectionLedger(args.ledger, binding, len(cohort["participants"])) as ledger:
        if RUNNER_CALL_CEILING > ledger.remaining_calls:
            raise BudgetExceeded("Harness correction exceeds cumulative API-call budget")
        if FLOW_CEILING > ledger.participants_remaining(fingerprint, len(cohort["participants"])):
            raise BudgetExceeded("Harness correction has fewer than 500 fresh identities")
        ledger.reserve_run(RESERVED_SECONDS, "harness-correction", fingerprint, args.expected_deployment_id)
        started_at = time.monotonic()
        client = original.base.HttpClient(
            base_url, ledger, metrics, args.timeout, stop, started_at + RESERVED_SECONDS,
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
        lock = threading.Lock()
        failure = None
        try:
            for virtual_users, seconds, burst, label in PROFILES:
                stages.append(original.run_stage(
                    client, cohort, ledger, fingerprint, virtual_users, seconds, burst,
                    label, sequence, lock, THINK_TIME_SECONDS,
                ))
                if stop.is_set():
                    break
        except BaseException as error:
            failure = original.base.safe_failure(error)
            stop.set()
        if any(remediation._sha(path, key) != binding[key] for key, path in evidence_paths.items()):
            raise SafetyError("Evidence-chain files changed during harness correction")
        elapsed = time.monotonic() - started_at
        metrics_report = metrics.report(elapsed)
        if failure is None:
            failure = original.metrics_failure(metrics_report)
        original.base.write_private_json(args.report, {
            "phase": PHASE,
            "plan_revision": PLAN_REVISION,
            "game_version": original.GAME_VERSION,
            "deployment_id": args.expected_deployment_id,
            "cohort_fingerprint": fingerprint,
            "prior_evidence_chain": binding,
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
        })
        return 1 if failure else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SafetyError as error:
        print(json.dumps({"phase": PHASE, "error": type(error).__name__, "message": str(error)}), file=sys.stderr)
        raise SystemExit(2)
