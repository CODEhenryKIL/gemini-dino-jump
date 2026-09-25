#!/usr/bin/env python3
"""Prepare one private, recoverable 5,000-participant Phase 1 cohort."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import secrets
import stat
import sys
import urllib.parse
import uuid
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

import auth  # noqa: E402
from config import (  # noqa: E402
    APP_ROLE,
    APPROVED_PREVIEW_PROJECT_REF,
    CONSTANTS,
    SCHEMA_NAME,
    SCHEMA_VERSION,
)


COHORT_SIZE = 5_000
COOKIE_NAME = "dj_session"
DEFAULT_CAMPAIGN_ID = "gemini_dino_phase1_test"
SUPABASE_CA = ROOT / "server" / "certs" / "supabase-ca-2021.crt"


class PreparationError(RuntimeError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def private_text(path: Path, label: str) -> str:
    if path.is_symlink():
        raise PreparationError(f"{label} must not be a symlink")
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise PreparationError(f"{label} permissions must be 0600")
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise PreparationError(f"{label} is empty")
    return value


def secret_value(file_path: str | None, environment_name: str, label: str) -> str:
    from_file = private_text(Path(file_path), label) if file_path else None
    from_environment = os.getenv(environment_name)
    if from_file and from_environment:
        raise PreparationError(f"Choose one {label} source: private file or environment")
    value = from_file or from_environment
    if not value:
        raise PreparationError(f"{label} is required through a private file or environment")
    return value


def validate_target(
    mode: str,
    base_url: str,
    deployment_id: str,
    project_ref: str,
    local_environment: str,
) -> dict[str, str]:
    parsed = urllib.parse.urlsplit(base_url)
    if (
        parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise PreparationError("Base URL must be one origin without credentials or a path")
    host = (parsed.hostname or "").lower()
    if not re.fullmatch(r"[A-Za-z0-9._-]{3,128}", deployment_id):
        raise PreparationError("Deployment identity is required")
    if mode == "remote":
        if (
            parsed.scheme != "https"
            or parsed.port not in (None, 443)
            or not host.endswith(".vercel.app")
            or host == "vercel.app"
        ):
            raise PreparationError("Remote cohort requires an exact HTTPS Vercel origin")
        if project_ref != APPROVED_PREVIEW_PROJECT_REF:
            raise PreparationError("Remote Supabase project is not approved")
        environment = "preview"
    else:
        if parsed.scheme != "http" or host not in {"127.0.0.1", "localhost", "::1"}:
            raise PreparationError("Local cohort requires a loopback HTTP origin")
        if project_ref != "local" or local_environment not in {"local", "test"}:
            raise PreparationError("Local cohort guard mismatch")
        environment = local_environment
    return {
        "environment": environment,
        "base_url": base_url.rstrip("/"),
        "deployment_id": deployment_id,
        "project_ref": project_ref,
    }


def validate_dsn(dsn: str, mode: str, project_ref: str) -> None:
    try:
        parsed = urllib.parse.urlsplit(dsn)
        username = urllib.parse.unquote(parsed.username or "")
    except ValueError as error:
        raise PreparationError("Database URL is invalid") from error
    if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname:
        raise PreparationError("A PostgreSQL database URL is required")
    host = parsed.hostname.lower()
    if mode == "remote":
        if (
            parsed.port != 6543
            or not host.endswith(".pooler.supabase.com")
            or username != f"{APP_ROLE}.{project_ref}"
        ):
            raise PreparationError("Remote cohort requires the scoped transaction-pooler role")
    elif host not in {"127.0.0.1", "localhost", "::1"} or username != APP_ROLE:
        raise PreparationError("Local cohort requires the loopback application role")


def _manifest_payload(target: dict[str, str], campaign_id: str) -> dict[str, Any]:
    participants = []
    for index in range(COHORT_SIZE):
        raw_cookie = secrets.token_urlsafe(48)
        participants.append(
            {
                "cookie": f"{COOKIE_NAME}={raw_cookie}",
                "participant_id": f"p_load_{uuid.uuid4().hex}",
                "referral_code": f"load_{secrets.token_urlsafe(18)}",
                "nickname": f"합성공룡{index + 1:04d}",
            }
        )
    return {
        "schema_version": 1,
        **target,
        "schema": SCHEMA_NAME,
        "campaign_id": campaign_id,
        "created_at": utc_now(),
        "preparation_api_calls": 0,
        "state": "PREPARED",
        "participants": participants,
    }


def _validate_manifest(
    data: dict[str, Any], target: dict[str, str], campaign_id: str
) -> None:
    expected = {
        "schema_version": 1,
        **target,
        "schema": SCHEMA_NAME,
        "campaign_id": campaign_id,
        "preparation_api_calls": 0,
    }
    if any(data.get(key) != value for key, value in expected.items()):
        raise PreparationError("Existing cohort manifest belongs to another guarded target")
    if data.get("state") not in {"PREPARED", "READY"}:
        raise PreparationError("Existing cohort manifest state is invalid")
    participants = data.get("participants")
    if not isinstance(participants, list) or len(participants) != COHORT_SIZE:
        raise PreparationError("Cohort manifest must contain exactly 5,000 participants")
    cookies = set()
    participant_ids = set()
    referrals = set()
    for participant in participants:
        if not isinstance(participant, dict):
            raise PreparationError("Cohort participant entry is invalid")
        cookie = participant.get("cookie")
        participant_id = participant.get("participant_id")
        referral = participant.get("referral_code")
        nickname = participant.get("nickname")
        if not isinstance(cookie, str) or not re.fullmatch(
            rf"{COOKIE_NAME}=[A-Za-z0-9_-]{{64}}", cookie
        ):
            raise PreparationError("Cohort cookie is invalid")
        if not isinstance(participant_id, str) or not re.fullmatch(
            r"p_load_[0-9a-f]{32}", participant_id
        ):
            raise PreparationError("Cohort participant ID is invalid")
        if not isinstance(referral, str) or not re.fullmatch(r"load_[A-Za-z0-9_-]{24}", referral):
            raise PreparationError("Cohort referral code is invalid")
        if not isinstance(nickname, str) or not 1 <= len(nickname) <= 24:
            raise PreparationError("Cohort nickname is invalid")
        cookies.add(cookie)
        participant_ids.add(participant_id)
        referrals.add(referral)
    if not all(len(values) == COHORT_SIZE for values in (cookies, participant_ids, referrals)):
        raise PreparationError("Cohort identities must be unique")


def _write_new_private_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        raise FileExistsError(path)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        os.fchmod(fd, 0o600)
        payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)


def ensure_manifest(
    path: Path, target: dict[str, str], campaign_id: str
) -> tuple[dict[str, Any], bool]:
    if path.exists() or path.is_symlink():
        data = json.loads(private_text(path, "Cohort manifest"))
        _validate_manifest(data, target, campaign_id)
        return data, False
    data = _manifest_payload(target, campaign_id)
    _validate_manifest(data, target, campaign_id)
    _write_new_private_json(path, data)
    return data, True


def _replace_private_json(path: Path, data: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        _write_new_private_json(temporary, data)
        os.replace(temporary, path)
        os.chmod(path, 0o600)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary.exists():
            temporary.unlink()


def mark_ready(path: Path, manifest: dict[str, Any]) -> None:
    ready = dict(manifest)
    ready["state"] = "READY"
    ready["ready_at"] = ready.get("ready_at") or utc_now()
    _replace_private_json(path, ready)
    manifest.clear()
    manifest.update(ready)


def validate_database_guard(
    conn, expected_environment: str, project_ref: str, campaign_id: str
) -> dict[str, Any]:
    row = conn.execute(
        """select current_user role,g.environment,g.project_ref,g.schema_name,g.synthetic_only,
        g.test_seed,g.campaign_id,c.is_test,c.real_prizes_enabled,c.status,c.game_version,
        exists(select 1 from dino_dev.schema_version where version=%s) schema_current
        from dino_dev.environment_guard g
        join dino_dev.campaign c on c.id=g.campaign_id where g.singleton""",
        (SCHEMA_VERSION,),
    ).fetchone()
    expected = {
        "role": APP_ROLE,
        "environment": expected_environment,
        "project_ref": project_ref,
        "schema_name": SCHEMA_NAME,
        "synthetic_only": True,
        "test_seed": True,
        "campaign_id": campaign_id,
        "is_test": True,
        "real_prizes_enabled": False,
        "status": "ACTIVE",
        "game_version": CONSTANTS["version"],
        "schema_current": True,
    }
    if not row or any(row[key] != value for key, value in expected.items()):
        raise PreparationError("Database environment, role, schema, or campaign guard mismatch")
    return dict(row)


def _seed_rows(manifest: dict[str, Any], pepper: str) -> list[dict[str, str]]:
    rows = []
    for participant in manifest["participants"]:
        raw_cookie = participant["cookie"].split("=", 1)[1]
        rows.append(
            {
                **participant,
                "token_hash": auth.token_hash(raw_cookie, pepper),
            }
        )
    return rows


def seed_cohort(conn, manifest: dict[str, Any], pepper: str) -> dict[str, int]:
    rows = _seed_rows(manifest, pepper)
    by_id = {row["participant_id"]: row for row in rows}
    ids = list(by_id)
    hashes = [row["token_hash"] for row in rows]
    referrals = [row["referral_code"] for row in rows]
    existing = conn.execute(
        """select id,token_hash,referral_code,campaign_id,environment,synthetic
        from dino_dev.participant
        where id=any(%s) or token_hash=any(%s) or referral_code=any(%s)""",
        (ids, hashes, referrals),
    ).fetchall()
    existing_ids = set()
    for stored in existing:
        expected = by_id.get(stored["id"])
        if (
            not expected
            or stored["token_hash"] != expected["token_hash"]
            or stored["referral_code"] != expected["referral_code"]
            or stored["campaign_id"] != manifest["campaign_id"]
            or stored["environment"] != manifest["environment"]
            or stored["synthetic"] is not True
        ):
            raise PreparationError("Cohort identity conflicts with existing data")
        existing_ids.add(stored["id"])

    if existing_ids:
        ledgers = conn.execute(
            """select participant_id,count(*) n,min(delta) delta
            from dino_dev.ticket_ledger
            where participant_id=any(%s) and source_type='INITIAL_GRANT' and source_id='initial'
            group by participant_id""",
            (list(existing_ids),),
        ).fetchall()
        valid_ledgers = {
            row["participant_id"] for row in ledgers if row["n"] == 1 and row["delta"] == 1
        }
        if valid_ledgers != existing_ids:
            raise PreparationError("Existing cohort initial-ticket ledger is incomplete")

    missing = [row for row in rows if row["participant_id"] not in existing_ids]
    if missing:
        with conn.cursor() as cursor:
            cursor.executemany(
                """insert into dino_dev.participant
                (id,campaign_id,token_hash,token_expires_at,nickname,referral_code,environment,
                 synthetic,initial_balance,invitation_balance,invitation_refund_pending,
                 first_link_kind,first_channel)
                values(%s,%s,%s,clock_timestamp()+interval '30 days',%s,%s,%s,true,1,0,0,
                       'load_seed','phase1_cohort')""",
                [
                    (
                        row["participant_id"],
                        manifest["campaign_id"],
                        row["token_hash"],
                        row["nickname"],
                        row["referral_code"],
                        manifest["environment"],
                    )
                    for row in missing
                ],
            )
            cursor.executemany(
                """insert into dino_dev.ticket_ledger
                (participant_id,ticket_kind,delta,source_type,source_id,balance_after)
                values(%s,'INITIAL',1,'INITIAL_GRANT','initial',1)""",
                [(row["participant_id"],) for row in missing],
            )

    final = conn.execute(
        "select count(*) n from dino_dev.participant where id=any(%s)", (ids,)
    ).fetchone()["n"]
    if final != COHORT_SIZE:
        raise PreparationError("Cohort database verification did not reach exactly 5,000 identities")
    return {"inserted": len(missing), "existing": len(existing_ids), "total": final}


def connect_database(dsn: str, mode: str):
    options = {
        "autocommit": False,
        "prepare_threshold": None,
        "row_factory": dict_row,
        "connect_timeout": 10,
        "application_name": "gemini-dino-jump-cohort-preparer",
    }
    if mode == "remote":
        options.update(sslmode="verify-full", sslrootcert=str(SUPABASE_CA))
    return psycopg.connect(dsn, **options)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("local", "remote"), required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--deployment-id", required=True)
    parser.add_argument("--expected-project-ref", default=APPROVED_PREVIEW_PROJECT_REF)
    parser.add_argument("--local-environment", choices=("local", "test"), default="test")
    parser.add_argument("--campaign-id", default=DEFAULT_CAMPAIGN_ID)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--database-url-file")
    parser.add_argument("--pepper-file")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    project_ref = args.expected_project_ref if args.mode == "remote" else "local"
    target = validate_target(
        args.mode,
        args.base_url,
        args.deployment_id,
        project_ref,
        args.local_environment,
    )
    manifest, created = ensure_manifest(args.output, target, args.campaign_id)
    dsn = secret_value(args.database_url_file, "PHASE1_COHORT_DATABASE_URL", "Database URL")
    pepper = secret_value(args.pepper_file, "PHASE1_COHORT_TOKEN_PEPPER", "Token pepper")
    if len(pepper) < 32:
        raise PreparationError("Token pepper must be at least 32 characters")
    validate_dsn(dsn, args.mode, project_ref)
    with connect_database(dsn, args.mode) as conn:
        with conn.transaction():
            validate_database_guard(conn, target["environment"], project_ref, args.campaign_id)
            result = seed_cohort(conn, manifest, pepper)
    mark_ready(args.output, manifest)
    print(
        json.dumps(
            {
                "ok": True,
                "manifest_created": created,
                "state": manifest["state"],
                **result,
                "output": str(args.output),
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (PreparationError, OSError, psycopg.Error, json.JSONDecodeError) as error:
        print(json.dumps({"ok": False, "error": type(error).__name__}), file=sys.stderr)
        raise SystemExit(2)
