#!/usr/bin/env python3
"""Bounded Phase 1 Preview load runner.

The runner is deliberately fail-closed: it never targets Production, never creates
participants, never bypasses game verification, and never resets its cumulative
request/time ledger.  Remote execution is an operator action; ``--dry-run`` is
network-free and is the default verification path in CI.
"""
from __future__ import annotations

import argparse
import copy
import concurrent.futures
import datetime as dt
import fcntl
import hashlib
import json
import math
import os
import re
import ssl
import stat
import sys
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
sys.path.insert(0, str(ROOT / "server"))
import game_verifier  # noqa: E402

EXPECTED_PROJECT_REF = "igfrnexknwtiljdqjrbp"
EXPECTED_SCHEMA = "dino_dev"
COOKIE_NAME = "dj_session"
GAME_VERSION = "1.2.0"
MAX_COHORT_SIZE = 5_000
MAX_API_CALLS = 30_000
# 2026-09-25: user approved a 40-minute cumulative limit; call cap is unchanged.
MAX_DURATION_SECONDS = 40 * 60
RUN_OVERHEAD_SECONDS = 90
DEFAULT_THINK_TIME_SECONDS = 45.0
PLAY_WAIT_GRACE_SECONDS = 0.25

# (virtual users, stage seconds, simultaneous launch)
PROFILES = {
    "smoke10": ((10, 15, False),),
    "10": ((10, 60, False),),
    "50": ((50, 120, False),),
    "100": ((100, 180, False),),
    "200": ((200, 300, False),),
    "burst": ((200, 30, True),),
    "full": (
        (10, 60, False),
        (50, 120, False),
        (100, 180, False),
        (200, 300, False),
        (200, 30, True),
    ),
}

BASE_FLOW_CALLS = 10
BASE_FLOW_MUTATIONS = 7
CLAIM_RETRY_CALLS = 2
CLAIM_EVERY_N_FLOWS = 20
PREFLIGHT_AND_SECURITY_CALLS = 19
INVITATION_PROBE_CALLS = 4


class SafetyError(RuntimeError):
    pass


class BudgetExceeded(SafetyError):
    pass


class SeriousFailure(SafetyError):
    pass


class RateLimited(SafetyError):
    pass


class UnexpectedResponse(SafetyError):
    pass


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1))
    return round(ordered[index], 2)


def endpoint_label(method: str, path: str) -> str:
    clean = urllib.parse.urlsplit(path).path
    clean = re.sub(r"/api/game-sessions/[^/]+", "/api/game-sessions/{id}", clean)
    clean = re.sub(r"/api/draws/[^/]+", "/api/draws/{id}", clean)
    clean = re.sub(r"/api/claims/[^/]+", "/api/claims/{id}", clean)
    return f"{method.upper()} {clean}"


def validate_target(base_url: str, mode: str) -> str:
    parsed = urllib.parse.urlsplit(base_url)
    if (
        parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise SafetyError("Base URL must be one explicit origin without credentials or a path")
    hostname = (parsed.hostname or "").lower()
    if mode == "remote":
        if (
            parsed.scheme != "https"
            or parsed.port not in (None, 443)
            or not hostname.endswith(".vercel.app")
            or hostname == "vercel.app"
        ):
            raise SafetyError("Remote target must be an explicit HTTPS Vercel deployment origin")
    elif parsed.scheme != "http" or hostname not in ("127.0.0.1", "localhost", "::1"):
        raise SafetyError("Local target must be a loopback HTTP origin")
    return base_url.rstrip("/")


def project_ref_from_config(config: dict[str, Any]) -> str | None:
    auth = config.get("auth")
    if not isinstance(auth, dict):
        return None
    try:
        host = urllib.parse.urlsplit(str(auth.get("supabase_url", ""))).hostname or ""
    except ValueError:
        return None
    suffix = ".supabase.co"
    return host[: -len(suffix)] if host.endswith(suffix) else None


def validate_preflight(
    mode: str,
    health: dict[str, Any],
    config: dict[str, Any],
    expected_project_ref: str,
    expected_deployment_id: str | None,
    expected_campaign_id: str,
    require_last_stock: bool = False,
) -> None:
    if health.get("ok") is not True or health.get("database") != "ready":
        raise SafetyError("Health check is not database-backed and ready")
    if health.get("service") != "gemini-dino-jump":
        raise SafetyError("Unexpected service identity")
    campaign = config.get("campaign")
    if not isinstance(campaign, dict):
        raise SafetyError("Safe campaign configuration is missing")
    if campaign.get("id") != expected_campaign_id or campaign.get("status") != "ACTIVE":
        raise SafetyError("The prepared test campaign is not active")
    if campaign.get("game_version") != GAME_VERSION:
        raise SafetyError("Game version mismatch")

    environment = health.get("environment")
    if environment == "production":
        raise SafetyError("Production targets are forbidden")
    if mode == "remote":
        required = {
            "environment": "preview",
            "project_ref": expected_project_ref,
            "schema": EXPECTED_SCHEMA,
            "synthetic_only": True,
            "test_seed": True,
            "deployment": expected_deployment_id,
        }
        for key, expected in required.items():
            if expected is None or health.get(key) != expected:
                raise SafetyError(f"Preview guard mismatch: {key}")
        if project_ref_from_config(config) != expected_project_ref:
            raise SafetyError("Public configuration points at another Supabase project")
    elif environment not in ("local", "test"):
        raise SafetyError("Local target reports a non-local environment")
    if require_last_stock and health.get("test_inventory_remaining") != 1:
        raise SafetyError("Last-stock probe requires exactly one prepared synthetic item")


class BudgetLedger:
    """Exclusive, durable cumulative admission ledger with no reset operation."""

    def __init__(self, path: Path):
        self.path = path
        if path.exists() and path.is_symlink():
            raise SafetyError("Ledger must not be a symlink")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path = path.with_name(path.name + ".lock")
        if self.lock_path.exists() and self.lock_path.is_symlink():
            raise SafetyError("Ledger lock must not be a symlink")
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        self.fd = os.open(self.lock_path, flags, 0o600)
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            os.close(self.fd)
            self.fd = None
            raise SafetyError("Another load run already owns this ledger") from error
        self.lock = threading.Lock()
        os.chmod(self.lock_path, 0o600)
        if stat.S_IMODE(os.fstat(self.fd).st_mode) != 0o600:
            raise SafetyError("Ledger lock permissions must be 0600")
        self.data = self._read()
        if not path.exists():
            self._write()

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            raw = b""
        else:
            if self.path.is_symlink() or stat.S_IMODE(self.path.stat().st_mode) != 0o600:
                raise SafetyError("Ledger must be a private regular file")
            raw = self.path.read_bytes()
            if len(raw) > 1_000_000:
                raise SafetyError("Ledger is unexpectedly large")
        if not raw:
            return {
                "version": 2,
                "admitted_api_calls": 0,
                "completed_api_calls": 0,
                "duration_reserved_seconds": 0,
                "runs": [],
                "cohorts": {},
                "external_cohort_calls": {},
            }
        data = json.loads(raw)
        if data.get("version") != 2:
            raise SafetyError("Unsupported budget ledger version; preserve it and use a new ledger")
        integer_fields = ("admitted_api_calls", "completed_api_calls", "duration_reserved_seconds")
        if any(type(data.get(key)) is not int or data[key] < 0 for key in integer_fields):
            raise SafetyError("Invalid budget ledger")
        if data["completed_api_calls"] > data["admitted_api_calls"]:
            raise SafetyError("Ledger completion count exceeds admissions")
        return data

    def _replace_data(self, data: dict[str, Any]) -> None:
        payload = json.dumps(data, separators=(",", ":"), sort_keys=True).encode()
        temporary = self.path.with_name(
            f".{self.path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
        )
        temp_fd = None
        try:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            temp_fd = os.open(temporary, flags, 0o600)
            written = 0
            while written < len(payload):
                written += os.write(temp_fd, payload[written:])
            os.fsync(temp_fd)
            os.close(temp_fd)
            temp_fd = None
            os.replace(temporary, self.path)
            os.chmod(self.path, 0o600)
            directory_fd = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if temp_fd is not None:
                os.close(temp_fd)
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    def _write(self) -> None:
        self._replace_data(self.data)

    def redeployment_state(
        self,
        old_fingerprint: str,
        new_fingerprint: str,
        proof: dict[str, Any],
    ) -> str:
        migrations = self.data.get("redeployment_migrations", [])
        matching = [
            item
            for item in migrations
            if item.get("old_fingerprint") == old_fingerprint
            and item.get("new_fingerprint") == new_fingerprint
        ]
        if matching:
            if len(matching) != 1 or any(
                matching[0].get(key) != proof.get(key)
                for key in (
                    "old_deployment_id",
                    "new_deployment_id",
                    "old_base_url",
                    "new_base_url",
                    "project_ref",
                    "schema",
                    "campaign_id",
                    "participant_identity_sha256",
                )
            ):
                raise SafetyError("Redeployment migration audit proof changed")
            if old_fingerprint in self.data.get("cohorts", {}) or new_fingerprint not in self.data.get("cohorts", {}):
                raise SafetyError("Redeployment migration ledger state is inconsistent")
            return "completed"
        cohorts = self.data.get("cohorts", {})
        if old_fingerprint not in cohorts:
            raise SafetyError("Original cohort cursor is missing from the ledger")
        if new_fingerprint in cohorts:
            raise SafetyError("New deployment cohort cursor already exists without an audit record")
        return "pending"

    def migrate_redeployment(
        self,
        old_fingerprint: str,
        new_fingerprint: str,
        proof: dict[str, Any],
    ) -> None:
        with self.lock:
            if (
                proof.get("old_cohort_fingerprint") != old_fingerprint
                or proof.get("new_cohort_fingerprint") != new_fingerprint
            ):
                raise SafetyError("Redeployment cohort identity proof does not match")
            state = self.redeployment_state(old_fingerprint, new_fingerprint, proof)
            if state == "completed":
                return
            candidate = copy.deepcopy(self.data)
            cursor = candidate["cohorts"].pop(old_fingerprint)
            candidate["cohorts"][new_fingerprint] = cursor
            external = candidate.setdefault("external_cohort_calls", {})
            if old_fingerprint in external:
                if new_fingerprint in external:
                    raise SafetyError("Redeployment preparation accounting already exists")
                external[new_fingerprint] = external.pop(old_fingerprint)
            audit = dict(proof)
            audit.update(
                {
                    "old_fingerprint": old_fingerprint,
                    "new_fingerprint": new_fingerprint,
                    "cursor_at_migration": int(cursor.get("next_index", 0)),
                    "cohort_total": int(cursor.get("total", 0)),
                    "migrated_at": int(time.time()),
                }
            )
            candidate.setdefault("redeployment_migrations", []).append(audit)
            self._replace_data(candidate)
            self.data = candidate

    def reserve_run(
        self,
        seconds: int,
        profile: str,
        cohort_fingerprint: str,
        deployment_id: str | None,
    ) -> None:
        with self.lock:
            used = self.data["duration_reserved_seconds"]
            if used + seconds > MAX_DURATION_SECONDS:
                raise BudgetExceeded(f"Cumulative {MAX_DURATION_SECONDS // 60}-minute duration budget exceeded")
            self.data["duration_reserved_seconds"] = used + seconds
            self.data["runs"].append(
                {
                    "profile": profile,
                    "duration_reserved_seconds": seconds,
                    "cohort_fingerprint": cohort_fingerprint,
                    "deployment_id": deployment_id,
                    "started_at": int(time.time()),
                }
            )
            self._write()

    def admit_call(self) -> None:
        with self.lock:
            if self.data["admitted_api_calls"] >= MAX_API_CALLS:
                raise BudgetExceeded("Cumulative 30,000 API-call budget exhausted")
            self.data["admitted_api_calls"] += 1
            self._write()

    def complete_call(self) -> None:
        with self.lock:
            self.data["completed_api_calls"] += 1
            self._write()

    def claim_participant(self, fingerprint: str, total: int, campaign_id: str) -> int:
        with self.lock:
            if any(
                item.get("old_fingerprint") == fingerprint
                for item in self.data.get("redeployment_migrations", [])
            ):
                raise SafetyError("Original deployment cohort cursor is retired")
            cohorts = self.data.setdefault("cohorts", {})
            state = cohorts.setdefault(
                fingerprint,
                {"next_index": 0, "total": total, "campaign_id": campaign_id},
            )
            if state.get("total") != total or state.get("campaign_id") != campaign_id:
                raise SafetyError("Cohort identity changed for an existing fingerprint")
            index = int(state.get("next_index", 0))
            if index >= total:
                raise BudgetExceeded("Fresh synthetic cohort is exhausted")
            state["next_index"] = index + 1
            self._write()
            return index

    def register_cohort_preparation(self, fingerprint: str, api_calls: int) -> None:
        """Charge already-completed API preparation once to the same phase cap."""
        if type(api_calls) is not int or api_calls < 0:
            raise SafetyError("Cohort preparation_api_calls must be a non-negative integer")
        with self.lock:
            if any(
                item.get("old_fingerprint") == fingerprint
                for item in self.data.get("redeployment_migrations", [])
            ):
                raise SafetyError("Original deployment cohort cursor is retired")
            charged = self.data.setdefault("external_cohort_calls", {})
            existing = charged.get(fingerprint)
            if existing is not None:
                if existing != api_calls:
                    raise SafetyError("Cohort preparation call count changed for an existing fingerprint")
                return
            if self.data["admitted_api_calls"] + api_calls > MAX_API_CALLS:
                raise BudgetExceeded("Cohort preparation exceeds the cumulative API-call budget")
            self.data["admitted_api_calls"] += api_calls
            self.data["completed_api_calls"] += api_calls
            charged[fingerprint] = api_calls
            self._write()

    def participants_remaining(self, fingerprint: str, total: int) -> int:
        if any(
            item.get("old_fingerprint") == fingerprint
            for item in self.data.get("redeployment_migrations", [])
        ):
            return 0
        state = self.data.get("cohorts", {}).get(fingerprint, {})
        return max(0, total - int(state.get("next_index", 0)))

    @property
    def remaining_calls(self) -> int:
        return MAX_API_CALLS - self.data["admitted_api_calls"]

    def close(self) -> None:
        if getattr(self, "fd", None) is not None:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
            os.close(self.fd)
            self.fd = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class Metrics:
    def __init__(self):
        self.lock = threading.Lock()
        self.latencies: dict[str, list[float]] = defaultdict(list)
        self.phase_latencies: dict[str, list[float]] = defaultdict(list)
        self.statuses: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self.calls = 0
        self.flows = 0
        self.timeouts = 0
        self.unexpected = 0
        self.expected_negatives = 0

    def record(
        self,
        label: str,
        phase: str,
        elapsed_ms: float,
        status: int,
        expected: tuple[int, ...],
        expected_negative: bool,
    ) -> None:
        with self.lock:
            self.calls += 1
            self.latencies[label].append(elapsed_ms)
            self.phase_latencies[phase].append(elapsed_ms)
            self.statuses[label][str(status)] += 1
            if expected_negative and status in expected:
                self.expected_negatives += 1
            elif status not in expected and status != 429:
                self.unexpected += 1

    def timeout(self, label: str, phase: str) -> None:
        with self.lock:
            self.calls += 1
            self.timeouts += 1
            self.unexpected += 1
            self.statuses[label]["timeout"] += 1
            self.phase_latencies[phase].append(float("inf"))

    def flow(self) -> None:
        with self.lock:
            self.flows += 1

    @staticmethod
    def _latency_summary(values: list[float]) -> dict[str, Any]:
        finite = [value for value in values if math.isfinite(value)]
        return {
            "count": len(values),
            "p50_ms": percentile(finite, 0.50),
            "p95_ms": percentile(finite, 0.95),
            "p99_ms": percentile(finite, 0.99),
        }

    def report(self, elapsed: float) -> dict[str, Any]:
        endpoints = {}
        for label, values in self.latencies.items():
            endpoints[label] = {
                **self._latency_summary(values),
                "statuses": dict(self.statuses[label]),
            }
        phases = {
            phase: self._latency_summary(values)
            for phase, values in self.phase_latencies.items()
        }
        rate_limited = sum(int(values.get("429", 0)) for values in self.statuses.values())
        return {
            "api_calls": self.calls,
            "flows_completed": self.flows,
            "rps": round(self.calls / max(elapsed, 0.001), 2),
            "unexpected_failures": self.unexpected,
            "expected_negative_responses": self.expected_negatives,
            "rate_limited_429": rate_limited,
            "timeouts": self.timeouts,
            "endpoints": endpoints,
            "phases": phases,
        }


def read_private_text(path: Path, label: str) -> str:
    if path.is_symlink():
        raise SafetyError(f"{label} must not be a symlink")
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise SafetyError(f"{label} permissions must be 0600")
    return path.read_text(encoding="utf-8").strip()


def load_cohort(
    path: Path,
    mode: str,
    base_url: str | None,
    expected_project_ref: str,
    expected_deployment_id: str | None,
) -> dict[str, Any]:
    data = json.loads(read_private_text(path, "Cohort file"))
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise SafetyError("Cohort schema_version must be 1")
    participants = data.get("participants")
    if not isinstance(participants, list) or not participants or len(participants) > MAX_COHORT_SIZE:
        raise SafetyError("Cohort must contain 1-5,000 synthetic participants")
    if mode == "remote" and len(participants) != MAX_COHORT_SIZE:
        raise SafetyError("Remote load requires exactly 5,000 prepared participants")
    cookie_pattern = re.compile(rf"^{COOKIE_NAME}=([A-Za-z0-9._~-]{{32,512}})$")
    cookies: list[str] = []
    participant_ids: list[str] = []
    for participant in participants:
        if not isinstance(participant, dict):
            raise SafetyError("Invalid participant entry")
        cookie = participant.get("cookie")
        participant_id = participant.get("participant_id")
        if not isinstance(cookie, str) or not cookie_pattern.fullmatch(cookie):
            raise SafetyError("Each participant needs one private dj_session cookie")
        if not isinstance(participant_id, str) or not participant_id:
            raise SafetyError("Each participant needs an opaque participant_id")
        referral_code = participant.get("referral_code")
        if referral_code is not None and (not isinstance(referral_code, str) or not referral_code):
            raise SafetyError("Invalid referral code")
        cookies.append(cookie)
        participant_ids.append(participant_id)
    if len(cookies) != len(set(cookies)) or len(participant_ids) != len(set(participant_ids)):
        raise SafetyError("Cohort contains duplicate identities")
    if not isinstance(data.get("campaign_id"), str) or not data["campaign_id"]:
        raise SafetyError("Cohort campaign_id is required")
    if type(data.get("preparation_api_calls", 0)) is not int or data.get("preparation_api_calls", 0) < 0:
        raise SafetyError("Cohort preparation_api_calls must be a non-negative integer")
    if mode == "remote":
        if data.get("environment") != "preview":
            raise SafetyError("Remote cohort is not marked Preview")
        if data.get("project_ref") != expected_project_ref:
            raise SafetyError("Remote cohort belongs to another Supabase project")
        if data.get("base_url") != base_url:
            raise SafetyError("Remote cohort belongs to another deployment origin")
        if not expected_deployment_id or data.get("deployment_id") != expected_deployment_id:
            raise SafetyError("Remote cohort belongs to another Vercel deployment")
    elif data.get("environment") not in ("local", "test"):
        raise SafetyError("Local cohort is not marked local/test")
    return data


def cohort_fingerprint(cohort: dict[str, Any]) -> str:
    digest = hashlib.sha256()
    for key in ("environment", "project_ref", "base_url", "deployment_id", "campaign_id"):
        digest.update(str(cohort.get(key, "")).encode())
        digest.update(b"\0")
    for participant in cohort["participants"]:
        for key in ("cookie", "participant_id", "referral_code"):
            digest.update(str(participant.get(key, "")).encode())
            digest.update(b"\0")
    return digest.hexdigest()


def participant_identity_fingerprint(cohort: dict[str, Any]) -> str:
    digest = hashlib.sha256()
    for participant in cohort["participants"]:
        for key in ("cookie", "participant_id", "referral_code"):
            digest.update(str(participant.get(key, "")).encode())
            digest.update(b"\0")
    return digest.hexdigest()


def retarget_cohort_for_redeployment(
    cohort: dict[str, Any],
    old_deployment_id: str,
    new_deployment_id: str,
    old_base_url: str,
    new_base_url: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    deployment_pattern = re.compile(r"^[A-Za-z0-9._-]{3,128}$")
    if (
        not deployment_pattern.fullmatch(old_deployment_id or "")
        or not deployment_pattern.fullmatch(new_deployment_id or "")
        or old_deployment_id == new_deployment_id
    ):
        raise SafetyError("Redeployment resume requires distinct explicit deployment IDs")
    if cohort.get("environment") != "preview" or cohort.get("deployment_id") != old_deployment_id:
        raise SafetyError("Cohort does not belong to the explicit original deployment")
    old_base_url = validate_target(old_base_url, "remote")
    new_base_url = validate_target(new_base_url, "remote")
    if old_base_url == new_base_url or cohort.get("base_url") != old_base_url:
        raise SafetyError("Redeployment resume requires distinct exact old and new Vercel origins")
    identity = participant_identity_fingerprint(cohort)
    retargeted = copy.deepcopy(cohort)
    retargeted["deployment_id"] = new_deployment_id
    retargeted["base_url"] = new_base_url
    if participant_identity_fingerprint(retargeted) != identity:
        raise SafetyError("Redeployment retarget changed participant identities")
    proof = {
        "old_deployment_id": old_deployment_id,
        "new_deployment_id": new_deployment_id,
        "old_base_url": old_base_url,
        "new_base_url": new_base_url,
        "project_ref": cohort.get("project_ref"),
        "schema": EXPECTED_SCHEMA,
        "campaign_id": cohort.get("campaign_id"),
        "participant_identity_sha256": identity,
        "old_cohort_fingerprint": cohort_fingerprint(cohort),
        "new_cohort_fingerprint": cohort_fingerprint(retargeted),
    }
    return retargeted, proof


def verify_redeployment_target(
    proof: dict[str, Any],
    health: dict[str, Any],
    config: dict[str, Any],
    base_url: str,
) -> None:
    campaign = config.get("campaign") if isinstance(config, dict) else None
    expected = {
        "new_deployment_id": health.get("deployment"),
        "new_base_url": validate_target(base_url, "remote"),
        "project_ref": health.get("project_ref"),
        "schema": health.get("schema"),
        "campaign_id": campaign.get("id") if isinstance(campaign, dict) else None,
    }
    for key, actual in expected.items():
        if proof.get(key) != actual:
            raise SafetyError(f"Redeployment proof mismatch: {key}")


class HttpClient:
    def __init__(
        self,
        base_url: str,
        ledger: BudgetLedger,
        metrics: Metrics,
        timeout: float,
        stop: threading.Event,
        deadline: float,
        protection_token: str | None = None,
        deployment_auth_cookie: str | None = None,
    ):
        self.base_url = base_url
        self.ledger = ledger
        self.metrics = metrics
        self.timeout = timeout
        self.stop = stop
        self.deadline = deadline
        self.protection_token = protection_token
        self.deployment_auth_cookie = deployment_auth_cookie
        self.context = ssl.create_default_context()
        self.stage_metrics: Metrics | None = None

    def request(
        self,
        method: str,
        path: str,
        phase: str,
        cookie: str | None = None,
        body: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        expected: tuple[int, ...] = (200,),
        expected_negative: bool = False,
    ) -> tuple[int, dict[str, Any]]:
        if self.stop.is_set():
            raise SeriousFailure("Run stopped")
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            self.stop.set()
            raise SeriousFailure("Reserved run deadline reached")
        self.ledger.admit_call()
        label = endpoint_label(method, path)
        headers = {"Accept": "application/json", "User-Agent": "dino-phase1-load/2"}
        if cookie:
            headers["Cookie"] = cookie
        if self.deployment_auth_cookie:
            headers["Cookie"] = "; ".join(
                value for value in (headers.get("Cookie"), self.deployment_auth_cookie) if value
            )
        if self.protection_token:
            headers["x-vercel-protection-bypass"] = self.protection_token
        payload = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            headers["Origin"] = self.base_url
            payload = json.dumps(body, separators=(",", ":")).encode()
        if method.upper() not in ("GET", "HEAD", "OPTIONS"):
            if not idempotency_key or not (8 <= len(idempotency_key) <= 128):
                raise SafetyError("Every mutation needs an 8-128 character idempotency key")
            headers["Idempotency-Key"] = idempotency_key
        request = urllib.request.Request(
            self.base_url + path,
            data=payload,
            headers=headers,
            method=method,
        )
        started = time.perf_counter()
        status = 0
        response_data: dict[str, Any] = {}
        try:
            with urllib.request.urlopen(
                request,
                timeout=max(0.1, min(self.timeout, remaining)),
                context=self.context,
            ) as response:
                if urllib.parse.urlsplit(response.geturl()).netloc != urllib.parse.urlsplit(self.base_url).netloc:
                    raise SeriousFailure("Request was redirected away from the approved deployment")
                status = response.status
                raw = response.read(1_000_001)
                if len(raw) > 1_000_000:
                    raise SeriousFailure("Response exceeded the 1 MB load-test bound")
                response_data = json.loads(raw or b"{}")
        except urllib.error.HTTPError as error:
            status = error.code
            try:
                response_data = json.loads(error.read(65_536) or b"{}")
            except (json.JSONDecodeError, ValueError):
                response_data = {}
        except (TimeoutError, urllib.error.URLError):
            self.metrics.timeout(label, phase)
            if self.stage_metrics:
                self.stage_metrics.timeout(label, phase)
            raise
        finally:
            # A call is complete only after an HTTP response was received. Admissions remain
            # permanently charged when the process dies or the network outcome is unknown.
            if status:
                self.ledger.complete_call()
        elapsed_ms = (time.perf_counter() - started) * 1000
        self.metrics.record(label, phase, elapsed_ms, status, expected, expected_negative)
        if self.stage_metrics:
            self.stage_metrics.record(label, phase, elapsed_ms, status, expected, expected_negative)

        if not isinstance(response_data, dict):
            raise UnexpectedResponse(f"Expected a JSON object from {label}")
        error_code = str(response_data.get("error", ""))
        if status >= 500:
            self.stop.set()
            raise SeriousFailure("Server 5xx safety stop")
        if cookie and status in (401, 403) and not expected_negative:
            self.stop.set()
            raise SeriousFailure("Prepared participant authentication was rejected")
        if "INVENTORY" in error_code or error_code in {"OUT_OF_STOCK", "STOCK_CONFLICT"}:
            self.stop.set()
            raise SeriousFailure("Inventory safety stop")
        if status == 429:
            raise RateLimited("Rate limited")
        if status not in expected:
            raise UnexpectedResponse(f"Unexpected HTTP status for {label}")
        return status, response_data


def event_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def legal_no_jump(seed: int) -> tuple[int, int, float]:
    sentinel_ticks = 60 * 600
    _, score, ticks, _ = game_verifier.simulate_and_verify(seed, [], 0, sentinel_ticks)
    valid, exact_score, exact_ticks, reason = game_verifier.simulate_and_verify(seed, [], score, ticks)
    if not valid or reason != "VERIFIED" or exact_score != score or exact_ticks != ticks:
        raise SeriousFailure("Local verifier could not construct a genuine collision result")
    return score, ticks, ticks / game_verifier.TICK_RATE + PLAY_WAIT_GRACE_SECONDS


def mutating_request(
    client: HttpClient,
    method: str,
    path: str,
    phase: str,
    cookie: str | None,
    body: dict[str, Any],
    expected: tuple[int, ...],
    key: str | None = None,
    expected_negative: bool = False,
) -> tuple[int, dict[str, Any]]:
    request_key = key or event_id("idem")
    return client.request(
        method,
        path,
        phase,
        cookie,
        body,
        request_key,
        expected,
        expected_negative,
    )


def preflight(
    client: HttpClient,
    mode: str,
    expected_project_ref: str,
    expected_deployment_id: str | None,
    campaign_id: str,
    require_last_stock: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    _, health = client.request("GET", "/api/health", "preflight")
    _, config = client.request("GET", "/api/config", "preflight")
    validate_preflight(
        mode,
        health,
        config,
        expected_project_ref,
        expected_deployment_id,
        campaign_id,
        require_last_stock,
    )
    return health, config


def security_probe(
    client: HttpClient,
    cohort: dict[str, Any],
    ledger: BudgetLedger,
    fingerprint: str,
) -> None:
    participants = cohort["participants"]
    campaign_id = cohort["campaign_id"]
    client.request("GET", "/api/me", "security", expected=(401,), expected_negative=True)
    first = participants[ledger.claim_participant(fingerprint, len(participants), campaign_id)]
    second = participants[ledger.claim_participant(fingerprint, len(participants), campaign_id)]
    _, me = client.request("GET", "/api/me", "security", first["cookie"])
    tickets = me.get("tickets", {})
    if tickets.get("initial") != 1 or tickets.get("invitation") != 0:
        raise SeriousFailure("Prepared participant does not have exactly one untouched initial ticket")

    observation_key = event_id("idem_probe")
    observation_id = event_id("obs_probe")
    body = {"observation_id": observation_id, "event_id": event_id("evt_probe")}
    first_status, first_body = mutating_request(
        client, "POST", "/api/observations", "security", None, body, (201,), observation_key
    )
    replay_status, replay_body = mutating_request(
        client, "POST", "/api/observations", "security", None, body, (201,), observation_key
    )
    if (first_status, first_body) != (replay_status, replay_body):
        raise SeriousFailure("Idempotent observation replay changed its response")
    conflict = {**body, "event_id": event_id("evt_probe_conflict")}
    mutating_request(
        client,
        "POST",
        "/api/observations",
        "security",
        None,
        conflict,
        (409,),
        observation_key,
        expected_negative=True,
    )

    create_event = event_id("evt_probe_create")
    _, created = mutating_request(
        client,
        "POST",
        "/api/game-sessions",
        "security",
        first["cookie"],
        {"event_id": create_event},
        (201,),
        event_id("idem_probe_create"),
    )
    session_id = created.get("session_id")
    if not isinstance(session_id, str):
        raise SeriousFailure("Security probe did not create a session")
    quoted = urllib.parse.quote(session_id, safe="")
    client.request(
        "GET",
        f"/api/game-sessions/{quoted}",
        "security",
        second["cookie"],
        expected=(404,),
        expected_negative=True,
    )
    _, started = mutating_request(
        client,
        "POST",
        f"/api/game-sessions/{quoted}/start",
        "security",
        first["cookie"],
        {"event_id": event_id("evt_probe_start")},
        (200,),
    )
    if started.get("status") != "ACTIVE":
        raise SeriousFailure("Security probe session did not become active")
    if client.stop.wait(1.05):
        raise SeriousFailure("Run stopped during fault checkpoint evidence wait")
    mutating_request(
        client,
        "POST",
        f"/api/game-sessions/{quoted}/checkpoint",
        "security",
        first["cookie"],
        {"event_id": event_id("evt_probe_checkpoint"), "tick": 60, "stage": 1},
        (202,),
    )
    _, faulted = mutating_request(
        client,
        "POST",
        f"/api/game-sessions/{quoted}/fault",
        "security",
        first["cookie"],
        {"event_id": event_id("evt_probe_fault"), "reason": "NETWORK_ERROR", "last_tick": 60},
        (202,),
    )
    if faulted.get("refund", {}).get("status") != "REVIEW_REQUIRED":
        raise SeriousFailure("Security probe fault was not queued for reconciliation")
    if faulted.get("fault_review", {}).get("status") != "PENDING":
        raise SeriousFailure("Security probe fault review did not start pending")
    if client.stop.wait(10.20):
        raise SeriousFailure("Run stopped during fault reconciliation grace period")
    _, recovered = client.request(
        "GET",
        f"/api/game-sessions/{quoted}",
        "security",
        first["cookie"],
    )
    if (
        recovered.get("status") != "ABORTED"
        or recovered.get("refund", {}).get("status") != "REFUNDED"
        or recovered.get("fault_review", {}).get("status") != "AUTO_APPROVED"
    ):
        raise SeriousFailure("Security probe could not reconcile its reserved ticket")

    # The same participant must not receive another automatic network-fault refund
    # inside the 24-hour abuse-control window.
    _, second_created = mutating_request(
        client,
        "POST",
        "/api/game-sessions",
        "security",
        first["cookie"],
        {"event_id": event_id("evt_probe_create_repeat")},
        (201,),
        event_id("idem_probe_create_repeat"),
    )
    second_session_id = second_created.get("session_id")
    if not isinstance(second_session_id, str) or second_session_id == session_id:
        raise SeriousFailure("Security probe did not create a distinct repeat session")
    second_quoted = urllib.parse.quote(second_session_id, safe="")
    mutating_request(
        client,
        "POST",
        f"/api/game-sessions/{second_quoted}/start",
        "security",
        first["cookie"],
        {"event_id": event_id("evt_probe_start_repeat")},
        (200,),
    )
    if client.stop.wait(1.05):
        raise SeriousFailure("Run stopped during repeat fault checkpoint evidence wait")
    mutating_request(
        client,
        "POST",
        f"/api/game-sessions/{second_quoted}/checkpoint",
        "security",
        first["cookie"],
        {"event_id": event_id("evt_probe_checkpoint_repeat"), "tick": 60, "stage": 1},
        (202,),
    )
    _, repeat_fault = mutating_request(
        client,
        "POST",
        f"/api/game-sessions/{second_quoted}/fault",
        "security",
        first["cookie"],
        {"event_id": event_id("evt_probe_fault_repeat"), "reason": "NETWORK_ERROR", "last_tick": 60},
        (202,),
    )
    if repeat_fault.get("fault_review", {}).get("status") != "PENDING":
        raise SeriousFailure("Repeat fault did not enter manual review")
    if client.stop.wait(10.20):
        raise SeriousFailure("Run stopped during repeat fault review wait")
    _, repeat_pending = client.request(
        "GET",
        f"/api/game-sessions/{second_quoted}",
        "security",
        first["cookie"],
    )
    if (
        repeat_pending.get("status") != "FAULT_REPORTED"
        or repeat_pending.get("refund", {}).get("status") != "REVIEW_REQUIRED"
        or repeat_pending.get("fault_review", {}).get("status") != "PENDING"
    ):
        raise SeriousFailure("Repeat network fault bypassed the 24-hour review boundary")


def invitation_probe(
    client: HttpClient,
    cohort: dict[str, Any],
    ledger: BudgetLedger,
    fingerprint: str,
) -> dict[str, Any]:
    participants = cohort["participants"]
    campaign_id = cohort["campaign_id"]
    inviter = participants[ledger.claim_participant(fingerprint, len(participants), campaign_id)]
    visitor = participants[ledger.claim_participant(fingerprint, len(participants), campaign_id)]
    code = inviter.get("referral_code")
    if not code or inviter["participant_id"] == visitor["participant_id"]:
        raise SafetyError("Invitation probe needs distinct participants and an inviter referral code")
    _, before = client.request("GET", "/api/referrals/me", "invitation", inviter["cookie"])
    _, restored = mutating_request(
        client,
        "POST",
        "/api/participants/anonymous",
        "invitation",
        visitor["cookie"],
        {"invite_code": code},
        (200,),
    )
    nonce = restored.get("invite_visit", {}).get("visit_nonce")
    if not isinstance(nonce, str):
        raise SeriousFailure("Invitation probe did not receive a visit nonce")
    if client.stop.wait(3.05):
        raise SeriousFailure("Run stopped during active invitation wait")
    _, qualified = mutating_request(
        client,
        "POST",
        "/api/referrals/qualify",
        "invitation",
        visitor["cookie"],
        {
            "code": code,
            "visit_nonce": nonce,
            "active_ms": 3050,
            "interacted": True,
            "event_id": event_id("evt_invite"),
        },
        (200,),
    )
    _, after = client.request("GET", "/api/referrals/me", "invitation", inviter["cookie"])
    if qualified.get("status") != "REWARDED":
        raise SeriousFailure("Fresh invitation probe was not rewarded")
    if after.get("invitation_balance") != before.get("invitation_balance", 0) + 1:
        raise SeriousFailure("Invitation balance did not increase exactly once")
    return {"completed": True, "active_ms": 3050, "granted": 1}


def unwrap_draw(data: dict[str, Any]) -> dict[str, Any]:
    draw = data.get("draw") if set(data) == {"draw"} else data
    if not isinstance(draw, dict):
        raise SeriousFailure("Invalid draw response")
    return draw


def wait_for_play(client: HttpClient, seconds: float, stage_deadline: float) -> None:
    deadline = min(time.monotonic() + seconds, client.deadline)
    # A flow admitted before the stage cutoff may finish during the bounded cleanup window.
    while time.monotonic() < deadline:
        if client.stop.wait(min(0.25, max(0.0, deadline - time.monotonic()))):
            raise SeriousFailure("Run stopped during genuine play wait")
    if time.monotonic() >= client.deadline:
        client.stop.set()
        raise SeriousFailure("Reserved run deadline reached")


def user_flow(client: HttpClient, participant: dict[str, Any], sequence: int) -> None:
    cookie = participant["cookie"]
    _, me = client.request("GET", "/api/me", "entrance", cookie)
    tickets = me.get("tickets", {})
    if tickets.get("initial") != 1 or tickets.get("invitation") != 0:
        raise SeriousFailure("Fresh load participant is not in the expected one-ticket state")

    _, created = mutating_request(
        client,
        "POST",
        "/api/game-sessions",
        "game_start",
        cookie,
        {"event_id": event_id("evt_create")},
        (201,),
    )
    session_id, seed, version = created.get("session_id"), created.get("seed"), created.get("version")
    if not isinstance(session_id, str) or type(seed) is not int or version != GAME_VERSION:
        raise SeriousFailure("Invalid game session response")
    quoted_session = urllib.parse.quote(session_id, safe="")
    _, started = mutating_request(
        client,
        "POST",
        f"/api/game-sessions/{quoted_session}/start",
        "game_start",
        cookie,
        {"event_id": event_id("evt_start")},
        (200,),
    )
    if started.get("status") != "ACTIVE":
        raise SeriousFailure("Game session did not become active")
    score, ticks, wait_seconds = legal_no_jump(seed)
    wait_for_play(client, wait_seconds, client.deadline)
    _, finished = mutating_request(
        client,
        "POST",
        f"/api/game-sessions/{quoted_session}/finish",
        "game_finish",
        cookie,
        {
            "event_id": event_id("evt_finish"),
            "score": score,
            "ticks": ticks,
            "jump_ticks": [],
            "client_finished_at": utc_now(),
        },
        (200,),
    )
    if finished.get("verification") != "VERIFIED" or finished.get("status") != "FINISHED":
        client.stop.set()
        raise SeriousFailure("Genuine physics result was rejected")

    _, draw_state = client.request("GET", "/api/draws/me", "draw", cookie)
    if draw_state.get("status") != "AVAILABLE":
        raise SeriousFailure("Fresh verified participant is not draw-eligible")
    draw_key = event_id("idem_draw")
    draw_body = {"pouch_index": sequence % 3, "event_id": event_id("evt_draw")}
    first_status, first_raw = mutating_request(
        client, "POST", "/api/draws", "draw", cookie, draw_body, (200, 201), draw_key
    )
    retry_status, retry_raw = mutating_request(
        client, "POST", "/api/draws", "duplicate_retry", cookie, draw_body, (first_status,), draw_key
    )
    first_draw, retry_draw = unwrap_draw(first_raw), unwrap_draw(retry_raw)
    if first_draw.get("draw_id") != retry_draw.get("draw_id") or first_raw != retry_raw:
        client.stop.set()
        raise SeriousFailure("Draw retry changed its immutable result")
    draw_id = first_draw.get("draw_id")
    if not isinstance(draw_id, str):
        raise SeriousFailure("Draw response has no opaque draw ID")
    _, scratched = mutating_request(
        client,
        "PATCH",
        f"/api/draws/{urllib.parse.quote(draw_id, safe='')}/scratch-complete",
        "draw",
        cookie,
        {"event_id": event_id("evt_scratch")},
        (200,),
    )
    if scratched.get("scratch_completed") is not True:
        raise SeriousFailure("Scratch completion was not persisted")

    claim_id = first_draw.get("claim_id")
    if claim_id and sequence % CLAIM_EVERY_N_FLOWS == 0:
        claim_path = f"/api/claims/{urllib.parse.quote(str(claim_id), safe='')}/submit"
        claim_key = event_id("idem_claim")
        claim_body = {
            "name": "TEST_LOAD_USER",
            "contact": "01000000000",
            "school": "TEST_LOAD_SCHOOL",
            "address": "TEST_LOAD_ADDRESS",
            "event_id": event_id("evt_claim"),
        }
        first_claim = mutating_request(
            client, "POST", claim_path, "claim", cookie, claim_body, (200,), claim_key
        )
        retry_claim = mutating_request(
            client, "POST", claim_path, "duplicate_retry", cookie, claim_body, (200,), claim_key
        )
        if first_claim != retry_claim:
            client.stop.set()
            raise SeriousFailure("Claim retry changed its immutable response")

    client.request("GET", "/api/leaderboard?limit=20", "ranking", cookie)
    analytics = {
        "events": [
            {
                "event_id": event_id("evt_page"),
                "name": "page_view",
                "occurred_at": utc_now(),
                "screen": "game",
                "game_session_id": session_id,
                "dimensions": {"source": "phase1_load"},
            }
        ]
    }
    _, accepted = mutating_request(
        client,
        "POST",
        "/api/events/batch",
        "tracking",
        cookie,
        analytics,
        (202,),
    )
    if accepted.get("accepted") != 1 or accepted.get("rejected", 0) != 0:
        raise SeriousFailure("Allowlisted tracking event was not accepted exactly once")
    client.metrics.flow()
    if client.stage_metrics:
        client.stage_metrics.flow()


def run_stage(
    client: HttpClient,
    cohort: dict[str, Any],
    ledger: BudgetLedger,
    fingerprint: str,
    virtual_users: int,
    duration: int,
    burst: bool,
    sequence: list[int],
    sequence_lock: threading.Lock,
    think_time: float,
) -> dict[str, Any]:
    participants = cohort["participants"]
    campaign_id = cohort["campaign_id"]
    started_at = time.monotonic()
    admission_deadline = started_at + duration
    stage_metrics = Metrics()
    client.stage_metrics = stage_metrics
    barrier = threading.Barrier(virtual_users) if burst else None

    def worker() -> None:
        if barrier:
            try:
                barrier.wait(timeout=15)
            except threading.BrokenBarrierError:
                client.stop.set()
                return
        while time.monotonic() < admission_deadline and not client.stop.is_set():
            try:
                index = ledger.claim_participant(fingerprint, len(participants), campaign_id)
            except BudgetExceeded:
                break
            with sequence_lock:
                sequence[0] += 1
                flow_sequence = sequence[0]
            try:
                user_flow(client, participants[index], flow_sequence)
            except BudgetExceeded:
                client.stop.set()
                break
            except SeriousFailure:
                client.stop.set()
                break
            except (RateLimited, UnexpectedResponse, urllib.error.URLError, TimeoutError):
                pass
            except Exception:
                with client.metrics.lock:
                    client.metrics.unexpected += 1
                client.stop.set()
                break
            remaining = admission_deadline - time.monotonic()
            if remaining > 0:
                client.stop.wait(min(think_time, remaining))

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=virtual_users,
        thread_name_prefix="phase1-load",
    ) as pool:
        futures = [pool.submit(worker) for _ in range(virtual_users)]
        concurrent.futures.wait(futures, timeout=duration + RUN_OVERHEAD_SECONDS)
        if any(not future.done() for future in futures):
            client.stop.set()
            raise SeriousFailure("Stage workers exceeded the bounded cleanup window")
    elapsed = time.monotonic() - started_at
    client.stage_metrics = None
    return {
        "virtual_users": virtual_users,
        "admission_window_seconds": duration,
        "actual_seconds_including_cleanup": round(elapsed, 2),
        "burst": burst,
        "stopped_early": client.stop.is_set() and elapsed + 0.5 < duration,
        "metrics": stage_metrics.report(elapsed),
    }


def estimate_profile(profile: str, think_time: float, invitation_probe_enabled: bool = False) -> dict[str, Any]:
    if think_time < 10:
        raise SafetyError("Think time must be at least 10 seconds")
    stages = []
    for virtual_users, seconds, burst in PROFILES[profile]:
        flows = virtual_users * math.ceil(seconds / think_time)
        stages.append(
            {
                "virtual_users": virtual_users,
                "seconds": seconds,
                "burst": burst,
                "flow_attempts_ceiling": flows,
            }
        )
    flows = sum(stage["flow_attempts_ceiling"] for stage in stages)
    claims = flows // CLAIM_EVERY_N_FLOWS
    probe_calls = PREFLIGHT_AND_SECURITY_CALLS + (INVITATION_PROBE_CALLS if invitation_probe_enabled else 0)
    script_calls = probe_calls + flows * BASE_FLOW_CALLS + claims * CLAIM_RETRY_CALLS
    absolute_calls = probe_calls + flows * 12 + claims * CLAIM_RETRY_CALLS
    mutations = 11 + (2 if invitation_probe_enabled else 0) + flows * BASE_FLOW_MUTATIONS + claims * 2
    return {
        "stages": stages,
        "flow_attempts_ceiling": flows,
        "claim_flow_attempts_ceiling": claims,
        "cohort_participants_required_ceiling": flows + 2 + (2 if invitation_probe_enabled else 0),
        "script_api_calls_ceiling": script_calls,
        "absolute_api_calls_ceiling": absolute_calls,
        "http_mutation_requests_ceiling": mutations,
        "client_tracking_events_ceiling": flows,
        "server_domain_event_attempts_ceiling": 7 + flows * 6 + claims + (1 if invitation_probe_enabled else 0),
        "database_write_statement_envelope": 60 + flows * 24 + claims * 8 + (12 if invitation_probe_enabled else 0),
    }


def reserved_duration(profile: str, invitation_probe_enabled: bool = False) -> int:
    probe_seconds = 4 if invitation_probe_enabled else 0
    return sum(stage[1] for stage in PROFILES[profile]) + RUN_OVERHEAD_SECONDS + probe_seconds


def dry_run(
    profile: str,
    cohort_size: int = MAX_COHORT_SIZE,
    think_time: float = DEFAULT_THINK_TIME_SECONDS,
    invitation_probe_enabled: bool = False,
) -> dict[str, Any]:
    estimate = estimate_profile(profile, think_time, invitation_probe_enabled)
    return {
        "profile": profile,
        "stages": estimate.pop("stages"),
        "planned_stage_seconds": sum(stage[1] for stage in PROFILES[profile]),
        "reserved_duration_seconds": reserved_duration(profile, invitation_probe_enabled),
        "think_time_seconds": think_time,
        "prepared_cohort_size": cohort_size,
        **estimate,
        "within_hard_api_call_cap": estimate["absolute_api_calls_ceiling"] <= MAX_API_CALLS,
        "within_prepared_cohort": estimate["cohort_participants_required_ceiling"] <= cohort_size,
        "hard_api_call_ceiling": MAX_API_CALLS,
        "hard_cumulative_seconds": MAX_DURATION_SECONDS,
        "real_prizes": False,
        "traffic_estimate_note": (
            "Conservative HTTP admission, mutation, tracking/domain-event, and database-statement "
            "envelopes; they are not measured row counts or monetary price quotes."
        ),
    }


def evaluate_targets(metrics_report: dict[str, Any]) -> dict[str, Any]:
    general_violations = []
    finish_draw_violations = []
    for endpoint, values in metrics_report.get("endpoints", {}).items():
        p95 = values.get("p95_ms")
        if p95 is None:
            continue
        critical = "/finish" in endpoint or "/api/draws" in endpoint
        limit = 2_000 if critical else 1_000
        if p95 > limit:
            (finish_draw_violations if critical else general_violations).append(
                {"endpoint": endpoint, "p95_ms": p95, "limit_ms": limit}
            )
    calls = int(metrics_report.get("api_calls", 0))
    unexpected = int(metrics_report.get("unexpected_failures", 0))
    failure_rate = unexpected / calls if calls else 0.0
    return {
        "general_api_p95_at_most_1000ms": not general_violations,
        "finish_draw_p95_at_most_2000ms": not finish_draw_violations,
        "unexpected_failure_rate_below_1_percent": failure_rate < 0.01,
        "unexpected_failure_rate": round(failure_rate, 6),
        "general_violations": general_violations,
        "finish_draw_violations": finish_draw_violations,
        "database_reconciliation_required": True,
    }


def write_private_json(path: Path, data: dict[str, Any]) -> None:
    if path.exists() and path.is_symlink():
        raise SafetyError("Report path must not be a symlink")
    payload = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True).encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.chmod(path, 0o600)
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)


def safe_failure(error: BaseException) -> dict[str, str]:
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
    parser.add_argument("--cohort", type=Path)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--expected-project-ref", default=EXPECTED_PROJECT_REF)
    parser.add_argument("--expected-deployment-id")
    parser.add_argument("--resume-from-deployment-id")
    parser.add_argument("--resume-from-base-url")
    parser.add_argument("--protection-token-file", type=Path)
    parser.add_argument("--deployment-auth-cookie-file", type=Path)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--think-time", type=float, default=DEFAULT_THINK_TIME_SECONDS)
    parser.add_argument("--invitation-probe", action="store_true")
    parser.add_argument("--require-last-stock", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    resume_requested = bool(
        args.resume_from_deployment_id or args.resume_from_base_url
    )
    if bool(args.resume_from_deployment_id) != bool(args.resume_from_base_url):
        raise SafetyError("Redeployment resume requires both original deployment ID and URL")
    if args.mode == "remote" and not args.expected_deployment_id and not args.dry_run:
        raise SafetyError("Remote runs require --expected-deployment-id")
    if resume_requested and (args.mode != "remote" or args.dry_run):
        raise SafetyError("Redeployment resume is only available for an actual remote run")
    if args.dry_run:
        cohort_size = MAX_COHORT_SIZE
        if args.cohort:
            base_url = validate_target(args.base_url, args.mode) if args.base_url else None
            cohort = load_cohort(
                args.cohort,
                args.mode,
                base_url,
                args.expected_project_ref,
                args.resume_from_deployment_id or args.expected_deployment_id,
            )
            cohort_size = len(cohort["participants"])
        report = dry_run(args.profile, cohort_size, args.think_time, args.invitation_probe)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["within_hard_api_call_cap"] and report["within_prepared_cohort"] else 2

    if not all((args.base_url, args.cohort, args.ledger, args.report)):
        raise SafetyError("Actual runs require explicit base URL, cohort, ledger, and report paths")
    base_url = validate_target(args.base_url, args.mode)
    cohort_base_url = (
        validate_target(args.resume_from_base_url, "remote")
        if resume_requested
        else base_url
    )
    cohort = load_cohort(
        args.cohort,
        args.mode,
        cohort_base_url,
        args.expected_project_ref,
        args.resume_from_deployment_id or args.expected_deployment_id,
    )
    original_cohort = cohort
    redeployment_proof = None
    if resume_requested:
        cohort, redeployment_proof = retarget_cohort_for_redeployment(
            original_cohort,
            args.resume_from_deployment_id,
            args.expected_deployment_id,
            cohort_base_url,
            base_url,
        )
    protection_token = None
    if args.protection_token_file:
        protection_token = read_private_text(args.protection_token_file, "Protection token file")
        if not (16 <= len(protection_token) <= 2048) or any(char.isspace() for char in protection_token):
            raise SafetyError("Invalid Vercel protection bypass token")
    deployment_auth_cookie = None
    if args.deployment_auth_cookie_file:
        deployment_auth_cookie = read_private_text(
            args.deployment_auth_cookie_file, "Deployment auth cookie file"
        )
        if not re.fullmatch(r"[A-Za-z0-9_~-]{1,64}=[^;\s]{16,2048}", deployment_auth_cookie):
            raise SafetyError("Invalid Vercel deployment authentication cookie")

    fingerprint = cohort_fingerprint(cohort)
    original_fingerprint = cohort_fingerprint(original_cohort)
    estimate = estimate_profile(args.profile, args.think_time, args.invitation_probe)
    reserved = reserved_duration(args.profile, args.invitation_probe)
    stop = threading.Event()
    metrics = Metrics()
    with BudgetLedger(args.ledger) as ledger:
        active_fingerprint = fingerprint
        migration_state = None
        if redeployment_proof:
            migration_state = ledger.redeployment_state(
                original_fingerprint, fingerprint, redeployment_proof
            )
            active_fingerprint = (
                fingerprint if migration_state == "completed" else original_fingerprint
            )
        ledger.register_cohort_preparation(
            active_fingerprint, cohort.get("preparation_api_calls", 0)
        )
        if estimate["absolute_api_calls_ceiling"] > ledger.remaining_calls:
            raise BudgetExceeded("Conservative call envelope exceeds the cumulative remaining budget")
        remaining_participants = ledger.participants_remaining(
            active_fingerprint, len(cohort["participants"])
        )
        if estimate["cohort_participants_required_ceiling"] > remaining_participants:
            raise BudgetExceeded("Fresh participant cohort is too small for this run")
        ledger.reserve_run(reserved, args.profile, fingerprint, args.expected_deployment_id)
        started_at = time.monotonic()
        client = HttpClient(
            base_url,
            ledger,
            metrics,
            args.timeout,
            stop,
            started_at + reserved,
            protection_token,
            deployment_auth_cookie,
        )
        health = config = None
        stage_reports: list[dict[str, Any]] = []
        invitation_report = None
        failure = None
        try:
            health, config = preflight(
                client,
                args.mode,
                args.expected_project_ref,
                args.expected_deployment_id,
                cohort["campaign_id"],
                args.require_last_stock,
            )
            if redeployment_proof:
                verify_redeployment_target(
                    redeployment_proof, health, config, base_url
                )
                ledger.migrate_redeployment(
                    original_fingerprint, fingerprint, redeployment_proof
                )
                active_fingerprint = fingerprint
                migration_state = "completed"
            security_probe(client, cohort, ledger, active_fingerprint)
            if args.invitation_probe:
                invitation_report = invitation_probe(
                    client, cohort, ledger, active_fingerprint
                )
            sequence = [0]
            sequence_lock = threading.Lock()
            for virtual_users, seconds, burst in PROFILES[args.profile]:
                if stop.is_set():
                    break
                stage_reports.append(
                    run_stage(
                        client,
                        cohort,
                        ledger,
                        active_fingerprint,
                        virtual_users,
                        seconds,
                        burst,
                        sequence,
                        sequence_lock,
                        args.think_time,
                    )
                )
        except BaseException as error:
            stop.set()
            failure = safe_failure(error)
        elapsed = time.monotonic() - started_at
        metric_report = metrics.report(elapsed)
        report = {
            "profile": args.profile,
            "mode": args.mode,
            "target": {
                "host": urllib.parse.urlsplit(base_url).hostname,
                "environment": health.get("environment") if health else None,
                "deployment": health.get("deployment") if health else None,
                "project_ref": health.get("project_ref") if health else None,
                "schema": health.get("schema") if health else None,
                "synthetic_only": health.get("synthetic_only") if health else None,
                "campaign_id": config.get("campaign", {}).get("id") if config else None,
            },
            "cohort_fingerprint": fingerprint,
            "planned_stage_seconds": sum(stage[1] for stage in PROFILES[args.profile]),
            "reserved_duration_seconds": reserved,
            "actual_elapsed_seconds": round(elapsed, 2),
            "plan_envelope": estimate,
            "invitation_probe": invitation_report,
            "redeployment_resume": {
                "old_deployment_id": redeployment_proof["old_deployment_id"],
                "new_deployment_id": redeployment_proof["new_deployment_id"],
                "old_base_url": redeployment_proof["old_base_url"],
                "new_base_url": redeployment_proof["new_base_url"],
                "participant_identity_sha256": redeployment_proof[
                    "participant_identity_sha256"
                ],
                "migration_state": migration_state,
            }
            if redeployment_proof
            else None,
            "last_stock_guarded": args.require_last_stock,
            "stages": stage_reports,
            "metrics": metric_report,
            "targets": evaluate_targets(metric_report),
            "budget": {
                "admitted_api_calls_cumulative": ledger.data["admitted_api_calls"],
                "completed_api_calls_cumulative": ledger.data["completed_api_calls"],
                "duration_reserved_seconds_cumulative": ledger.data["duration_reserved_seconds"],
                "api_calls_remaining": ledger.remaining_calls,
            },
            "participants_remaining": ledger.participants_remaining(
                active_fingerprint, len(cohort["participants"])
            ),
            "serious_stop": stop.is_set(),
            "failure": failure,
        }
        write_private_json(args.report, report)
        return 2 if stop.is_set() else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SafetyError as error:
        print(
            json.dumps({"error": type(error).__name__, "message": str(error)}, ensure_ascii=False),
            file=sys.stderr,
        )
        raise SystemExit(2)
