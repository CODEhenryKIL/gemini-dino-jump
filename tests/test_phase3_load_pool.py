import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from prepare_phase3_load_pool import (
    CAMPAIGN_ID,
    EXPECTED_SPEC_SHA256,
    PREFIX,
    PoolPreparationError,
    apply_pool,
    load_plan,
    rollback_pool,
)
from test_migration_acceptance import (
    ADDITIONS,
    CLAIM_DRAFT,
    CLAIM_FIX,
    FOUNDATION,
    GAME_V21,
    INTERRUPTED_AND_SHARE,
    KAKAO_SHARE_WEBHOOK,
    LOW_SCORE_REFUND,
    PHASE2,
    PHASE3,
    REAL_TOP3_CONTACT,
    TemporaryAuditDatabase,
)


class Phase3LoadPoolPlanTest(unittest.TestCase):
    def test_plan_is_network_free_and_pinned_to_current_manifest(self):
        plan = load_plan()
        self.assertEqual(plan["manifest_spec_sha256"], EXPECTED_SPEC_SHA256)
        self.assertEqual((plan["total_slots"], plan["prize_slots"], plan["benefit_slots"]), (5000, 77, 4923))
        self.assertEqual(sum(item["quantity"] for item in plan["prizes"]), 77)
        self.assertTrue(all(item["id"].startswith(PREFIX) for item in plan["prizes"]))
        self.assertEqual((plan["network_calls"], plan["database_writes"]), (0, 0))

    def test_manifest_quantity_change_requires_a_new_reviewed_digest(self):
        manifest = json.loads((ROOT / "server/production-launch-manifest.json").read_text())
        changed = copy.deepcopy(manifest)
        changed["draw_prizes"][0]["quantity"] += 1
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "changed.json"
            path.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaisesRegex(PoolPreparationError, "PHASE3_LOAD_MANIFEST_CHANGED"):
                load_plan(path)


class Phase3LoadPoolPostgresTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database = TemporaryAuditDatabase()
        cls.database.create()
        for migration in (
            FOUNDATION, ADDITIONS, CLAIM_FIX, PHASE2, GAME_V21,
            REAL_TOP3_CONTACT, CLAIM_DRAFT, LOW_SCORE_REFUND,
            KAKAO_SHARE_WEBHOOK, INTERRUPTED_AND_SHARE, PHASE3,
        ):
            cls.database.apply(migration)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "database"):
            cls.database.drop()

    def connect(self):
        return psycopg.connect(self.database.dsn, row_factory=dict_row)

    def setUp(self):
        with self.connect() as conn:
            conn.execute("delete from dino_dev.environment_guard")
            conn.execute("delete from dino_dev.draw_pool_slot")
            conn.execute("delete from dino_dev.inventory_history")
            conn.execute("delete from dino_dev.inventory_item")
            conn.execute("delete from dino_dev.prize")
            conn.execute("delete from dino_dev.campaign")
            conn.execute(
                """insert into dino_dev.campaign
                (id,title,status,version,game_version,benefit_url,settings,probability_version,is_test,real_prizes_enabled)
                values(%s,'load','ACTIVE',7,'1.2.0','https://example.invalid','{"keep":true}','legacy',true,false)""",
                (CAMPAIGN_ID,),
            )
            conn.execute(
                """insert into dino_dev.environment_guard
                (singleton,environment,project_ref,schema_name,synthetic_only,test_seed,campaign_id)
                values(true,'preview','igfrnexknwtiljdqjrbp','dino_dev',true,true,%s)""",
                (CAMPAIGN_ID,),
            )
            conn.execute(
                """insert into dino_dev.prize
                (id,campaign_id,name,category,image_url,probability,is_active,is_test)
                values('legacy_benefit',%s,'benefit','NO_PRIZE','/benefit.png',0,true,true),
                      ('legacy_keep',%s,'keep','COUPON','/keep.png',0.1,true,true)""",
                (CAMPAIGN_ID, CAMPAIGN_ID),
            )
            conn.execute("insert into dino_dev.inventory_item(id,prize_id) values('legacy_keep_001','legacy_keep')")

    def test_apply_is_exact_idempotent_and_rollback_preserves_legacy_rows(self):
        plan = load_plan()
        with tempfile.TemporaryDirectory() as directory:
            backup_path = Path(directory) / "rollback.json"
            with self.connect() as conn:
                result = apply_pool(conn, plan, backup_path)
            self.assertTrue(result["created"])
            self.assertEqual((result["total"], result["prizes"], result["benefits"]), (5000, 77, 4923))
            self.assertEqual(backup_path.stat().st_mode & 0o777, 0o600)

            with self.connect() as conn:
                second = apply_pool(conn, plan, backup_path)
                campaign = conn.execute(
                    "select version,settings,probability_version from dino_dev.campaign where id=%s",
                    (CAMPAIGN_ID,),
                ).fetchone()
                prefixed = conn.execute(
                    "select count(*)::int n from dino_dev.inventory_item where id like %s",
                    (PREFIX + "%",),
                ).fetchone()["n"]
            self.assertFalse(second["created"])
            self.assertEqual(prefixed, 77)
            self.assertEqual(campaign["version"], 8)
            self.assertEqual(campaign["settings"]["phase3_manifest_hash"], EXPECTED_SPEC_SHA256)
            self.assertEqual(campaign["settings"]["phase3_probability_version"], plan["probability_version"])

            backup = json.loads(backup_path.read_text())
            with self.connect() as conn:
                rolled_back = rollback_pool(conn, backup)
            self.assertEqual((rolled_back["removed_slots"], rolled_back["removed_inventory"]), (5000, 77))
            with self.connect() as conn:
                state = conn.execute(
                    """select version,settings,probability_version,
                    (select count(*) from dino_dev.draw_pool_slot) slots,
                    (select count(*) from dino_dev.prize where id like %s) prefixed_prizes,
                    (select count(*) from dino_dev.inventory_item where id='legacy_keep_001') legacy_inventory
                    from dino_dev.campaign where id=%s""",
                    (PREFIX + "%", CAMPAIGN_ID),
                ).fetchone()
            self.assertEqual(dict(state), {
                "version": 7,
                "settings": {"keep": True},
                "probability_version": "legacy",
                "slots": 0,
                "prefixed_prizes": 0,
                "legacy_inventory": 1,
            })

    def test_apply_fails_closed_when_pool_is_not_empty(self):
        with self.connect() as conn:
            conn.execute(
                "insert into dino_dev.draw_pool_slot(campaign_id,slot_number,outcome_kind) values(%s,1,'BENEFIT')",
                (CAMPAIGN_ID,),
            )
        with tempfile.TemporaryDirectory() as directory, self.connect() as conn:
            with self.assertRaisesRegex(PoolPreparationError, "PHASE3_LOAD_POOL_NOT_EMPTY"):
                apply_pool(conn, load_plan(), Path(directory) / "backup.json")
        with self.connect() as conn:
            self.assertEqual(conn.execute("select count(*) n from dino_dev.draw_pool_slot").fetchone()["n"], 1)
            self.assertEqual(conn.execute("select count(*) n from dino_dev.prize where id like %s", (PREFIX + "%",)).fetchone()["n"], 0)


if __name__ == "__main__":
    unittest.main()
