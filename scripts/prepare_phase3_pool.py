"""Prepare a separate, paused synthetic Phase 3 pool on a local PostgreSQL DB.

Never selects the campaign for the app, resets records, or provisions real stock.
The DSN comes only from PHASE3_POOL_DATABASE_URL and is never logged.
"""
import argparse
import hashlib
import json
import os
import re
from urllib.parse import urlparse

import psycopg
from psycopg.rows import dict_row

from phase3_preflight import DEFAULT_MANIFEST, validate


def provision(conn, manifest, campaign_id):
    if not re.fullmatch(r"phase3_[a-z0-9_]{1,40}_test", campaign_id):
        raise ValueError("Use a separate phase3_*_test campaign ID")
    result = validate(manifest)
    if result["errors"]:
        raise ValueError("Manifest inventory validation failed")
    conn.execute("select pg_advisory_xact_lock(hashtext(%s))", ("phase3-provision:" + campaign_id,))
    guard = conn.execute("select * from dino_dev.environment_guard where singleton for update").fetchone()
    if not guard or guard["environment"] not in {"local", "test"} or not guard["synthetic_only"] or guard["project_ref"] != "local":
        raise ValueError("Only guarded local synthetic databases are supported")
    if guard["campaign_id"] == campaign_id:
        raise ValueError("Refusing to provision the active application campaign")
    inventory_spec = {key: manifest[key] for key in ("version", "draw_pool", "draw_prizes", "ranking_prizes")}
    digest = hashlib.sha256(json.dumps(inventory_spec, sort_keys=True).encode()).hexdigest()
    current = conn.execute("select * from dino_dev.campaign where id=%s for update", (campaign_id,)).fetchone()
    if current:
        if not current["is_test"] or current["real_prizes_enabled"] or current["settings"].get("phase3_manifest_hash") != digest:
            raise ValueError("Existing campaign differs; no records were overwritten")
        counts = conn.execute("select count(*) total,count(*) filter(where outcome_kind='PRIZE') prizes,count(*) filter(where allocated_draw_id is not null) allocated from dino_dev.draw_pool_slot where campaign_id=%s", (campaign_id,)).fetchone()
        if (counts["total"], counts["prizes"]) != (5000, 77):
            raise ValueError("Existing pool is incomplete; refusing automatic repair")
        rows = conn.execute("""select s.prize_id,count(*) quantity,
          bool_and(p.campaign_id=s.campaign_id and i.prize_id=s.prize_id) consistent
          from dino_dev.draw_pool_slot s
          join dino_dev.prize p on p.id=s.prize_id
          join dino_dev.inventory_item i on i.id=s.inventory_item_id
          where s.campaign_id=%s and s.outcome_kind='PRIZE' group by s.prize_id""", (campaign_id,)).fetchall()
        expected = {campaign_id + "_" + row["id"]: row["quantity"] for row in manifest["draw_prizes"]}
        if {row["prize_id"]: row["quantity"] for row in rows} != expected or not all(row["consistent"] for row in rows):
            raise ValueError("Existing prize distribution differs; refusing automatic repair")
        return {"campaign_id": campaign_id, "created": False, **counts}

    settings = {"initial_tickets": 1, "invitation_balance_max": 3, "invitation_cooldown_hours": 10,
                "draw_max_rounds": 10, "phase3_manifest_hash": digest,
                "ranking_inventory_separate": manifest["ranking_prizes"]}
    conn.execute("""insert into dino_dev.campaign(id,title,status,game_version,benefit_url,settings,probability_version)
      values(%s,'3차 격리 합성 경품 검증','PAUSED','2.1.0','https://VQyu3J.s.gy/Game',%s::jsonb,%s)""",
                 (campaign_id, json.dumps(settings), manifest["version"]))
    slot_number = 0
    for prize in manifest["draw_prizes"]:
        prize_id = campaign_id + "_" + prize["id"]
        conn.execute("""insert into dino_dev.prize(id,campaign_id,name,category,image_url,probability)
          values(%s,%s,%s,%s,'/assets/icons/Picture-Light.png',%s)""",
                     (prize_id, campaign_id, "[합성 검증] " + prize["name"], prize["category"], prize["quantity"] / 5000))
        for number in range(1, prize["quantity"] + 1):
            slot_number += 1
            inventory_id = f"{prize_id}_{number:03d}"
            conn.execute("insert into dino_dev.inventory_item(id,prize_id) values(%s,%s)", (inventory_id, prize_id))
            conn.execute("""insert into dino_dev.inventory_history(inventory_item_id,to_status,reason,related_type,related_id)
              values(%s,'AVAILABLE','PHASE3_ISOLATED_SYNTHETIC_POOL','manifest',%s)""", (inventory_id, manifest["version"]))
            conn.execute("""insert into dino_dev.draw_pool_slot(campaign_id,slot_number,outcome_kind,prize_id,inventory_item_id)
              values(%s,%s,'PRIZE',%s,%s)""", (campaign_id, slot_number, prize_id, inventory_id))
    conn.execute("""insert into dino_dev.prize(id,campaign_id,name,category,image_url,probability)
      values(%s,%s,'Gemini 혜택','NO_PRIZE','/assets/icons/Picture-Light.png',0.9846)""", (campaign_id + "_benefit", campaign_id))
    conn.execute("""insert into dino_dev.draw_pool_slot(campaign_id,slot_number,outcome_kind)
      select %s,n,'BENEFIT' from generate_series(78,5000)n""", (campaign_id,))
    counts = conn.execute("select count(*) total,count(*) filter(where outcome_kind='PRIZE') prizes from dino_dev.draw_pool_slot where campaign_id=%s", (campaign_id,)).fetchone()
    if (counts["total"], counts["prizes"]) != (5000, 77):
        raise ValueError("Pool validation failed; transaction must be rolled back")
    return {"campaign_id": campaign_id, "created": True, "allocated": 0, **counts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", default="phase3_inventory_test")
    args = parser.parse_args()
    dsn = os.getenv("PHASE3_POOL_DATABASE_URL", "")
    target = urlparse(dsn)
    if target.scheme not in {"postgres", "postgresql"} or target.hostname not in {"localhost", "127.0.0.1", "::1"}:
        parser.exit(2, "PHASE3_POOL_DATABASE_URL must identify a local PostgreSQL database\n")
    # libpq parameters can override a URI host; disallow alternate connection routing.
    if target.query or target.fragment:
        parser.exit(2, "Connection query parameters are not supported\n")
    manifest = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    try:
        with psycopg.connect(dsn, row_factory=dict_row) as conn:
            result = provision(conn, manifest, args.campaign)
    except (ValueError, psycopg.Error) as exc:
        parser.exit(1, f"Pool preparation failed: {type(exc).__name__}; no partial writes committed\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
