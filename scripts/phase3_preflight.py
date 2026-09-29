"""Read-only validation of the Phase 3 inventory and launch preparation manifest.

This validates a document, not live infrastructure or the truth of approval records.
No deployment, database mutation, or public-event activation is performed.
"""
import argparse
import datetime as dt
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "config/phase3-launch.json"


def validate(manifest):
    errors, pending = [], []
    prizes = manifest.get("draw_prizes", [])
    ranking = manifest.get("ranking_prizes", [])
    pool = manifest.get("draw_pool", {})
    for collection, rows in (("draw_prizes", prizes), ("ranking_prizes", ranking)):
        ids = [row.get("id") for row in rows]
        if len(set(ids)) != len(ids) or not all(ids):
            errors.append(f"{collection}: 상품 ID가 비어 있거나 중복됩니다")
        for row in rows:
            if any(type(row.get(key)) is not int or row[key] <= 0 for key in ("quantity", "unit_price_krw")):
                errors.append(f"{collection}: 수량·단가는 양의 정수여야 합니다")
    if errors:
        return {"errors": errors, "pending": pending, "totals": {}}

    draw_count = sum(row["quantity"] for row in prizes)
    draw_budget = sum(row["quantity"] * row["unit_price_krw"] for row in prizes)
    ranking_count = sum(row["quantity"] for row in ranking)
    ranking_budget = sum(row["quantity"] * row["unit_price_krw"] for row in ranking)
    expected_draw = dict(zip(
        ("samtanbyme", "sony_ult_wear", "orthomol_7day", "naverpay_50000", "musinsa_50000", "baemin_20000", "starbucks_10000", "convenience_5000", "ghana", "snickers", "chupa_chups"),
        (1, 2, 2, 3, 2, 4, 9, 24, 10, 10, 10)))
    if {row["id"]: row["quantity"] for row in prizes} != expected_draw:
        errors.append("복주머니 상품별 수량이 확정 재고와 다릅니다")
    actual_ranking = sorted((row.get("rank", 0), row["id"], row["quantity"], row["unit_price_krw"]) for row in ranking)
    if actual_ranking != [(1, "musinsa_50000", 1, 50000), (2, "baemin_20000", 1, 20000), (3, "starbucks_10000", 1, 10000)]:
        errors.append("랭킹 경품은 무신사 5만원·배민 2만원·스타벅스 1만원 각 1개여야 합니다")
    if (draw_count, draw_budget, ranking_count, ranking_budget) != (77, 1519000, 3, 80000):
        errors.append("확정 경품 수량 또는 예산 합계가 다릅니다")
    if pool != {"total_slots": 5000, "benefit_slots": 4923, "max_draws_per_participant": 10, "mode": "WITHOUT_REPLACEMENT"}:
        errors.append("추첨 설정은 총 5,000자리·혜택 4,923자리·참가자당 최대 10회 비복원 방식이어야 합니다")
    if not isinstance(manifest.get("version"), str) or not manifest["version"].strip():
        errors.append("설정 버전이 필요합니다")
    if manifest.get("status") not in {"DRAFT", "APPROVED"}:
        errors.append("설정 상태는 DRAFT 또는 APPROVED여야 합니다")
    elif manifest["status"] != "APPROVED":
        pending.append("status.APPROVED")
    if type(manifest.get("event_enabled")) is not bool:
        errors.append("event_enabled는 true 또는 false여야 합니다")

    campaign = manifest.get("campaign", {})
    if not isinstance(campaign.get("id"), str) or not campaign["id"].strip():
        pending.append("campaign.id")
    if campaign.get("timezone") != "Asia/Seoul":
        errors.append("행사 표시 시간대는 Asia/Seoul이어야 합니다")
    if bool(campaign.get("opens_at")) != bool(campaign.get("closes_at")):
        errors.append("행사 시작과 종료는 함께 설정해야 합니다")
    dates = {}
    for key in ("opens_at", "closes_at", "claim_closes_at"):
        value = campaign.get(key)
        if not value:
            pending.append(f"campaign.{key}")
            continue
        try:
            dates[key] = dt.datetime.fromisoformat(value)
            if dates[key].utcoffset() is None:
                raise ValueError()
        except (ValueError, TypeError):
            errors.append(f"campaign.{key}: 시간대가 포함된 ISO 날짜가 필요합니다")
    if all(key in dates and dates[key].utcoffset() is not None for key in ("opens_at", "closes_at")) and dates["opens_at"] >= dates["closes_at"]:
        errors.append("행사 종료는 시작보다 늦어야 합니다")
    if all(key in dates and dates[key].utcoffset() is not None for key in ("closes_at", "claim_closes_at")) and dates["claim_closes_at"] <= dates["closes_at"]:
        errors.append("수령 접수 마감은 행사 종료보다 늦어야 합니다")

    required = {
        "policies": ("pool_exhaustion", "unallocated_inventory_at_close", "beta_data_migration", "ranking_ties", "finish_after_close", "draw_and_ranking_double_award", "eligibility_and_proof", "claim_deadline_and_no_response", "duplicate_person_claims", "privacy_retention_and_deletion", "operator_contact"),
        "approvals": ("environment", "inventory", "privacy", "benefit_and_brand", "public_launch"),
        "evidence": ("target_db_and_backup", "runtime_production_guard", "inventory_reconciliation", "real_kakao_game_and_draw", "physical_device_qa", "final_load_test", "notion_and_benefit_links", "rollback_rehearsal"),
    }
    for group, keys in required.items():
        for key in keys:
            value = manifest.get(group, {}).get(key)
            if not isinstance(value, str) or not value.strip() or value.strip().upper() in {"TODO", "TBD", "PENDING", "UNDECIDED"}:
                pending.append(f"{group}.{key}")
    for key in ("unlimited_play", "synthetic_inventory", "shortened_clock"):
        if manifest.get("production_flags", {}).get(key) is not False:
            errors.append(f"production_flags.{key}: 본행사 설정은 false여야 합니다")
    if manifest.get("event_enabled") is not False and (errors or pending or manifest.get("status") != "APPROVED"):
        errors.append("미확정·미승인 설정으로 본행사를 켤 수 없습니다")
    return {"errors": errors, "pending": pending, "totals": {
        "draw_prizes": draw_count, "draw_budget_krw": draw_budget,
        "ranking_prizes": ranking_count, "ranking_budget_krw": ranking_budget,
        "total_budget_krw": draw_budget + ranking_budget,
        "initial_actual_prize_probability": draw_count / 5000,
    }}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", nargs="?", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--require-launch-ready", action="store_true")
    args = parser.parse_args()
    try:
        result = validate(json.loads(args.manifest.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError, AttributeError, KeyError) as exc:
        parser.exit(2, f"Invalid manifest: {type(exc).__name__}\n")
    result["document_ready"] = not result["errors"] and not result["pending"]
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(bool(result["errors"] or (args.require_launch_ready and result["pending"])))


if __name__ == "__main__":
    raise SystemExit(main())
