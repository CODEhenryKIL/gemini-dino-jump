#!/usr/bin/env python3
"""Dry-run-first, fail-closed Phase 2 mixed Preview load runner.

Remote execution requires an explicit ``--execute`` flag and a private Phase 2
approval marker. Merely invoking this script is network-free.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "server"))

import phase1_load as base  # noqa: E402
import game_verifier  # noqa: E402
import game_verifier_v2  # noqa: E402

PHASE = 2
GAME_VERSION = "2.0.0"
MAX_API_CALLS = 10_000
MAX_DURATION_SECONDS = 12 * 60
RUN_OVERHEAD_SECONDS = 90
DEFAULT_THINK_TIME_SECONDS = 45.0
MAX_FIXTURE_TICKS = 75 * 60
RICH_FIXTURE_EVERY = 100
CLAIM_EVERY = 20
PROFILES = {
    "full": (
        (100, 180, False, "100-stage"),
        (200, 30, True, "200-burst"),
    ),
}
BASE_FLOW_CALLS = 11
PREFLIGHT_CALLS = 2

SafetyError = base.SafetyError
BudgetExceeded = base.BudgetExceeded
SeriousFailure = base.SeriousFailure
UnexpectedResponse = base.UnexpectedResponse
RateLimited = base.RateLimited


class Phase2BudgetLedger(base.BudgetLedger):
    """Phase 2 ledger that refuses Phase 1 files and has independent hard caps."""

    def _read(self) -> dict[str, Any]:
        existed = self.path.exists()
        data = super()._read()
        phase = data.get("phase")
        if existed and phase != PHASE:
            raise SafetyError("Refusing a non-Phase-2 ledger; preserve the Phase 1 ledger")
        data["phase"] = PHASE
        return data

    def reserve_run(self, seconds: int, profile: str, cohort_fingerprint: str, deployment_id: str | None) -> None:
        with self.lock:
            if self.data.get("runs"):
                raise BudgetExceeded("Phase 2 permits only one 100-VU stage plus one 200-VU burst")
            used = self.data["duration_reserved_seconds"]
            if used + seconds > MAX_DURATION_SECONDS:
                raise BudgetExceeded("Cumulative Phase 2 12-minute duration budget exceeded")
            self.data["duration_reserved_seconds"] = used + seconds
            self.data["runs"].append({
                "phase": PHASE,
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
                raise BudgetExceeded("Cumulative Phase 2 10,000 API-call budget exhausted")
            self.data["admitted_api_calls"] += 1
            self._write()

    def register_cohort_preparation(self, fingerprint: str, api_calls: int) -> None:
        if type(api_calls) is not int or api_calls < 0:
            raise SafetyError("Cohort preparation_api_calls must be a non-negative integer")
        with self.lock:
            charged = self.data.setdefault("external_cohort_calls", {})
            existing = charged.get(fingerprint)
            if existing is not None:
                if existing != api_calls:
                    raise SafetyError("Cohort preparation count changed")
                return
            if self.data["admitted_api_calls"] + api_calls > MAX_API_CALLS:
                raise BudgetExceeded("Cohort preparation exceeds the Phase 2 call budget")
            self.data["admitted_api_calls"] += api_calls
            self.data["completed_api_calls"] += api_calls
            charged[fingerprint] = api_calls
            self._write()

    @property
    def remaining_calls(self) -> int:
        return MAX_API_CALLS - self.data["admitted_api_calls"]


def validate_phase2_preflight(
    mode: str,
    health: dict[str, Any],
    config: dict[str, Any],
    expected_project_ref: str,
    expected_deployment_id: str | None,
    expected_campaign_id: str,
) -> None:
    if health.get("ok") is not True or health.get("database") != "ready":
        raise SafetyError("Health check is not database-backed and ready")
    if health.get("service") != "gemini-dino-jump":
        raise SafetyError("Unexpected service identity")
    if health.get("environment") == "production":
        raise SafetyError("Production targets are forbidden")
    campaign = config.get("campaign")
    if not isinstance(campaign, dict) or campaign.get("id") != expected_campaign_id:
        raise SafetyError("Prepared campaign identity mismatch")
    if campaign.get("status") != "ACTIVE":
        raise SafetyError("Prepared campaign is not active")
    if campaign.get("game_version") != GAME_VERSION:
        raise SafetyError("Phase 2 requires game version 2.0.0")
    if mode == "remote":
        expected = {
            "environment": "preview",
            "project_ref": expected_project_ref,
            "schema": base.EXPECTED_SCHEMA,
            "synthetic_only": True,
            "test_seed": True,
            "deployment": expected_deployment_id,
        }
        for key, value in expected.items():
            if value is None or health.get(key) != value:
                raise SafetyError(f"Preview guard mismatch: {key}")
        if base.project_ref_from_config(config) != expected_project_ref:
            raise SafetyError("Public config points at another Supabase project")
    elif health.get("environment") not in ("local", "test"):
        raise SafetyError("Local target reports a non-local environment")


def load_approval_marker(
    path: Path,
    base_url: str,
    deployment_id: str,
    campaign_id: str,
) -> dict[str, Any]:
    try:
        marker = json.loads(base.read_private_text(path, "Phase 2 approval marker"))
    except json.JSONDecodeError as error:
        raise SafetyError("Invalid Phase 2 approval marker JSON") from error
    expected = {
        "phase": PHASE,
        "approved_remote": True,
        "base_url": base_url,
        "deployment_id": deployment_id,
        "campaign_id": campaign_id,
        "max_api_calls": MAX_API_CALLS,
        "max_duration_seconds": MAX_DURATION_SECONDS,
    }
    if not isinstance(marker, dict) or any(marker.get(key) != value for key, value in expected.items()):
        raise SafetyError("Phase 2 remote approval marker does not match this exact bounded run")
    if marker.get("stages") != ["100-stage", "200-burst"]:
        raise SafetyError("Approval marker must name the one 100 stage and one 200 burst")
    return marker


def normal_fixture(seed: int) -> dict[str, Any]:
    result = game_verifier_v2.simulate(
        game_verifier.V2_CONSTANTS,
        seed,
        [],
        game_verifier.V2_CONSTANTS["rules"]["maxTicks"],
    )
    verified = game_verifier.verify_game(GAME_VERSION, seed, [], result["score"], result["ticks"])
    if (
        not verified["valid"]
        or result.get("end_reason") != "COLLISION"
        or type(result.get("ticks")) is not int
        or result["ticks"] > MAX_FIXTURE_TICKS
    ):
        raise SeriousFailure("Local v2 verifier rejected its deterministic no-jump fixture")
    return {"jump_ticks": [], **result}


def rich_fixture(seed: int) -> dict[str, Any]:
    command = [
        "node",
        str(ROOT / "tests" / "js_v2_fixture_runner.cjs"),
        json.dumps({"mode": "bot", "seed": seed, "target_revives": 2}, separators=(",", ":")),
    ]
    try:
        completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=20, check=True)
        result = json.loads(completed.stdout)
        verified = game_verifier.verify_game(
            GAME_VERSION, seed, result.get("jump_ticks"), result.get("score"), result.get("ticks")
        )
        summary = verified.get("summary", {})
        bounded = (
            verified.get("valid") is True
            and result.get("end_reason") == "COLLISION"
            and type(result.get("ticks")) is int
            and 0 < result["ticks"] <= MAX_FIXTURE_TICKS
            and summary.get("coins", 0) >= 1
            and summary.get("revives", 0) >= 2
        )
        if bounded:
            result["summary"] = summary
            return result
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError, TypeError, ValueError):
        pass
    # Never truncate ticks or fabricate a terminal result. A genuine no-jump
    # collision is the safe bounded fallback for seeds whose rich bot runs long.
    return normal_fixture(seed)


def game_fixture(seed: int, sequence: int) -> tuple[dict[str, Any], bool]:
    rich_attempt = sequence % RICH_FIXTURE_EVERY == 0
    fixture = rich_fixture(seed) if rich_attempt else normal_fixture(seed)
    summary = fixture.get("summary", {})
    used_rich_path = rich_attempt and summary.get("coins", 0) >= 1 and summary.get("revives", 0) >= 2
    return fixture, used_rich_path


def phase2_user_flow(client: base.HttpClient, participant: dict[str, Any], sequence: int) -> None:
    cookie = participant["cookie"]
    _, me = client.request("GET", "/api/me", "entry", cookie)
    tickets = me.get("tickets", {})
    if tickets.get("initial") != 1 or tickets.get("invitation") != 0:
        raise SeriousFailure("Fresh Phase 2 participant is not in the expected one-ticket state")

    _, created = base.mutating_request(
        client, "POST", "/api/game-sessions", "game_start", cookie,
        {"event_id": base.event_id("evt_create")}, (201,),
    )
    session_id, seed, version = created.get("session_id"), created.get("seed"), created.get("version")
    if not isinstance(session_id, str) or type(seed) is not int or version != GAME_VERSION:
        raise SeriousFailure("Invalid Phase 2 game session response")
    session_path = urllib.parse.quote(session_id, safe="")
    _, started = base.mutating_request(
        client, "POST", f"/api/game-sessions/{session_path}/start", "game_start", cookie,
        {"event_id": base.event_id("evt_start")}, (200,),
    )
    if started.get("status") != "ACTIVE":
        raise SeriousFailure("Game session did not become active")

    fixture, rich = game_fixture(seed, sequence)
    base.wait_for_play(client, fixture["ticks"] / 60 + base.PLAY_WAIT_GRACE_SECONDS, client.deadline)
    _, finished = base.mutating_request(
        client, "POST", f"/api/game-sessions/{session_path}/finish", "game_finish", cookie,
        {
            "event_id": base.event_id("evt_finish"),
            "score": fixture["score"],
            "ticks": fixture["ticks"],
            "jump_ticks": fixture["jump_ticks"],
            "client_finished_at": base.utc_now(),
        },
        (200,),
    )
    if finished.get("verification") != "VERIFIED" or finished.get("status") != "FINISHED":
        raise SeriousFailure("Genuine Phase 2 physics result was rejected")
    summary = finished.get("summary", {})
    if rich and any(
        summary.get(key) != fixture.get("summary", {}).get(key)
        for key in ("coins", "coin_score", "hearts", "revives")
    ):
        raise SeriousFailure("Server response did not reproduce the deterministic rich fixture")

    _, draw_state = client.request("GET", "/api/draws/me", "draw", cookie)
    if draw_state.get("status") != "AVAILABLE":
        raise SeriousFailure("Verified participant is not draw-eligible")
    _, raw_draw = base.mutating_request(
        client, "POST", "/api/draws", "draw", cookie,
        {"pouch_index": sequence % 3, "event_id": base.event_id("evt_draw")}, (200, 201),
    )
    draw = base.unwrap_draw(raw_draw)
    draw_id = draw.get("draw_id")
    if not isinstance(draw_id, str):
        raise SeriousFailure("Draw response has no opaque draw ID")
    _, scratched = base.mutating_request(
        client, "PATCH", f"/api/draws/{urllib.parse.quote(draw_id, safe='')}/scratch-complete",
        "draw", cookie, {"event_id": base.event_id("evt_scratch")}, (200,),
    )
    if scratched.get("scratch_completed") is not True:
        raise SeriousFailure("Scratch completion was not persisted")

    client.request("GET", "/api/leaderboard?limit=20", "ranking", cookie)
    client.request("GET", "/api/referrals/me", "share", cookie)
    client.request("GET", "/api/claims", "claim", cookie)
    claim_id = draw.get("claim_id")
    if claim_id and sequence % CLAIM_EVERY == 0:
        base.mutating_request(
            client, "POST", f"/api/claims/{urllib.parse.quote(str(claim_id), safe='')}/submit",
            "claim", cookie,
            {"name": "TEST_PHASE2_LOAD", "contact": "01000000000", "school": "TEST_SCHOOL", "address": "TEST_ADDRESS", "event_id": base.event_id("evt_claim")},
            (200,),
        )

    events = {"events": [
        {
            "event_id": base.event_id("evt_page"), "name": "page_view", "occurred_at": base.utc_now(),
            "screen": "game", "game_session_id": session_id,
            "dimensions": {"source": "phase2_load", "game_version": GAME_VERSION},
        },
        {
            "event_id": base.event_id("evt_share"), "name": "share_attempted", "occurred_at": base.utc_now(),
            "screen": "invite", "dimensions": {"source": "phase2_load", "link_kind": "retry_invite", "share_method": "copy", "status": "attempted", "share_id": base.event_id("share")},
        },
    ]}
    _, accepted = base.mutating_request(
        client, "POST", "/api/events/batch", "tracking", cookie, events, (202,),
    )
    if accepted.get("accepted") != 2 or accepted.get("rejected", 0) != 0:
        raise SeriousFailure("Phase 2 tracking batch was not accepted exactly")
    client.metrics.flow()
    if client.stage_metrics:
        client.stage_metrics.flow()


def run_stage(
    client: base.HttpClient,
    cohort: dict[str, Any],
    ledger: Phase2BudgetLedger,
    fingerprint: str,
    virtual_users: int,
    duration: int,
    burst: bool,
    label: str,
    sequence: list[int],
    sequence_lock: threading.Lock,
    think_time: float,
) -> dict[str, Any]:
    started_at = time.monotonic()
    admission_deadline = started_at + duration
    stage_metrics = base.Metrics()
    client.stage_metrics = stage_metrics
    barrier = threading.Barrier(virtual_users) if burst else None
    failures: list[BaseException] = []
    failure_lock = threading.Lock()

    def record_failure(error: BaseException) -> None:
        with failure_lock:
            if not failures:
                failures.append(error)
        client.stop.set()

    def worker() -> None:
        if barrier:
            try:
                barrier.wait(timeout=15)
            except threading.BrokenBarrierError:
                record_failure(SeriousFailure("Burst workers did not reach the start barrier"))
                return
        while time.monotonic() < admission_deadline and not client.stop.is_set():
            try:
                index = ledger.claim_participant(fingerprint, len(cohort["participants"]), cohort["campaign_id"])
            except BudgetExceeded:
                break
            with sequence_lock:
                sequence[0] += 1
                flow_sequence = sequence[0]
            try:
                phase2_user_flow(client, cohort["participants"][index], flow_sequence)
            except BudgetExceeded as error:
                record_failure(error)
                break
            except SeriousFailure as error:
                record_failure(error)
                break
            except (RateLimited, UnexpectedResponse, urllib.error.URLError, TimeoutError) as error:
                record_failure(error)
                break
            except Exception as error:
                with client.metrics.lock:
                    client.metrics.unexpected += 1
                record_failure(error)
                break
            if burst:
                break
            remaining = admission_deadline - time.monotonic()
            if remaining > 0:
                client.stop.wait(min(think_time, remaining))

    with concurrent.futures.ThreadPoolExecutor(max_workers=virtual_users, thread_name_prefix="phase2-load") as pool:
        futures = [pool.submit(worker) for _ in range(virtual_users)]
        concurrent.futures.wait(futures, timeout=duration + RUN_OVERHEAD_SECONDS)
        if any(not future.done() for future in futures):
            client.stop.set()
            raise SeriousFailure("Stage workers exceeded the bounded cleanup window")
    if failures:
        raise failures[0]
    elapsed = time.monotonic() - started_at
    client.stage_metrics = None
    return {
        "label": label,
        "virtual_users": virtual_users,
        "admission_window_seconds": duration,
        "actual_seconds_including_cleanup": round(elapsed, 2),
        "burst": burst,
        "metrics": stage_metrics.report(elapsed),
    }


def estimate_profile(think_time: float = DEFAULT_THINK_TIME_SECONDS) -> dict[str, Any]:
    if think_time < 10:
        raise SafetyError("Think time must be at least 10 seconds")
    stages = []
    for virtual_users, seconds, burst, label in PROFILES["full"]:
        flows = virtual_users if burst else virtual_users * math.ceil(seconds / think_time)
        stages.append({"label": label, "virtual_users": virtual_users, "seconds": seconds, "burst": burst, "flow_attempts_ceiling": flows})
    flows = sum(stage["flow_attempts_ceiling"] for stage in stages)
    claim_calls = math.ceil(flows / CLAIM_EVERY)
    calls = PREFLIGHT_CALLS + flows * BASE_FLOW_CALLS + claim_calls
    return {
        "stages": stages,
        "flow_attempts_ceiling": flows,
        "rich_fixture_attempts": flows // RICH_FIXTURE_EVERY,
        "cohort_participants_required_ceiling": flows,
        "absolute_api_calls_ceiling": calls,
        "tracking_events_ceiling": flows * 2,
    }


def reserved_duration() -> int:
    return sum(stage[1] + RUN_OVERHEAD_SECONDS for stage in PROFILES["full"])


def metrics_failure(metrics_report: dict[str, Any]) -> dict[str, str] | None:
    failures = {
        "rate_limited_429": int(metrics_report.get("rate_limited_429", 0) or 0),
        "timeouts": int(metrics_report.get("timeouts", 0) or 0),
        "unexpected_failures": int(metrics_report.get("unexpected_failures", 0) or 0),
    }
    if not any(failures.values()):
        return None
    detail = ", ".join(f"{name}={count}" for name, count in failures.items() if count)
    return {"type": "LoadMetricsFailure", "reason": f"Phase 2 load metrics contain failures: {detail}"}


def load_platform_auth(
    protection_token_file: Path | None,
    deployment_auth_cookie_file: Path | None,
) -> tuple[str | None, str | None]:
    protection_token = None
    if protection_token_file:
        protection_token = base.read_private_text(protection_token_file, "Protection token file")
        if not (16 <= len(protection_token) <= 2048) or any(char.isspace() for char in protection_token):
            raise SafetyError("Invalid Vercel protection bypass token")
    deployment_auth_cookie = None
    if deployment_auth_cookie_file:
        deployment_auth_cookie = base.read_private_text(
            deployment_auth_cookie_file, "Deployment auth cookie file"
        )
        if not re.fullmatch(r"[A-Za-z0-9_~-]{1,64}=[^;\s]{16,2048}", deployment_auth_cookie):
            raise SafetyError("Invalid Vercel deployment authentication cookie")
    return protection_token, deployment_auth_cookie


def dry_run(think_time: float = DEFAULT_THINK_TIME_SECONDS, cohort_size: int = base.MAX_COHORT_SIZE) -> dict[str, Any]:
    estimate = estimate_profile(think_time)
    return {
        "phase": PHASE,
        "mode": "dry-run",
        "network_calls": 0,
        "profile": "full",
        "game_version": GAME_VERSION,
        "prepared_cohort_size": cohort_size,
        "reserved_duration_seconds": reserved_duration(),
        "hard_cumulative_seconds": MAX_DURATION_SECONDS,
        "hard_api_call_ceiling": MAX_API_CALLS,
        **estimate,
        "within_hard_api_call_cap": estimate["absolute_api_calls_ceiling"] <= MAX_API_CALLS,
        "within_prepared_cohort": estimate["cohort_participants_required_ceiling"] <= cohort_size,
        "remote_approval_required": True,
        "estimated_cost": "TBD",
        "note": "Planning estimate only; no HTTP, database write, load execution, or cost promise.",
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Enable an actual bounded run; omitted means network-free dry-run")
    parser.add_argument("--mode", choices=("local", "remote"), default="local")
    parser.add_argument("--base-url")
    parser.add_argument("--cohort", type=Path)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--approval-marker", type=Path)
    parser.add_argument("--expected-project-ref", default=base.EXPECTED_PROJECT_REF)
    parser.add_argument("--expected-deployment-id")
    parser.add_argument("--protection-token-file", type=Path)
    parser.add_argument("--deployment-auth-cookie-file", type=Path)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--think-time", type=float, default=DEFAULT_THINK_TIME_SECONDS)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if not args.execute:
        report = dry_run(args.think_time)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["within_hard_api_call_cap"] and report["within_prepared_cohort"] else 2
    if not all((args.base_url, args.cohort, args.ledger, args.report)):
        raise SafetyError("Actual runs require explicit base URL, cohort, Phase 2 ledger, and report")
    base_url = base.validate_target(args.base_url, args.mode)
    if args.mode == "remote":
        if not args.expected_deployment_id or not args.approval_marker:
            raise SafetyError("Remote Phase 2 execution requires deployment ID and approval marker")
    cohort = base.load_cohort(
        args.cohort, args.mode, base_url, args.expected_project_ref, args.expected_deployment_id
    )
    if args.mode == "remote":
        load_approval_marker(
            args.approval_marker, base_url, args.expected_deployment_id, cohort["campaign_id"]
        )
    protection_token, deployment_auth_cookie = load_platform_auth(
        args.protection_token_file, args.deployment_auth_cookie_file
    )
    estimate = estimate_profile(args.think_time)
    reserved = reserved_duration()
    fingerprint = base.cohort_fingerprint(cohort)
    stop = threading.Event()
    metrics = base.Metrics()
    with Phase2BudgetLedger(args.ledger) as ledger:
        ledger.register_cohort_preparation(fingerprint, cohort.get("preparation_api_calls", 0))
        if estimate["absolute_api_calls_ceiling"] > ledger.remaining_calls:
            raise BudgetExceeded("Conservative Phase 2 call envelope exceeds remaining budget")
        if estimate["cohort_participants_required_ceiling"] > ledger.participants_remaining(fingerprint, len(cohort["participants"])):
            raise BudgetExceeded("Fresh participant cohort is too small for Phase 2")
        ledger.reserve_run(reserved, "full", fingerprint, args.expected_deployment_id)
        started_at = time.monotonic()
        client = base.HttpClient(
            base_url, ledger, metrics, args.timeout, stop, started_at + reserved,
            protection_token, deployment_auth_cookie,
        )
        _, health = client.request("GET", "/api/health", "preflight")
        _, config = client.request("GET", "/api/config", "preflight")
        validate_phase2_preflight(
            args.mode, health, config, args.expected_project_ref,
            args.expected_deployment_id, cohort["campaign_id"],
        )
        stages = []
        sequence = [0]
        sequence_lock = threading.Lock()
        failure = None
        try:
            for virtual_users, seconds, burst, label in PROFILES["full"]:
                stages.append(run_stage(
                    client, cohort, ledger, fingerprint, virtual_users, seconds, burst,
                    label, sequence, sequence_lock, args.think_time,
                ))
                if stop.is_set():
                    break
        except BaseException as error:
            failure = base.safe_failure(error)
            stop.set()
        elapsed = time.monotonic() - started_at
        metrics_report = metrics.report(elapsed)
        if failure is None:
            failure = metrics_failure(metrics_report)
        report = {
            "phase": PHASE,
            "game_version": GAME_VERSION,
            "profile": "full",
            "base_url": base_url,
            "deployment_id": args.expected_deployment_id,
            "cohort_fingerprint": fingerprint,
            "estimate": estimate,
            "reserved_duration_seconds": reserved,
            "actual_duration_seconds": round(elapsed, 2),
            "stages": stages,
            "metrics": metrics_report,
            "failure": failure,
            "budget": {
                "admitted_api_calls": ledger.data["admitted_api_calls"],
                "completed_api_calls": ledger.data["completed_api_calls"],
                "duration_reserved_seconds": ledger.data["duration_reserved_seconds"],
                "max_api_calls": MAX_API_CALLS,
                "max_duration_seconds": MAX_DURATION_SECONDS,
            },
            "estimated_cost": "TBD",
        }
        base.write_private_json(args.report, report)
        return 1 if failure else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SafetyError as error:
        print(json.dumps({"phase": PHASE, "error": type(error).__name__, "message": str(error)}), file=sys.stderr)
        raise SystemExit(2)
