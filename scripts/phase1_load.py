#!/usr/bin/env python3
"""Bounded Phase 1 load generator. Standard library only; never targets production."""
from __future__ import annotations

import argparse
import concurrent.futures
import fcntl
import hashlib
import json
import math
import os
import re
import ssl
import stat
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "server"))
import game_verifier  # noqa: E402

EXPECTED_PROJECT_REF = "igfrnexknwtiljdqjrbp"
MAX_API_CALLS = 30_000
MAX_DURATION_SECONDS = 30 * 60
RUN_OVERHEAD_SECONDS = 90
GAME_VERSION = "1.2.0"

PROFILES = {
    "smoke10": ((10, 15, False),),
    "smoke50": ((50, 15, False),),
    "10": ((10, 60, False),),
    "50": ((50, 120, False),),
    "100": ((100, 180, False),),
    "200": ((200, 300, False),),
    "burst": ((200, 30, True),),
    "full": ((10, 60, False), (50, 120, False), (100, 180, False), (200, 300, False), (200, 30, True)),
}

class SafetyError(RuntimeError): pass
class BudgetExceeded(SafetyError): pass
class SeriousFailure(SafetyError): pass
class RateLimited(SafetyError): pass
class UnexpectedResponse(SafetyError): pass


def percentile(values: list[float], p: float) -> float | None:
    if not values: return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(p * len(ordered)) - 1))
    return round(ordered[index], 2)


def endpoint_label(method: str, path: str) -> str:
    clean = urllib.parse.urlsplit(path).path
    clean = re.sub(r"/api/game-sessions/[^/]+", "/api/game-sessions/{id}", clean)
    clean = re.sub(r"/api/draws/[^/]+", "/api/draws/{id}", clean)
    clean = re.sub(r"/api/claims/[^/]+", "/api/claims/{id}", clean)
    return f"{method.upper()} {clean}"


def validate_target(base_url: str, mode: str) -> str:
    parsed = urllib.parse.urlsplit(base_url)
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        raise SafetyError("Base URL must be an explicit origin without credentials, path, query, or hash")
    if mode == "remote":
        if parsed.scheme != "https" or not parsed.hostname or not parsed.hostname.endswith(".vercel.app"):
            raise SafetyError("Remote target must be an explicit HTTPS Vercel Preview origin")
    elif parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
        raise SafetyError("Local target must be a loopback HTTP origin")
    return base_url.rstrip("/")


def validate_preflight(mode: str, health: dict, config: dict, campaign: dict, expected_ref: str = EXPECTED_PROJECT_REF) -> None:
    if health.get("status") != "ok" or health.get("database") != "ok": raise SafetyError("Health check is not database-backed OK")
    if health.get("synthetic_only") is not True: raise SafetyError("Target is not synthetic-only")
    if campaign.get("is_test") is not True or campaign.get("real_prizes_enabled") is not False: raise SafetyError("Target campaign is not test-only")
    if campaign.get("game_version") != GAME_VERSION or config.get("game_version") != GAME_VERSION: raise SafetyError("Game version mismatch")
    expected_environment = "preview" if mode == "remote" else ("local", "test")
    if mode == "remote":
        if health.get("environment") != expected_environment or config.get("environment") != expected_environment: raise SafetyError("Remote target is not Preview")
        if health.get("project_ref") != expected_ref: raise SafetyError("Unexpected Supabase project reference")
    elif health.get("environment") not in expected_environment or config.get("environment") not in expected_environment:
        raise SafetyError("Local target has a non-local environment")
    if config.get("environment") == "production" or health.get("environment") == "production": raise SafetyError("Production targets are forbidden")


class BudgetLedger:
    """Exclusive cumulative ledger. There is intentionally no reset operation."""
    def __init__(self, path: Path):
        self.path = path
        if path.is_symlink(): raise SafetyError("Ledger must not be a symlink")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        try: fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            os.close(self.fd); self.fd = None; raise SafetyError("Another load run already owns this ledger") from error
        self.lock = threading.Lock()
        os.chmod(path, 0o600)
        if stat.S_IMODE(os.fstat(self.fd).st_mode) != 0o600: raise SafetyError("Ledger permissions must be 0600")
        self.data = self._read()

    def _read(self) -> dict:
        os.lseek(self.fd, 0, os.SEEK_SET)
        raw = os.read(self.fd, 1_000_000)
        if not raw: return {"version": 1, "api_calls": 0, "duration_seconds": 0, "runs": []}
        data = json.loads(raw)
        if data.get("version") != 1 or any(type(data.get(k)) is not int or data[k] < 0 for k in ("api_calls", "duration_seconds")):
            raise SafetyError("Invalid budget ledger")
        return data

    def _write(self) -> None:
        payload = json.dumps(self.data, separators=(",", ":")).encode()
        os.lseek(self.fd, 0, os.SEEK_SET); os.ftruncate(self.fd, 0); os.write(self.fd, payload); os.fsync(self.fd)

    def reserve_duration(self, seconds: int, label: str) -> None:
        if self.data["duration_seconds"] + seconds > MAX_DURATION_SECONDS: raise BudgetExceeded("Cumulative 30-minute duration budget exceeded")
        self.data["duration_seconds"] += seconds
        self.data.setdefault("runs", []).append({"label": label, "duration_seconds": seconds, "started_at": int(time.time())})
        self._write()

    def consume_call(self) -> None:
        with self.lock:
            if self.data["api_calls"] >= MAX_API_CALLS: raise BudgetExceeded("Cumulative 30,000 API-call budget exhausted")
            self.data["api_calls"] += 1
            self._write()

    @property
    def remaining_calls(self) -> int: return MAX_API_CALLS - self.data["api_calls"]
    def claim_token(self, cohort_fingerprint: str, total: int) -> int:
        with self.lock:
            cohorts = self.data.setdefault("cohorts", {})
            state = cohorts.setdefault(cohort_fingerprint, {"next_index": 0, "total": total})
            if state.get("total") != total: raise SafetyError("Cohort size changed for an existing fingerprint")
            index = int(state.get("next_index", 0))
            if index >= total: raise BudgetExceeded("Token cohort is exhausted")
            state["next_index"] = index + 1; self._write(); return index
    def tokens_remaining(self, cohort_fingerprint: str, total: int) -> int:
        state = self.data.get("cohorts", {}).get(cohort_fingerprint, {})
        return max(0, total - int(state.get("next_index", 0)))
    def close(self) -> None:
        if getattr(self, "fd", None) is not None:
            fcntl.flock(self.fd, fcntl.LOCK_UN); os.close(self.fd); self.fd = None
    def __enter__(self): return self
    def __exit__(self, *_): self.close()


class Metrics:
    def __init__(self):
        self.lock = threading.Lock(); self.latencies = defaultdict(list); self.statuses = defaultdict(lambda: defaultdict(int)); self.timeouts = 0; self.unexpected = 0; self.calls = 0; self.flows = 0
    def record(self, label: str, elapsed_ms: float, status: int, expected: tuple[int, ...]) -> None:
        with self.lock:
            self.calls += 1; self.latencies[label].append(elapsed_ms); self.statuses[label][str(status)] += 1
            if status not in expected and status != 429: self.unexpected += 1
    def timeout(self, label: str) -> None:
        with self.lock: self.calls += 1; self.timeouts += 1; self.statuses[label]["timeout"] += 1; self.unexpected += 1
    def flow(self) -> None:
        with self.lock: self.flows += 1
    def report(self, elapsed: float) -> dict:
        endpoints = {}
        for label, values in self.latencies.items():
            endpoints[label] = {"count": len(values), "p50_ms": percentile(values, .50), "p95_ms": percentile(values, .95), "p99_ms": percentile(values, .99), "statuses": dict(self.statuses[label])}
        count_429 = sum(int(values.get("429", 0)) for values in self.statuses.values())
        return {"api_calls": self.calls, "flows_completed": self.flows, "rps": round(self.calls / max(.001, elapsed), 2), "unexpected_failures": self.unexpected, "rate_limited_429": count_429, "timeouts": self.timeouts, "endpoints": endpoints}


class Client:
    def __init__(self, base_url: str, ledger: BudgetLedger, metrics: Metrics, timeout: float, stop: threading.Event, deadline: float):
        self.base_url, self.ledger, self.metrics, self.timeout, self.stop = base_url, ledger, metrics, timeout, stop
        self.deadline = deadline; self.stage_metrics = None
        self.context = ssl.create_default_context()

    def request(self, method: str, path: str, token: str | None = None, body: dict | None = None, expected=(200,), serious_5xx=True) -> tuple[int, dict]:
        if self.stop.is_set(): raise SeriousFailure("Run stopped")
        remaining = self.deadline - time.monotonic()
        if remaining <= 0: self.stop.set(); raise SeriousFailure("Cumulative run deadline reached")
        self.ledger.consume_call()
        label = endpoint_label(method, path); headers = {"Accept": "application/json"}
        payload = None
        if token: headers["Authorization"] = "Bearer " + token
        if body is not None: headers["Content-Type"] = "application/json"; payload = json.dumps(body, separators=(",", ":")).encode()
        request = urllib.request.Request(self.base_url + path, data=payload, headers=headers, method=method)
        started = time.perf_counter(); status = 0; data = {}
        try:
            with urllib.request.urlopen(request, timeout=max(.1, min(self.timeout, remaining)), context=self.context) as response:
                status = response.status; data = json.loads(response.read(1_000_000) or b"{}")
        except urllib.error.HTTPError as error:
            status = error.code
            try: data = json.loads(error.read(65536) or b"{}")
            except Exception: data = {}
        except (TimeoutError, urllib.error.URLError):
            self.metrics.timeout(label)
            if self.stage_metrics: self.stage_metrics.timeout(label)
            raise
        elapsed = (time.perf_counter() - started) * 1000
        self.metrics.record(label, elapsed, status, expected)
        if self.stage_metrics: self.stage_metrics.record(label, elapsed, status, expected)
        if serious_5xx and status >= 500:
            self.stop.set(); raise SeriousFailure("Server 5xx safety stop")
        if token and status in (401, 403):
            self.stop.set(); raise SeriousFailure("A valid cohort token was rejected")
        if status == 429: raise RateLimited("Rate limited")
        if status not in expected: raise UnexpectedResponse("Unexpected HTTP response")
        return status, data


def load_tokens(path: Path, mode: str, expected_ref: str = EXPECTED_PROJECT_REF) -> list[str]:
    if path.is_symlink(): raise SafetyError("Token input must not be a symlink")
    if stat.S_IMODE(path.stat().st_mode) & 0o077: raise SafetyError("Token input permissions must not allow group or world access")
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or data.get("schema") != "dino-load-cohort-v1": raise SafetyError("Token input schema must be dino-load-cohort-v1")
    expected_environment = "preview" if mode == "remote" else ("local", "test")
    if mode == "remote" and (data.get("environment") != expected_environment or data.get("project_ref") != expected_ref): raise SafetyError("Token cohort does not match the approved Preview database")
    if mode == "local" and data.get("environment") not in expected_environment: raise SafetyError("Token cohort is not local/test")
    raw = data.get("tokens")
    if not isinstance(raw, list) or any(not isinstance(x, str) or len(x) < 16 for x in raw): raise SafetyError("Token file must contain private participant tokens")
    if len(raw) != len(set(raw)): raise SafetyError("Token file contains duplicates")
    if mode == "remote" and len(raw) < 5000: raise SafetyError("Remote load requires 5,000 pre-seeded participant tokens")
    return raw


def cohort_fingerprint(tokens: list[str]) -> str:
    digest = hashlib.sha256()
    for token in tokens: digest.update(len(token).to_bytes(4, "big")); digest.update(token.encode())
    return digest.hexdigest()


def legal_no_jump(seed: int) -> tuple[int, int, float]:
    _, score, ticks, _ = game_verifier.simulate_and_verify(seed, [], 0, game_verifier.MAX_TICKS)
    valid, exact_score, exact_ticks, reason = game_verifier.simulate_and_verify(seed, [], score, ticks)
    if not valid or reason != "VERIFIED" or exact_ticks != ticks: raise SeriousFailure("Local verifier could not produce a legal collision")
    return exact_score, exact_ticks, exact_ticks / game_verifier.TICK_RATE + 0.2


def security_probe(client: Client, tokens: list[str], cohort: str) -> None:
    try: status, _ = client.request("GET", "/api/me", expected=(401,), serious_5xx=True)
    except UnexpectedResponse as error: client.stop.set(); raise SeriousFailure("Unauthenticated /api/me was not rejected") from error
    if status != 401: client.stop.set(); raise SeriousFailure("Unauthenticated /api/me was not rejected")
    if len(tokens) < 2: return
    first_index = client.ledger.claim_token(cohort, len(tokens)); second_index = client.ledger.claim_token(cohort, len(tokens))
    first_token, second_token = tokens[first_index], tokens[second_index]
    key = "probe_" + uuid.uuid4().hex
    status, created = client.request("POST", "/api/game-sessions", first_token, {"idempotency_key": key}, expected=(200, 201))
    if status not in (200, 201) or not created.get("session_id"): raise SeriousFailure("Security probe session creation failed")
    session_id = created["session_id"]
    try: status, _ = client.request("GET", f"/api/game-sessions/{urllib.parse.quote(session_id)}", second_token, expected=(404,))
    except UnexpectedResponse as error: client.stop.set(); raise SeriousFailure("Cross-participant session access was not hidden") from error
    if status != 404: client.stop.set(); raise SeriousFailure("Cross-participant session access was not hidden")
    client.request("POST", f"/api/game-sessions/{urllib.parse.quote(session_id)}/abort", first_token, {}, expected=(200,))


def user_flow(client: Client, token: str, sequence: int, version: str) -> None:
    key = "load_" + uuid.uuid4().hex
    _, created = client.request("POST", "/api/game-sessions", token, {"idempotency_key": key}, expected=(200, 201))
    session_id, seed = created.get("session_id"), created.get("seed")
    if not isinstance(session_id, str) or type(seed) is not int: raise SeriousFailure("Invalid session create shape")
    client.request("POST", f"/api/game-sessions/{urllib.parse.quote(session_id)}/start", token, {}, expected=(200,))
    score, ticks, wait_seconds = legal_no_jump(seed)
    deadline = min(time.monotonic() + wait_seconds, client.deadline)
    while time.monotonic() < deadline:
        if client.stop.wait(min(.25, deadline - time.monotonic())): raise SeriousFailure("Run stopped")
    if time.monotonic() >= client.deadline:
        client.stop.set(); raise SeriousFailure("Cumulative run deadline reached")
    finish_body = {"score": score, "valid_ticks": ticks, "jump_ticks": [], "version": version}
    _, finished = client.request("POST", f"/api/game-sessions/{urllib.parse.quote(session_id)}/finish", token, finish_body, expected=(200,))
    if finished.get("eligible_for_draw") is not True or finished.get("verification_result") != "VERIFIED": client.stop.set(); raise SeriousFailure("Legal game result was rejected")
    _, draw = client.request("POST", "/api/draws", token, {"session_id": session_id, "pouch_index": sequence % 3}, expected=(200, 201))
    _, retry = client.request("POST", "/api/draws", token, {"session_id": session_id, "pouch_index": sequence % 3}, expected=(200, 201))
    if draw.get("draw_id") != retry.get("draw_id") or draw.get("claim_id") != retry.get("claim_id"): client.stop.set(); raise SeriousFailure("Draw retry changed immutable result")
    draw_id = draw.get("draw_id")
    if not isinstance(draw_id, str): raise SeriousFailure("Invalid draw response")
    client.request("PATCH", f"/api/draws/{urllib.parse.quote(draw_id)}/scratch-complete", token, {}, expected=(200,))
    claim_id = draw.get("claim_id")
    if claim_id and sequence % 10 == 0:
        claim_path = f"/api/claims/{urllib.parse.quote(claim_id)}/submit"
        claim_body = {"recipient_name": "TEST_LOAD_USER", "contact_phone": "01000000000", "shipping_address": "TEST_LOAD_ADDRESS", "consent": True}
        _, first = client.request("POST", claim_path, token, claim_body, expected=(200,))
        _, second = client.request("POST", claim_path, token, claim_body, expected=(200,))
        if first.get("status") != second.get("status") or first.get("coupon_code") != second.get("coupon_code"): client.stop.set(); raise SeriousFailure("Claim retry changed immutable result")
    client.request("GET", "/api/leaderboard?limit=20", token, expected=(200,))
    event = {"event_id": "evt_load_" + uuid.uuid4().hex, "event_name": "page_view", "screen": "game", "channel": "load_test"}
    client.request("POST", "/api/events", token, {"events": [event]}, expected=(202,))
    client.metrics.flow()


def run_stage(client: Client, tokens: list[str], cohort: str, concurrency: int, duration: int, burst: bool, version: str, sequence_counter: list[int], counter_lock: threading.Lock, think_time: float) -> dict:
    started = time.monotonic(); deadline = started + duration; stage_metrics = Metrics(); client.stage_metrics = stage_metrics
    barrier = threading.Barrier(concurrency) if burst else None
    def worker():
        if barrier:
            try: barrier.wait(timeout=10)
            except threading.BrokenBarrierError: return
        while time.monotonic() < deadline and not client.stop.is_set():
            try: token_index = client.ledger.claim_token(cohort, len(tokens)); token = tokens[token_index]
            except BudgetExceeded: break
            with counter_lock: sequence_counter[0] += 1; sequence = sequence_counter[0]
            try:
                user_flow(client, token, sequence, version)
            except BudgetExceeded: client.stop.set(); break
            except SeriousFailure: client.stop.set(); break
            except (RateLimited, UnexpectedResponse): pass
            except (urllib.error.URLError, TimeoutError): pass
            except Exception:
                with client.metrics.lock: client.metrics.unexpected += 1
                client.stop.set(); break
            remaining = deadline - time.monotonic()
            if remaining > 0: client.stop.wait(min(think_time, remaining))
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="phase1-load") as pool:
        futures = [pool.submit(worker) for _ in range(concurrency)]
        remaining = deadline - time.monotonic()
        if remaining > 0 and not client.stop.wait(remaining): pass
        concurrent.futures.wait(futures, timeout=max(1, client.timeout + 2))
    elapsed = time.monotonic() - started
    client.stage_metrics = None
    return {"virtual_users": concurrency, "planned_seconds": duration, "actual_seconds": round(elapsed, 2), "burst": burst, "metrics": stage_metrics.report(elapsed), "stopped_early": client.stop.is_set() and elapsed + .5 < duration}


def preflight(client: Client, mode: str, expected_ref: str) -> tuple[dict, dict, dict]:
    _, health = client.request("GET", "/api/health", expected=(200,))
    _, config = client.request("GET", "/api/config", expected=(200,))
    _, campaign = client.request("GET", "/api/campaign", expected=(200,))
    validate_preflight(mode, health, config, campaign, expected_ref)
    return health, config, campaign


def write_private_json(path: Path, data: dict) -> None:
    if path.is_symlink(): raise SafetyError("Report path must not be a symlink")
    encoded = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True).encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try: os.chmod(path, 0o600); os.write(fd, encoded); os.fsync(fd)
    finally: os.close(fd)


def estimate_profile(profile: str, think_time: float) -> dict:
    """Return conservative request envelopes; these are traffic estimates, never price quotes."""
    if think_time <= 0: raise SafetyError("Think time must be positive")
    stages = []
    for virtual_users, seconds, burst in PROFILES[profile]:
        flows = virtual_users * math.ceil(seconds / think_time)
        stages.append({"virtual_users": virtual_users, "seconds": seconds, "burst": burst, "flow_attempts_ceiling": flows, "absolute_api_calls_ceiling": flows * 11})
    flows = sum(stage["flow_attempts_ceiling"] for stage in stages)
    claim_flows = flows // 10
    # Current flow: 8 base calls; at most two claim retry calls every tenth sequence.
    script_calls = 7 + flows * 8 + claim_flows * 2
    return {
        "stages": stages,
        "flow_attempts_ceiling": flows,
        "claim_flow_attempts_ceiling": claim_flows,
        "cohort_tokens_required_ceiling": flows + 2,
        "script_api_calls_ceiling": script_calls,
        "absolute_api_calls_ceiling": 7 + flows * 11,
        "mutating_api_requests_ceiling": 2 + flows * 7 + claim_flows * 2,
        "client_analytics_events_ceiling": flows,
        "server_domain_event_attempts_ceiling": flows * 3 + claim_flows,
    }


def dry_run(profile: str, token_count: int = 5000, think_time: float = 45.0) -> dict:
    estimate = estimate_profile(profile, think_time)
    return {"profile": profile, "stages": estimate.pop("stages"), "planned_duration_seconds": sum(x[1] for x in PROFILES[profile]), "reserved_duration_seconds": reserved_duration(profile), "think_time_seconds": think_time, "prepared_cohort_tokens": token_count, **estimate, "within_hard_api_call_cap": estimate["absolute_api_calls_ceiling"] <= MAX_API_CALLS, "within_prepared_cohort": estimate["cohort_tokens_required_ceiling"] <= token_count, "hard_api_call_ceiling": MAX_API_CALLS, "traffic_estimate_note": "API requests, mutation requests, and event attempts are conservative test-volume envelopes, not database-row counts or monetary price estimates.", "external_analytics_events": 0, "real_prizes": False}


def reserved_duration(profile: str) -> int:
    """Reserve and enforce stage time plus bounded preflight and worker cleanup."""
    return sum(stage[1] for stage in PROFILES[profile]) + RUN_OVERHEAD_SECONDS


def safe_failure(error: BaseException) -> dict:
    if isinstance(error, SafetyError):
        return {"type": type(error).__name__, "reason": str(error)}
    if isinstance(error, (TimeoutError, urllib.error.URLError)):
        return {"type": type(error).__name__, "reason": "Network preflight or request failed"}
    return {"type": type(error).__name__, "reason": "Load run failed"}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("local", "remote"), default="local")
    parser.add_argument("--base-url")
    parser.add_argument("--profile", choices=tuple(PROFILES), default="smoke10")
    parser.add_argument("--tokens", type=Path)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--expected-project-ref", default=EXPECTED_PROJECT_REF)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--think-time", type=float, default=45.0, help="Seconds between fresh-token user-flow attempts (minimum 10; failures are paced too)")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.dry_run:
        count = len(load_tokens(args.tokens, args.mode, args.expected_project_ref)) if args.tokens else 5000
        print(json.dumps(dry_run(args.profile, count, args.think_time), ensure_ascii=False, indent=2)); return 0
    if not all((args.base_url, args.tokens, args.ledger, args.report)): raise SafetyError("Actual runs require explicit --base-url, --tokens, --ledger, and --report")
    if args.think_time < 10: raise SafetyError("Think time must be at least 10 seconds")
    base_url = validate_target(args.base_url, args.mode); token_values = load_tokens(args.tokens, args.mode, args.expected_project_ref)
    planned_duration = sum(stage[1] for stage in PROFILES[args.profile]); reserved = reserved_duration(args.profile)
    stop = threading.Event(); metrics = Metrics(); cohort = cohort_fingerprint(token_values)
    with BudgetLedger(args.ledger) as ledger:
        estimate = estimate_profile(args.profile, args.think_time)
        if estimate["absolute_api_calls_ceiling"] > ledger.remaining_calls: raise BudgetExceeded("Conservative API-call envelope exceeds the cumulative remaining budget")
        if estimate["cohort_tokens_required_ceiling"] > ledger.tokens_remaining(cohort, len(token_values)): raise BudgetExceeded("Fresh-token cohort is too small for the conservative flow envelope")
        ledger.reserve_duration(reserved, args.profile)
        started = time.monotonic(); client = Client(base_url, ledger, metrics, args.timeout, stop, started + reserved)
        health = config = campaign = None; stage_reports = []; failure = None
        try:
            health, config, campaign = preflight(client, args.mode, args.expected_project_ref)
            security_probe(client, token_values, cohort)
            sequence, sequence_lock = [0], threading.Lock()
            for concurrency, duration, burst in PROFILES[args.profile]:
                if stop.is_set(): break
                stage_reports.append(run_stage(client, token_values, cohort, concurrency, duration, burst, campaign["game_version"], sequence, sequence_lock, args.think_time))
        except BaseException as error:
            stop.set(); failure = safe_failure(error)
        elapsed = time.monotonic() - started
        target = {"host": urllib.parse.urlsplit(base_url).hostname, "environment": config.get("environment") if config else None, "project_ref": health.get("project_ref") if health else None, "synthetic_only": health.get("synthetic_only") if health else None, "real_prizes_enabled": campaign.get("real_prizes_enabled") if campaign else None}
        report = {"profile": args.profile, "mode": args.mode, "target": target, "planned_duration_seconds": planned_duration, "reserved_duration_seconds": reserved, "think_time_seconds": args.think_time, "plan_envelope": estimate, "actual_elapsed_seconds": round(elapsed,2), "stages": stage_reports, "metrics": metrics.report(elapsed), "budget": {"api_calls_used_cumulative": ledger.data["api_calls"], "duration_seconds_reserved_cumulative": ledger.data["duration_seconds"], "api_calls_remaining": ledger.remaining_calls}, "tokens_remaining": ledger.tokens_remaining(cohort, len(token_values)), "serious_stop": stop.is_set(), "failure": failure}
        write_private_json(args.report, report)
        if stop.is_set(): return 2
    return 0


if __name__ == "__main__":
    try: raise SystemExit(main())
    except SafetyError as error:
        print(json.dumps({"error": type(error).__name__, "message": str(error)}, ensure_ascii=False), file=sys.stderr); raise SystemExit(2)
