#!/usr/bin/env python3
"""Prepare the finite synthetic draw pool used only by the final Preview load.

Default mode is a database-free plan. ``--apply`` requires an approved Preview
maintenance credential and a new private rollback backup. Existing draws,
inventory, prizes and participant records are never updated or deleted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import urllib.parse
import uuid
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
PROJECT_REF = "igfrnexknwtiljdqjrbp"
SCHEMA = "dino_dev"
CAMPAIGN_ID = "gemini_dino_phase1_test"
PREFIX = "phase3load_"
EXPECTED_SPEC_SHA256 = "337a66173f12f80c5f31f8bc6792d81e93178bdaa91bc3ee0610686fc2dcae6d"
# Historical test input: the production manifest may change after the run, but
# the synthetic 77-prize pool must remain reproducible from reviewed evidence.
DEFAULT_MANIFEST = ROOT / "docs" / "evidence" / "phase3-load-manifest-20260929.json"
SUPABASE_CA = ROOT / "server" / "certs" / "supabase-ca-2021.crt"


class PoolPreparationError(RuntimeError):
    pass


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode()


def load_plan(path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    spec = {key: manifest[key] for key in ("version", "draw_pool", "draw_prizes")}
    digest = hashlib.sha256(_canonical(spec)).hexdigest()
    if digest != EXPECTED_SPEC_SHA256:
        raise PoolPreparationError("PHASE3_LOAD_MANIFEST_CHANGED")
    pool = manifest["draw_pool"]
    prizes = manifest["draw_prizes"]
    total = int(pool.get("total_slots", 0))
    benefits = int(pool.get("benefit_slots", 0))
    prize_total = sum(int(item.get("quantity", 0)) for item in prizes)
    if total != 5000 or prize_total != 77 or benefits != 4923 or prize_total + benefits != total:
        raise PoolPreparationError("PHASE3_LOAD_POOL_COUNTS_INVALID")
    ids = [item.get("id") for item in prizes]
    if len(ids) != len(set(ids)) or any(not re.fullmatch(r"[a-z0-9_]{2,48}", str(item)) for item in ids):
        raise PoolPreparationError("PHASE3_LOAD_PRIZE_IDS_INVALID")
    return {
        "schema_version": 1,
        "mode": "PLAN_ONLY",
        "environment": "preview",
        "project_ref": PROJECT_REF,
        "schema": SCHEMA,
        "campaign_id": CAMPAIGN_ID,
        "manifest_version": manifest["version"],
        "manifest_spec_sha256": digest,
        "probability_version": f"phase3-load-{digest[:16]}",
        "prefix": PREFIX,
        "total_slots": total,
        "prize_slots": prize_total,
        "benefit_slots": benefits,
        "prizes": [
            {
                "source_id": item["id"],
                "id": PREFIX + item["id"],
                "name": "[합성 부하] " + str(item["name"]),
                "category": item["category"],
                "quantity": int(item["quantity"]),
                "probability": int(item["quantity"]) / total,
            }
            for item in prizes
        ],
        "network_calls": 0,
        "database_writes": 0,
        "apply_requires_explicit_flag": True,
    }


def _private_text(path: Path) -> str:
    if path.is_symlink() or stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise PoolPreparationError("PHASE3_LOAD_DATABASE_FILE_NOT_PRIVATE")
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise PoolPreparationError("PHASE3_LOAD_DATABASE_URL_MISSING")
    return value


def connect(dsn: str):
    parsed = urllib.parse.urlsplit(dsn)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.query or parsed.fragment:
        raise PoolPreparationError("PHASE3_LOAD_DSN_INVALID")
    direct = (
        parsed.hostname == f"db.{PROJECT_REF}.supabase.co"
        and parsed.port == 5432
        and parsed.username == "postgres"
    )
    pooled = (
        bool(parsed.hostname)
        and parsed.hostname.endswith(".pooler.supabase.com")
        and parsed.port in {5432, 6543}
        and parsed.username == f"postgres.{PROJECT_REF}"
    )
    if not (direct or pooled) or parsed.path != "/postgres":
        raise PoolPreparationError("PHASE3_LOAD_APPROVED_PROJECT_REQUIRED")
    return psycopg.connect(
        dsn,
        autocommit=False,
        row_factory=dict_row,
        connect_timeout=5,
        prepare_threshold=None,
        sslmode="verify-full",
        sslrootcert=str(SUPABASE_CA),
        application_name="gemini-dino-phase3-load-pool",
    )


def _maintenance_scope(conn, *, lock: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    role = conn.execute(
        """select current_user name,rolsuper or rolbypassrls maintenance
        from pg_roles where rolname=current_user"""
    ).fetchone()
    if not role or not role["maintenance"] or role["name"] in {"dino_dev_app", "dino_prod_app"}:
        raise PoolPreparationError("PHASE3_LOAD_MAINTENANCE_ROLE_REQUIRED")
    suffix = " for update" if lock else ""
    guard = conn.execute(
        f"select * from {SCHEMA}.environment_guard where singleton" + suffix
    ).fetchone()
    if (
        not guard
        or guard["environment"] != "preview"
        or guard["project_ref"] != PROJECT_REF
        or guard["schema_name"] != SCHEMA
        or guard["synthetic_only"] is not True
        or guard["test_seed"] is not True
        or guard["campaign_id"] != CAMPAIGN_ID
    ):
        raise PoolPreparationError("PHASE3_LOAD_GUARD_MISMATCH")
    campaign = conn.execute(
        f"select * from {SCHEMA}.campaign where id=%s" + suffix, (CAMPAIGN_ID,),
    ).fetchone()
    if (
        not campaign
        or campaign["status"] != "ACTIVE"
        or campaign["is_test"] is not True
        or campaign["real_prizes_enabled"] is not False
    ):
        raise PoolPreparationError("PHASE3_LOAD_CAMPAIGN_MISMATCH")
    return dict(guard), dict(campaign)


def _pool_counts(conn) -> dict[str, int]:
    return dict(conn.execute(
        f"""select count(*)::int total,
        count(*) filter(where outcome_kind='PRIZE')::int prizes,
        count(*) filter(where outcome_kind='BENEFIT')::int benefits,
        count(*) filter(where allocated_draw_id is not null)::int allocated
        from {SCHEMA}.draw_pool_slot where campaign_id=%s""",
        (CAMPAIGN_ID,),
    ).fetchone())


def _validate_existing_pool(conn, plan: dict[str, Any]) -> dict[str, Any]:
    counts = _pool_counts(conn)
    if counts != {"total": 5000, "prizes": 77, "benefits": 4923, "allocated": 0}:
        raise PoolPreparationError("PHASE3_LOAD_EXISTING_POOL_INVALID")
    rows = conn.execute(
        f"""select p.id,count(*)::int quantity,bool_and(i.status='AVAILABLE') inventory_available
        from {SCHEMA}.draw_pool_slot s join {SCHEMA}.prize p on p.id=s.prize_id
        join {SCHEMA}.inventory_item i on i.id=s.inventory_item_id
        where s.campaign_id=%s and s.outcome_kind='PRIZE'
        group by p.id order by p.id""", (CAMPAIGN_ID,),
    ).fetchall()
    expected = {item["id"]: item["quantity"] for item in plan["prizes"]}
    actual = {row["id"]: row["quantity"] for row in rows}
    if actual != expected or not all(row["inventory_available"] for row in rows):
        raise PoolPreparationError("PHASE3_LOAD_EXISTING_DISTRIBUTION_INVALID")
    return counts


def _write_private_json(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        if path.is_symlink() or stat.S_IMODE(path.stat().st_mode) & 0o077:
            raise PoolPreparationError("PHASE3_LOAD_BACKUP_NOT_PRIVATE")
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise PoolPreparationError("PHASE3_LOAD_BACKUP_INVALID") from error
        if existing != payload:
            raise PoolPreparationError("PHASE3_LOAD_BACKUP_CHANGED")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        os.fchmod(fd, 0o600)
        data = _canonical(payload)
        written = 0
        while written < len(data):
            written += os.write(fd, data[written:])
        os.fsync(fd)
    finally:
        os.close(fd)


def apply_pool(conn, plan: dict[str, Any], backup_path: Path) -> dict[str, Any]:
    conn.execute(
        "select pg_advisory_xact_lock(hashtextextended(%s,0))",
        ("draw-pool:" + CAMPAIGN_ID,),
    )
    _guard, campaign = _maintenance_scope(conn, lock=True)
    marker = (campaign.get("settings") or {}).get("phase3_manifest_hash")
    if marker is not None:
        if marker != plan["manifest_spec_sha256"] or campaign["probability_version"] != plan["probability_version"]:
            raise PoolPreparationError("PHASE3_LOAD_EXISTING_MARKER_CHANGED")
        counts = _validate_existing_pool(conn, plan)
        return {"created": False, **counts, "manifest_spec_sha256": marker}
    if _pool_counts(conn)["total"] != 0:
        raise PoolPreparationError("PHASE3_LOAD_POOL_NOT_EMPTY")
    benefit = conn.execute(
        f"""select id from {SCHEMA}.prize where campaign_id=%s and category='NO_PRIZE'
        and is_active order by id limit 1""", (CAMPAIGN_ID,),
    ).fetchone()
    if not benefit:
        raise PoolPreparationError("PHASE3_LOAD_ACTIVE_BENEFIT_REQUIRED")
    collisions = conn.execute(
        f"""select
        (select count(*) from {SCHEMA}.prize where id like %s) prize_count,
        (select count(*) from {SCHEMA}.inventory_item where id like %s) inventory_count""",
        (PREFIX + "%", PREFIX + "%"),
    ).fetchone()
    if collisions["prize_count"] or collisions["inventory_count"]:
        raise PoolPreparationError("PHASE3_LOAD_PREFIX_COLLISION")
    backup = {
        "schema_version": 1,
        "campaign_id": CAMPAIGN_ID,
        "manifest_spec_sha256": plan["manifest_spec_sha256"],
        "old_settings": campaign.get("settings") or {},
        "old_probability_version": campaign["probability_version"],
        "old_campaign_version": campaign["version"],
        "prefix": PREFIX,
    }
    _write_private_json(backup_path, backup)
    slot = 0
    for prize in plan["prizes"]:
        conn.execute(
            f"""insert into {SCHEMA}.prize
            (id,campaign_id,name,category,image_url,probability,is_active,is_test)
            values(%s,%s,%s,%s,'/assets/icons/Picture-Light.png',%s,true,true)""",
            (prize["id"], CAMPAIGN_ID, prize["name"], prize["category"], prize["probability"]),
        )
        for number in range(1, prize["quantity"] + 1):
            slot += 1
            inventory_id = f"{prize['id']}_{number:03d}"
            conn.execute(
                f"insert into {SCHEMA}.inventory_item(id,prize_id) values(%s,%s)",
                (inventory_id, prize["id"]),
            )
            conn.execute(
                f"""insert into {SCHEMA}.inventory_history
                (inventory_item_id,to_status,reason,related_type,related_id)
                values(%s,'AVAILABLE','PHASE3_LOAD_SYNTHETIC_POOL','manifest',%s)""",
                (inventory_id, plan["manifest_spec_sha256"]),
            )
            conn.execute(
                f"""insert into {SCHEMA}.draw_pool_slot
                (campaign_id,slot_number,outcome_kind,prize_id,inventory_item_id)
                values(%s,%s,'PRIZE',%s,%s)""",
                (CAMPAIGN_ID, slot, prize["id"], inventory_id),
            )
    conn.execute(
        f"""insert into {SCHEMA}.draw_pool_slot(campaign_id,slot_number,outcome_kind)
        select %s,n,'BENEFIT' from generate_series(%s,5000)n""",
        (CAMPAIGN_ID, slot + 1),
    )
    conn.execute(
        f"""update {SCHEMA}.campaign set
        settings=jsonb_set(
            jsonb_set(settings,'{{phase3_manifest_hash}}',to_jsonb(%s::text),true),
            '{{phase3_probability_version}}',to_jsonb(%s::text),true
        ),
        probability_version=%s,version=version+1,updated_at=clock_timestamp()
        where id=%s""",
        (plan["manifest_spec_sha256"], plan["probability_version"],
         plan["probability_version"], CAMPAIGN_ID),
    )
    counts = _validate_existing_pool(conn, plan)
    return {"created": True, **counts, "manifest_spec_sha256": plan["manifest_spec_sha256"]}


def rollback_pool(conn, backup: dict[str, Any]) -> dict[str, Any]:
    if (
        backup.get("schema_version") != 1
        or backup.get("campaign_id") != CAMPAIGN_ID
        or backup.get("manifest_spec_sha256") != EXPECTED_SPEC_SHA256
        or backup.get("prefix") != PREFIX
    ):
        raise PoolPreparationError("PHASE3_LOAD_BACKUP_INVALID")
    conn.execute(
        "select pg_advisory_xact_lock(hashtextextended(%s,0))",
        ("draw-pool:" + CAMPAIGN_ID,),
    )
    _guard, campaign = _maintenance_scope(conn, lock=True)
    counts = _pool_counts(conn)
    if counts["allocated"]:
        raise PoolPreparationError("PHASE3_LOAD_ROLLBACK_POOL_USED")
    if (campaign.get("settings") or {}).get("phase3_manifest_hash") != EXPECTED_SPEC_SHA256:
        raise PoolPreparationError("PHASE3_LOAD_ROLLBACK_MARKER_CHANGED")
    conn.execute(f"delete from {SCHEMA}.draw_pool_slot where campaign_id=%s", (CAMPAIGN_ID,))
    inventory_ids = [
        row["id"] for row in conn.execute(
            f"select id from {SCHEMA}.inventory_item where id like %s", (PREFIX + "%",),
        )
    ]
    if inventory_ids:
        conn.execute(
            f"delete from {SCHEMA}.inventory_history where inventory_item_id=any(%s)",
            (inventory_ids,),
        )
        conn.execute(f"delete from {SCHEMA}.inventory_item where id=any(%s)", (inventory_ids,))
    conn.execute(f"delete from {SCHEMA}.prize where id like %s", (PREFIX + "%",))
    conn.execute(
        f"""update {SCHEMA}.campaign set settings=%s::jsonb,probability_version=%s,
        version=%s,updated_at=clock_timestamp() where id=%s""",
        (json.dumps(backup["old_settings"]), backup["old_probability_version"],
         backup["old_campaign_version"], CAMPAIGN_ID),
    )
    return {"rolled_back": True, "removed_slots": counts["total"], "removed_inventory": len(inventory_ids)}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--apply", action="store_true")
    action.add_argument("--rollback", action="store_true")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--database-url-file", type=Path)
    parser.add_argument("--backup", type=Path)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    plan = load_plan(args.manifest)
    if not args.apply and not args.rollback:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    if not args.database_url_file or not args.backup:
        raise PoolPreparationError("PHASE3_LOAD_DATABASE_AND_BACKUP_REQUIRED")
    dsn = _private_text(args.database_url_file)
    with connect(dsn) as conn:
        if args.apply:
            with conn.transaction():
                result = apply_pool(conn, plan, args.backup)
        else:
            backup = json.loads(_private_text(args.backup))
            with conn.transaction():
                result = rollback_pool(conn, backup)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (PoolPreparationError, OSError, psycopg.Error, json.JSONDecodeError) as error:
        print(json.dumps({"ok": False, "error": type(error).__name__}), file=sys.stderr)
        raise SystemExit(2)
